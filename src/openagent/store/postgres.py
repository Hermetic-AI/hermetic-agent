"""基于 asyncpg 的 PostgreSQL 版 ``SessionRepository``。"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator

import asyncpg
import structlog
from asyncpg import Pool, Record

from .base import Message, Part, Session, SessionRepository

logger = structlog.get_logger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT 'New Session',
    model TEXT,
    agent_name TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    parts JSONB NOT NULL DEFAULT '[]',
    metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_agent_name ON sessions(agent_name);

-- Forward-compatible migrations for older dev DBs (idempotent).
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS title TEXT NOT NULL DEFAULT 'New Session';
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS model TEXT;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS agent_name TEXT NOT NULL DEFAULT '';
"""


def _record_to_session(row: Record) -> Session:
    """将 asyncpg 行记录映射为 ``Session`` 实例（不加载消息）。"""
    keys = row.keys()
    return Session(
        session_id=row["session_id"],
        user_id=row["user_id"],
        title=row["title"] if "title" in keys else "New Session",
        model=row["model"] if "model" in keys else None,
        agent_name=row["agent_name"] if "agent_name" in keys else "",
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        messages=[],
        metadata=row["metadata"] or {},
    )


def _record_to_message(row: Record) -> Message:
    """将 asyncpg 行记录映射为 ``Message`` 实例（含 parts 重建）。"""
    parts_data = row["parts"] or []
    return Message(
        message_id=row["message_id"],
        session_id=row["session_id"],
        role=row["role"],
        content=row["content"],
        created_at=row["created_at"],
        parts=[Part.from_dict(p) for p in parts_data],
        metadata=row["metadata"] or {},
    )


