"""基于字典的内存版 ``SessionRepository``，用于开发与测试环境。"""

from __future__ import annotations

from datetime import datetime

import structlog

from .base import Message, Session, SessionRepository

logger = structlog.get_logger(__name__)


class MemorySessionRepository(SessionRepository):
    """内存版会话仓储，提供基于 dict 的回退实现。

    该后端适用于开发、测试或没有持久化存储的环境。
    """

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._messages: dict[str, list[Message]] = {}
        logger.info("memory_storage_initialized")

    # Match app.py startup contract (connect / init_schema / close)
    async def connect(self) -> None:
        """初始化连接；内存版无操作。"""
        pass

    async def init_schema(self) -> None:
        """初始化表结构；内存版无操作。"""
        pass

    async def close(self) -> None:
        """清空全部内存数据，释放资源。"""
        self._sessions.clear()
        self._messages.clear()

    async def save_session(self, session: Session) -> None:
        """创建或覆盖一个会话；首次写入时初始化消息列表。

        Args:
            session: 完整会话对象。
        """
        self._sessions[session.session_id] = session
        if session.session_id not in self._messages:
            self._messages[session.session_id] = []
        logger.debug("session_saved", session_id=session.session_id)

    # Alias used by SDK adapters when persisting newly-created sessions
    create_session = save_session

    async def get_session(self, session_id: str) -> Session | None:
        """按 ID 获取会话。

        Args:
            session_id: 会话 ID。

        Returns:
            找到时返回 ``Session``，否则 ``None``。
        """
        session = self._sessions.get(session_id)
        if session is None:
            logger.debug("session_not_found", session_id=session_id)
            return None
        logger.debug("session_retrieved", session_id=session_id)
        return session

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
        sessions = list(self._sessions.values())
        if user_id is not None:
            sessions = [s for s in sessions if s.user_id == user_id]
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        result = sessions[:limit]
        logger.debug(
            "sessions_listed",
            count=len(result),
            user_id=user_id,
            limit=limit,
        )
        return result

    async def delete_session(self, session_id: str) -> bool:
        """删除会话及其消息。

        Args:
            session_id: 会话 ID。

        Returns:
            ``True`` 表示确实存在并已删除，``False`` 表示原本就不存在。
        """
        existed = session_id in self._sessions
        if existed:
            del self._sessions[session_id]
        if session_id in self._messages:
            del self._messages[session_id]
        logger.debug("session_deleted", session_id=session_id, success=existed)
        return existed

    async def save_message(self, session_id: str, message: Message) -> None:
        """创建或更新一条消息，并刷新所属会话的 ``updated_at``。

        Args:
            session_id: 所属会话 ID。
            message: 消息对象。
        """
        if session_id not in self._messages:
            self._messages[session_id] = []
        existing_ids = {m.message_id for m in self._messages[session_id]}
        if message.message_id in existing_ids:
            self._messages[session_id] = [
                m if m.message_id != message.message_id else message
                for m in self._messages[session_id]
            ]
        else:
            self._messages[session_id].append(message)
        if session_id in self._sessions:
            self._sessions[session_id].updated_at = datetime.utcnow()
        logger.debug(
            "message_saved",
            message_id=message.message_id,
            session_id=session_id,
        )

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
        messages = self._messages.get(session_id, [])
        messages.sort(key=lambda m: m.created_at)
        result = messages[:limit]
        logger.debug(
            "messages_retrieved",
            session_id=session_id,
            count=len(result),
            limit=limit,
        )
        return result

    def clear(self) -> None:
        """清空所有存储的会话与消息，主要用于测试。"""
        self._sessions.clear()
        self._messages.clear()
        logger.info("memory_storage_cleared")

    def __len__(self) -> int:
        """返回当前存储的会话总数。"""
        return len(self._sessions)


# Back-compat alias.
MemoryStorage = MemorySessionRepository
