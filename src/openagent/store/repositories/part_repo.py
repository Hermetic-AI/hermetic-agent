"""PartRepository ABC — 消息分段仓储接口."""

from __future__ import annotations

from abc import abstractmethod

from openagent.store.models.part import Part
from openagent.store.repositories._base import Repository


class PartRepository(Repository[Part]):
    """消息分段仓储接口.

    注意: parts 有 session_id 冗余, 按 session 查不需要 JOIN messages.
    """

    @abstractmethod
    async def list_by_message(
        self, message_id: str, *, include_deleted: bool = False
    ) -> list[Part]:
        """按 message 列 part(按 position ASC)."""

    @abstractmethod
    async def list_by_session(
        self,
        session_id: str,
        *,
        limit: int = 200,
        offset: int = 0,
        part_type: str | None = None,
    ) -> list[Part]:
        """按 session 列 part(按 created_at ASC), 可选按 type 过滤."""

    @abstractmethod
    async def batch_create(self, parts: list[Part]) -> list[Part]:
        """批量插入(同 message 的多个 part, 一次往返)."""


__all__ = ["PartRepository"]
