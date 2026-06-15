"""Memory Part Repository."""

from __future__ import annotations

from typing import Any

from openagent.store.models.part import Part
from openagent.store.repositories.memory._base import MemoryRepository
from openagent.store.repositories.part_repo import PartRepository


class MemoryPartRepository(MemoryRepository[Part], PartRepository):
    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[Part]:
        items = list(self._store.values())
        if not include_deleted:
            items = [s for s in items if not s.is_deleted]
        for k in ("message_id", "session_id", "part_type"):
            if k in filters and filters[k] is not None:
                items = [s for s in items if getattr(s, k) == filters[k]]
        items.sort(key=lambda s: (s.created_at, s.id))
        return items[offset : offset + limit]

    async def count(
        self, *, include_deleted: bool = False, **filters: Any
    ) -> int:
        items = list(self._store.values())
        if not include_deleted:
            items = [s for s in items if not s.is_deleted]
        for k in ("message_id", "session_id", "part_type"):
            if k in filters and filters[k] is not None:
                items = [s for s in items if getattr(s, k) == filters[k]]
        return len(items)

    async def list_by_message(
        self, message_id: str, *, include_deleted: bool = False
    ) -> list[Part]:
        items = list(self._store.values())
        if not include_deleted:
            items = [s for s in items if not s.is_deleted]
        items = [s for s in items if s.message_id == message_id]
        items.sort(key=lambda s: (s.position, s.id))
        return items

    async def list_by_session(
        self,
        session_id: str,
        *,
        limit: int = 200,
        offset: int = 0,
        part_type: str | None = None,
    ) -> list[Part]:
        return await self.list(
            session_id=session_id, part_type=part_type, limit=limit, offset=offset
        )

    async def batch_create(self, parts: list[Part]) -> list[Part]:
        for p in parts:
            await self.create(p)
        return parts
