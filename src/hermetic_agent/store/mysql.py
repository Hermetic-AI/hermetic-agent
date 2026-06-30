"""MySQL 版 ``SessionRepository`` 兼容 Shim (Tortoise ORM).

新架构 (``hermetic_agent.store.repositories.mysql``) 把 storage 拆成 6 个 per-entity
Repository, 内部用 Tortoise ORM. 但 ``AgentBridge`` / ``OpenCodeAdapter`` / 
``ClaudeCodeAdapter`` / ``lifecycle`` 还在用旧 ``SessionRepository`` 接口 
(``save_session`` / ``create_session`` / ``get_session`` / ``list_sessions`` / 
``delete_session`` / ``save_message`` / ``create_message`` / ``get_messages``).

本文件提供 shim, 把旧接口适配到 Tortoise + per-entity repo.

字段翻译:
- 旧 ``Session.session_id`` ↔ Tortoise ``Session.id``
- 旧 ``Message.message_id`` ↔ Tortoise ``Message.id``
- 旧 ``Message.parts: list[Part]`` (内嵌) ↔ Tortoise ``Message`` + ``Part`` 两表

启动期: ``connect()`` 调 ``Tortoise.init()``, ``init_schema()`` 调
``Tortoise.generate_schemas()`` — 不再需要外部 DDL 文件.
"""
from __future__ import annotations

from typing import Any

import structlog

from hermetic_agent.store.base import Message, Part, Session, SessionRepository
from hermetic_agent.store.models._common import close_tortoise, init_tortoise
from hermetic_agent.store.models.message import Message as NewMessage
from hermetic_agent.store.models.part import Part as NewPart
from hermetic_agent.store.models.session import Session as NewSession
from hermetic_agent.store.repositories.mysql import (
    MySQLMessageRepository,
    MySQLPartRepository,
    MySQLSessionRepository,
)

logger = structlog.get_logger(__name__)


def _legacy_to_new_session(s: Session) -> NewSession:
    """旧 ``Session`` (session_id 字段) -> Tortoise ``Session`` (id 字段 + 聚合默认值)."""
    return NewSession(
        id=s.session_id,
        user_id=s.user_id or "",
        title=s.title or "New Session",
        model=s.model,
        agent_name=s.agent_name or "",
        metadata=dict(s.metadata) if s.metadata else None,
    )


