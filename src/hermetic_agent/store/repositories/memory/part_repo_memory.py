"""Memory Part Repository."""

from __future__ import annotations

from typing import Any

from hermetic_agent.store.models.part import Part
from hermetic_agent.store.repositories.memory._base import MemoryRepository
from hermetic_agent.store.repositories.part_repo import PartRepository


class MemoryPartRepository(MemoryRepository[Part], PartRepository):
    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[Part]:
        # ID 兼容: ``message_id`` / ``session_id`` 是 FK column, Tortoise 存 UUID
        # 对象; 业务方传 str. 两边 ``str()`` 化对比, 跟生产 MySQL 路径一致.
        items = list(self._store.values())
        if not include_deleted:
            items = [s for s in items if not s.is_deleted]
        for k in ("message_id", "session_id", "part_type"):
            if k in filters and filters[k] is not None:
                target = str(filters[k]) if k in ("message_id", "session_id") else filters[k]
                items = [s for s in items if str(getattr(s, k)) == target]
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
                target = str(filters[k]) if k in ("message_id", "session_id") else filters[k]
                items = [s for s in items if str(getattr(s, k)) == target]
        return len(items)

    async def list_by_message(
        self, message_id: str, *, include_deleted: bool = False
    ) -> list[Part]:
        # ID 兼容: Tortoise ``Part.message_id`` (FK column) 是 ``UUID`` 对象,
        # 但业务方传进来的是 ``str``. 两边 ``str()`` 化对比, 跟生产 MySQL 路径一致.
        target = str(message_id)
        items = list(self._store.values())
        if not include_deleted:
            items = [s for s in items if not s.is_deleted]
        items = [s for s in items if str(s.message_id) == target]
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
