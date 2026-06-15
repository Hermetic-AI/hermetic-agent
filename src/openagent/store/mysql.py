"""MySQL 版 ``SessionRepository`` 兼容 Shim.

新架构 (``openagent.store.repositories.mysql``) 把 storage 拆成 6 个 per-entity
Repository + Service 容器. 但 ``AgentBridge`` / ``OpenCodeAdapter`` / 
``ClaudeCodeAdapter`` / ``lifecycle`` 还在用旧 ``SessionRepository`` 接口 
(``save_session`` / ``create_session`` / ``get_session`` / ``list_sessions`` / 
``delete_session`` / ``save_message`` / ``create_message`` / ``get_messages``).

本文件提供 shim, 把旧接口适配到新 driver (``MySQLPool``) + per-entity repo
(``MySQLSessionRepository`` / ``MySQLMessageRepository`` / ``MySQLPartRepository``).

字段翻译:
- 旧 ``Session.session_id`` ↔ 新 ``Session.id``
- 旧 ``Message.message_id`` ↔ 新 ``Message.id``
- 旧 ``Message.parts: list[Part]`` (内嵌) ↔ 新 ``messages`` + ``parts`` 两表

启动期: ``connect()`` 建池, ``init_schema()`` 幂等执行 v2 schema
(读 ``docs/db/openagent-schema.sql``).
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import structlog

from openagent.store.base import Message, Part, Session, SessionRepository
from openagent.store.driver import MySQLConfig, MySQLPool
from openagent.store.models.message import Message as NewMessage
from openagent.store.models.part import Part as NewPart
from openagent.store.models.session import Session as NewSession
from openagent.store.repositories.mysql import (
    MySQLMessageRepository,
    MySQLPartRepository,
    MySQLSessionRepository,
)

logger = structlog.get_logger(__name__)

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "docs" / "db" / "openagent-schema.sql"
)


def _legacy_to_new_session(s: Session) -> NewSession:
    """旧 ``Session`` (session_id 字段) -> 新 ``Session`` (id 字段 + 聚合默认值)."""
    return NewSession(
        id=s.session_id,
        user_id=s.user_id or "",
        title=s.title or "New Session",
        model=s.model,
        agent_name=s.agent_name or "",
        metadata=dict(s.metadata) if s.metadata else None,
    )


def _new_to_legacy_session(s: NewSession) -> Session:
    """新 ``Session`` -> 旧 ``Session`` (丢聚合, 留主字段 + 元数据)."""
    return Session(
        session_id=s.id,
        user_id=s.user_id or "",
        title=s.title or "New Session",
        model=s.model,
        agent_name=s.agent_name or "",
        created_at=s.created_at,
        updated_at=s.updated_at,
        messages=[],
        metadata=dict(s.metadata) if s.metadata else {},
    )


def _legacy_to_new_message(m: Message) -> NewMessage:
    """旧 ``Message`` (message_id 字段) -> 新 ``Message`` (id 字段, parts 拆出)."""
    return NewMessage(
        id=m.message_id,
        session_id=m.session_id or "",
        role=m.role,
        content=m.content,
        metadata=dict(m.metadata) if m.metadata else None,
        created_at=m.created_at,
        updated_at=m.created_at,
    )


def _legacy_to_new_part(
    p: Part, *, message_id: str, session_id: str, position: int
) -> NewPart:
    """旧 ``Part`` -> 新 ``Part`` (id 字段由 NewPart 默认工厂生成)."""
    return NewPart(
        message_id=message_id,
        session_id=session_id,
        part_type=p.part_type,
        content=p.content,
        position=position,
        metadata=dict(p.metadata) if p.metadata else None,
    )


def _new_part_to_legacy(p: NewPart) -> Part:
    """新 ``Part`` -> 旧 ``Part`` (旧 Part 没有 id / message_id / session_id / position)."""
    return Part(
        content=p.content or "",
        part_type=p.part_type,
        metadata=dict(p.metadata) if p.metadata else {},
    )


def _new_message_to_legacy(
    m: NewMessage, parts: list[NewPart]
) -> Message:
    """新 ``Message`` + 关联 ``Part`` 列表 -> 旧 ``Message`` (parts 内嵌)."""
    return Message(
        message_id=m.id,
        session_id=m.session_id,
        role=m.role,
        content=m.content,
        created_at=m.created_at,
        parts=[_new_part_to_legacy(p) for p in parts],
        metadata=dict(m.metadata) if m.metadata else {},
    )


class MySQLStorage(SessionRepository):
    """MySQL 版 ``SessionRepository`` - 把旧接口适配到新 driver + per-entity repos.

    启动期: ``connect()`` 建池, ``init_schema()`` 幂等执行 v2 schema.
    业务: ``save_session`` / ``get_session`` / ``list_sessions`` / ``delete_session``
    委派到 ``MySQLSessionRepository``; ``save_message`` / ``get_messages`` 委派到
    ``MySQLMessageRepository`` + ``MySQLPartRepository`` (parts 拆表).

    Args:
        dsn: MySQL DSN 字符串. 与 ``pool`` 二选一.
        pool: 已建好的 ``MySQLPool`` (测试 / 共享池场景).
        min_size: 自建池最小连接数.
        max_size: 自建池最大连接数.
        echo: 自建池是否 echo SQL.
    """

    def __init__(
        self,
        dsn: str | None = None,
        pool: MySQLPool | None = None,
        min_size: int = 5,
        max_size: int = 20,
        echo: bool = False,
    ) -> None:
        if pool is not None:
            self._pool = pool
            self._own_pool = False
        else:
            if not dsn:
                raise ValueError("MySQLStorage requires dsn or pool")
            cfg = MySQLConfig.from_dsn(dsn)
            self._pool = MySQLPool(
                cfg, min_size=min_size, max_size=max_size, echo=echo,
            )
            self._own_pool = True
        self._session_repo = MySQLSessionRepository(self._pool)
        self._message_repo = MySQLMessageRepository(self._pool)
        self._part_repo = MySQLPartRepository(self._pool)

    async def connect(self) -> None:
        """建池. 幂等."""
        await self._pool.connect()
        logger.info("mysql_storage_connected", own_pool=self._own_pool)

    async def init_schema(self) -> None:
        """读 ``docs/db/openagent-schema.sql`` 幂等执行. 需先 ``connect()``.

        Raises:
            RuntimeError: 找不到 schema 文件 / 池未连接.
        """
        if not _SCHEMA_PATH.exists():
            raise RuntimeError(
                f"Schema SQL not found at {_SCHEMA_PATH}; "
                "set up docs/db/openagent-schema.sql before starting."
            )
        ddl = _SCHEMA_PATH.read_text(encoding="utf-8")
        await self._pool.init_schema(ddl)
        logger.info("mysql_storage_schema_initialized", path=str(_SCHEMA_PATH))

    async def close(self) -> None:
        """关池 (仅关自建的; 外部注入的留给 owner)."""
        if self._own_pool:
            await self._pool.close()

    async def save_session(self, session: Session) -> None:
        """写一个 session (upsert by session_id).

        新 ``MySQLSessionRepository.create`` 是裸 INSERT, 重复 id 会 Duplicate.
        先 ``get_by_id`` 检查, 存在则 ``update``, 不存在则 ``create``.
        """
        new_s = _legacy_to_new_session(session)
        existing = await self._session_repo.get_by_id(new_s.id)
        if existing is None:
            await self._session_repo.create(new_s)
        else:
            await self._session_repo.update(
                new_s.id,
                user_id=new_s.user_id,
                title=new_s.title,
                model=new_s.model,
                agent_name=new_s.agent_name,
                metadata=new_s.metadata,
            )
        logger.debug("session_saved", session_id=new_s.id)

    async def get_session(self, session_id: str) -> Session | None:
        """按 session_id 取 session (不含 messages)."""
        new_s = await self._session_repo.get_by_id(session_id)
        if new_s is None:
            return None
        return _new_to_legacy_session(new_s)

    async def list_sessions(
        self, user_id: str | None = None, limit: int = 100,
    ) -> list[Session]:
        """列 sessions (按 updated_at DESC)."""
        kwargs: dict[str, Any] = {"limit": limit}
        if user_id is not None:
            kwargs["user_id"] = user_id
        new_sessions = await self._session_repo.list(**kwargs)
        return [_new_to_legacy_session(s) for s in new_sessions]

    async def delete_session(self, session_id: str) -> bool:
        """硬删 session (FK CASCADE 清掉 messages + parts).

        匹配旧 ``PostgresStorage`` 物理删语义. 业务上若要保留审计, 改用
        ``MySQLSessionRepository.soft_delete`` 并手动级联软删 messages.
        """
        return await self._session_repo.hard_delete(session_id)

    async def save_message(self, session_id: str, message: Message) -> None:
        """写一条 message, parts 一并 batch_create. 已存在同 id 则更新并替换 parts."""
        new_m = _legacy_to_new_message(message)
        existing = await self._message_repo.get_by_id(new_m.id)
        if existing is None:
            await self._message_repo.create(new_m)
        else:
            await self._message_repo.update(
                new_m.id,
                session_id=new_m.session_id,
                role=new_m.role,
                content=new_m.content,
                metadata=new_m.metadata,
            )
        old_parts = await self._part_repo.list_by_message(new_m.id)
        for p in old_parts:
            await self._part_repo.hard_delete(p.id)
        if message.parts:
            new_parts = [
                _legacy_to_new_part(
                    p, message_id=new_m.id, session_id=session_id, position=i,
                )
                for i, p in enumerate(message.parts)
            ]
            await self._part_repo.batch_create(new_parts)
        logger.debug(
            "message_saved",
            message_id=new_m.id,
            session_id=session_id,
            parts=len(message.parts),
        )

    async def get_messages(
        self, session_id: str, limit: int = 100,
    ) -> list[Message]:
        """按 created_at ASC 拉 session 全部 messages, 一次性拉所有 parts 再 merge.

        避免 N+1: v2 schema parts 有 session_id 冗余, 一次 ``list_by_session``
        拉完所有 parts, 按 message_id 分组, 再按 position 排序.
        """
        new_messages = await self._message_repo.list(
            session_id=session_id, limit=limit, include_deleted=False,
        )
        if not new_messages:
            return []
        all_parts = await self._part_repo.list_by_session(
            session_id, limit=limit * 50,
        )
        parts_by_msg: dict[str, list[NewPart]] = {}
        for p in all_parts:
            parts_by_msg.setdefault(p.message_id, []).append(p)
        for k in parts_by_msg:
            parts_by_msg[k].sort(key=lambda x: (x.position, x.id))
        return [
            _new_message_to_legacy(m, parts_by_msg.get(m.id, []))
            for m in new_messages
        ]


# Back-compat alias (跟 memory.py / postgres.py 风格一致)
MySQLSessionRepository_Legacy = MySQLStorage  # 避免与新架构 MySQLSessionRepository 同名冲突
