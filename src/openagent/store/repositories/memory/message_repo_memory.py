"""Memory Message Repository."""

from __future__ import annotations

from typing import Any

from openagent.store.models.message import Message
from openagent.store.repositories.memory._base import MemoryRepository
from openagent.store.repositories.message_repo import MessageRepository


class MemoryMessageRepository(MemoryRepository[Message], MessageRepository):
    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[Message]:
        # ID 兼容: ``session_id`` / ``turn_id`` 是 FK column, Tortoise 存 UUID
        # 对象; 业务方传 str. 两边 ``str()`` 化对比.
        items = list(self._store.values())
        if not include_deleted:
            items = [s for s in items if not s.is_deleted]
        for k in ("session_id", "turn_id", "role"):
            if k in filters and filters[k] is not None:
                target = str(filters[k]) if k in ("session_id", "turn_id") else filters[k]
                items = [s for s in items if str(getattr(s, k)) == target]
        items.sort(key=lambda s: (s.created_at, s.id))
        return items[offset : offset + limit]

    async def count(
        self, *, include_deleted: bool = False, **filters: Any
    ) -> int:
        items = list(self._store.values())
        if not include_deleted:
            items = [s for s in items if not s.is_deleted]
        for k in ("session_id", "turn_id", "role"):
            if k in filters and filters[k] is not None:
                target = str(filters[k]) if k in ("session_id", "turn_id") else filters[k]
                items = [s for s in items if str(getattr(s, k)) == target]
        return len(items)

    async def list_by_session(
        self,
        session_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> list[Message]:
        return await self.list(
            session_id=session_id, limit=limit, offset=offset, include_deleted=include_deleted
        )

    async def list_by_turn(self, turn_id: str) -> list[Message]:
        return await self.list(turn_id=turn_id, limit=10)