class PostgresSessionRepository(SessionRepository):
    """PostgreSQL 版 ``SessionRepository``（从 ``PostgresStorage`` 改名而来）。"""
    def __init__(
        self,
        dsn: str | None = None,
        pool: Pool | None = None,
        min_size: int = 5,
        max_size: int = 10,
    ) -> None:
        """初始化仓储。

        Args:
            dsn: asyncpg 连接串；与 ``pool`` 二选一。
            pool: 已有的 asyncpg 连接池；为 ``None`` 时由本类自行创建。
            min_size: 自建连接池的最小连接数。
            max_size: 自建连接池的最大连接数。
        """
        self._dsn = dsn
        self._pool = pool
        self._min_size = min_size
        self._max_size = max_size
        self._own_pool = pool is None
        self._initialized = False

    async def initialize(self) -> None:
        """建立连接池并执行表结构初始化（幂等）。

        Raises:
            ValueError: 既没有提供 ``dsn`` 也没有提供 ``pool`` 时。
        """
        if self._initialized:
            return
        if self._pool is None:
            if self._dsn is None:
                raise ValueError("dsn or pool must be provided")
            self._pool = await asyncpg.create_pool(
                self._dsn,
                min_size=self._min_size,
                max_size=self._max_size,
            )
            logger.info("postgres_pool_created", dsn=self._dsn, min=self._min_size, max=self._max_size)
        await self._pool.execute(SCHEMA)
        self._initialized = True
        logger.info("postgres_storage_initialized")

    # Alias so app.py can call connect() (matches app.py startup contract)
    connect = initialize

    async def close(self) -> None:
        """关闭由本类自建的连接池；外部注入的池不会被关闭。"""
        if self._own_pool and self._pool is not None:
            await self._pool.close()
            logger.info("postgres_pool_closed")

    @asynccontextmanager
    async def _acquire(self) -> AsyncIterator[Pool]:
        """获取一个 asyncpg 连接，作用域内自动归还。"""
        if self._pool is None:
            raise RuntimeError("PostgresStorage not initialized. Call initialize() first.")
        async with self._pool.acquire() as conn:
            yield conn

    async def save_session(self, session: Session) -> None:
        """插入或更新一个会话（按 ``session_id`` 唯一）。

        Args:
            session: 完整会话对象。
        """
        async with self._acquire() as conn:
            await conn.execute(
                """
                INSERT INTO sessions
                    (session_id, user_id, title, model, agent_name, created_at, updated_at, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (session_id) DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    title = EXCLUDED.title,
                    model = EXCLUDED.model,
                    agent_name = EXCLUDED.agent_name,
                    updated_at = EXCLUDED.updated_at,
                    metadata = EXCLUDED.metadata
                """,
                session.session_id,
                session.user_id,
                session.title,
                session.model,
                session.agent_name,
                session.created_at,
                session.updated_at,
                json.dumps(session.metadata, ensure_ascii=False),
            )
        logger.debug("session_saved", session_id=session.session_id)

    # Adapter-facing API: persist a newly-created session (same SQL path as save_session)
    create_session = save_session

    async def get_session(self, session_id: str) -> Session | None:
        """按 ID 加载会话（不含消息体）。

        Args:
            session_id: 会话 ID。

        Returns:
            找到时返回 ``Session``，否则 ``None``。
        """
        async with self._acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM sessions WHERE session_id = $1",
                session_id,
            )
        if row is None:
            logger.debug("session_not_found", session_id=session_id)
            return None
        return _record_to_session(row)

    async def list_sessions(
        self, user_id: str | None = None, limit: int = 100
    ) -> list[Session]:
        """按 ``updated_at`` 倒序返回最近会话。

        Args:
            user_id: 可选的用户 ID 过滤。
            limit: 最多返回数量。

        Returns:
            会话列表（不含消息体）。
        """
        async with self._acquire() as conn:
            if user_id is not None:
                rows = await conn.fetch(
                    """
                    SELECT * FROM sessions
                    WHERE user_id = $1
                    ORDER BY updated_at DESC
                    LIMIT $2
                    """,
                    user_id,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM sessions
                    ORDER BY updated_at DESC
                    LIMIT $1
                    """,
                    limit,
                )
        return [_record_to_session(row) for row in rows]

    async def delete_session(self, session_id: str) -> bool:
        """删除指定会话；级联删除其消息。

        Args:
            session_id: 会话 ID。

        Returns:
            ``True`` 表示确实删除了一条记录。
        """
        async with self._acquire() as conn:
            result = await conn.execute(
                "DELETE FROM sessions WHERE session_id = $1",
                session_id,
            )
        deleted = result == "DELETE 1"
        logger.debug("session_deleted", session_id=session_id, success=deleted)
        return deleted

    async def save_message(self, session_id: str, message: Message) -> None:
        """插入或更新一条消息，并刷新所属会话的 ``updated_at``。

        Args:
            session_id: 所属会话 ID。
            message: 消息对象。
        """
        async with self._acquire() as conn:
            await conn.execute(
                """
                INSERT INTO messages (message_id, session_id, role, content, created_at, parts, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (message_id) DO UPDATE SET
                    session_id = EXCLUDED.session_id,
                    role = EXCLUDED.role,
                    content = EXCLUDED.content,
                    parts = EXCLUDED.parts,
                    metadata = EXCLUDED.metadata
                """,
                message.message_id,
                session_id,
                message.role,
                message.content,
                message.created_at,
                json.dumps([p.to_dict() for p in message.parts], ensure_ascii=False),
                json.dumps(message.metadata, ensure_ascii=False),
            )
            await conn.execute(
                "UPDATE sessions SET updated_at = NOW() WHERE session_id = $1",
                session_id,
            )
        logger.debug("message_saved", message_id=message.message_id, session_id=session_id)

    async def get_messages(
        self, session_id: str, limit: int = 100
    ) -> list[Message]:
        """按 ``created_at`` 升序返回指定会话的消息。

        Args:
            session_id: 所属会话 ID。
            limit: 最多返回数量。

        Returns:
            消息列表。
        """
        async with self._acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM messages
                WHERE session_id = $1
                ORDER BY created_at ASC
                LIMIT $2
                """,
                session_id,
                limit,
            )
        return [_record_to_message(row) for row in rows]


# Back-compat alias.
PostgresStorage = PostgresSessionRepository
