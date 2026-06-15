"""MessageRepository ABC — 消息仓储接口."""

from __future__ import annotations

from abc import abstractmethod

from openagent.store.models.message import Message
from openagent.store.repositories._base import Repository


class MessageRepository(Repository[Message]):
    """消息仓储接口."""

    @abstractmethod
    async def list_by_session(
        self,
        session_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> list[Message]:
        """按 session 列消息(按 created_at ASC)."""

    @abstractmethod
    async def list_by_turn(self, turn_id: str) -> list[Message]:
        """按 turn 列消息(通常 2 条: user + assistant)."""


__all__ = ["MessageRepository"]