def _new_to_legacy_session(s: NewSession) -> Session:
    """Tortoise ``Session`` -> 旧 ``Session`` (丢聚合, 留主字段 + 元数据)."""
    return Session(
        session_id=str(s.id),
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
    """旧 ``Message`` -> Tortoise ``Message`` (id 字段名不同, parts 拆出)."""
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
    """旧 ``Part`` -> Tortoise ``Part`` (id 字段由 NewPart 默认工厂生成)."""
    return NewPart(
        message_id=message_id,
        session_id=session_id,
        part_type=p.part_type,
        content=p.content,
        position=position,
        metadata=dict(p.metadata) if p.metadata else None,
    )


def _new_part_to_legacy(p: NewPart) -> Part:
    """Tortoise ``Part`` -> 旧 ``Part`` (旧 Part 没有 id / message_id / session_id / position)."""
    return Part(
        content=p.content or "",
        part_type=p.part_type,
        metadata=dict(p.metadata) if p.metadata else {},
    )


def _new_message_to_legacy(m: NewMessage, parts: list[NewPart]) -> Message:
    """Tortoise ``Message`` + 关联 ``Part`` 列表 -> 旧 ``Message`` (parts 内嵌)."""
    return Message(
        message_id=str(m.id),
        session_id=m.session_id,
        role=m.role,
        content=m.content,
        created_at=m.created_at,
        parts=[_new_part_to_legacy(p) for p in parts],
        metadata=dict(m.metadata) if m.metadata else {},
    )


class MySQLStorage(SessionRepository):
    """MySQL 版 ``SessionRepository`` - 把旧接口适配到 Tortoise + per-entity repos.

    启动期: ``connect()`` 调 ``Tortoise.init()``, ``init_schema()`` 调
    ``Tortoise.generate_schemas()`` (model 自描述, 无外部 DDL).
    业务: 委派到 ``MySQLSessionRepository`` / ``MySQLMessageRepository`` /
    ``MySQLPartRepository``.

    Args:
        dsn: MySQL DSN 字符串. 必填 (Tortoise 没有 pool 注入点).
    """

    def __init__(self, dsn: str | None = None) -> None:
        if not dsn:
            raise ValueError("MySQLStorage requires dsn")
        self._dsn = dsn
        self._session_repo = MySQLSessionRepository()
        self._message_repo = MySQLMessageRepository()
        self._part_repo = MySQLPartRepository()

    async def connect(self) -> None:
        """``Tortoise.init()`` 初始化. 幂等(重复 init Tortoise 会抛错, 外面包 try)."""
        try:
            await init_tortoise(self._dsn, generate_schemas=False)
            logger.info("mysql_storage_connected", dsn=self._dsn)
        except Exception as e:
            # ``Tortoise.init`` 重复调会 ``ConfigurationError: Already initialised``.
            # 这里允许重复 connect() (lifecycle 可能重入), 记录 debug 跳过.
            logger.debug("tortoise_already_inited", error=str(e))

    async def init_schema(self) -> None:
        """``Tortoise.generate_schemas()`` 自动建表. 幂等 (CREATE TABLE IF NOT EXISTS)."""
        from tortoise import Tortoise

        await Tortoise.generate_schemas()
        logger.info("mysql_storage_schema_initialized", source="tortoise.generate_schemas")

    async def close(self) -> None:
        """``Tortoise.close_connections()``."""
        await close_tortoise()

    async def save_session(self, session: Session) -> None:
        """写一个 session (upsert by session_id).

        Tortoise ``Model.save()`` 对主键已存在的记录做 UPDATE, 不存在做 INSERT,
        直接拿来做 upsert 语义, 比旧 ``MySQLSessionRepository.create`` 更友好.
        """
        new_s = _legacy_to_new_session(session)
        await new_s.save()
        logger.debug("session_saved", session_id=str(new_s.id))

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

        匹配旧 ``PostgresStorage`` 物理删语义.
        """
        return await self._session_repo.hard_delete(session_id)

    async def save_message(self, session_id: str, message: Message) -> None:
        """写一条 message, parts 一并 batch_create. 已存在同 id 则更新并替换 parts."""
        new_m = _legacy_to_new_message(message)
        await new_m.save()
        old_parts = await self._part_repo.list_by_message(str(new_m.id))
        for p in old_parts:
            await self._part_repo.hard_delete(str(p.id))
        if message.parts:
            new_parts = [
                _legacy_to_new_part(
                    p, message_id=str(new_m.id), session_id=session_id, position=i,
                )
                for i, p in enumerate(message.parts)
            ]
            await self._part_repo.batch_create(new_parts)
        logger.debug(
            "message_saved",
            message_id=str(new_m.id),
            session_id=session_id,
            parts=len(message.parts),
        )

    async def get_messages(
        self, session_id: str, limit: int = 100,
    ) -> list[Message]:
        """按 created_at ASC 拉 session 全部 messages, 一次性拉所有 parts 再 merge.

        避免 N+1: Tortoise ``Part`` 表有 ``session_id`` 冗余, 一次 ``list_by_session``
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
            parts_by_msg.setdefault(str(p.message_id), []).append(p)
        for k in parts_by_msg:
            parts_by_msg[k].sort(key=lambda x: (x.position, x.id))
        return [
            _new_message_to_legacy(m, parts_by_msg.get(str(m.id), []))
            for m in new_messages
        ]


# Back-compat alias (跟 memory.py / postgres.py 风格一致; 同时方便老代码 import).
MySQLSessionRepository_Legacy = MySQLStorage
