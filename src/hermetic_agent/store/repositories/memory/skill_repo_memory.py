"""Memory Skill Repository."""

from __future__ import annotations

from typing import Any

from hermetic_agent.store.models.skill import Skill
from hermetic_agent.store.repositories.memory._base import MemoryRepository
from hermetic_agent.store.repositories.skill_repo import SkillRepository


class MemorySkillRepository(MemoryRepository[Skill], SkillRepository):
    def __init__(self) -> None:
        super().__init__()

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[Skill]:
        items = list(self._store.values())
        if not include_deleted:
            items = [s for s in items if not s.is_deleted]
        for k in ("code", "status", "source"):
            if k in filters and filters[k] is not None:
                items = [s for s in items if getattr(s, k) == filters[k]]
        items.sort(key=lambda s: (s.updated_at, s.id), reverse=True)
        return items[offset : offset + limit]

    async def count(
        self, *, include_deleted: bool = False, **filters: Any
    ) -> int:
        items = list(self._store.values())
        if not include_deleted:
            items = [s for s in items if not s.is_deleted]
        for k in ("code", "status"):
            if k in filters and filters[k] is not None:
                items = [s for s in items if getattr(s, k) == filters[k]]
        return len(items)

    async def get_by_code(self, code: str) -> Skill | None:
        for s in self._store.values():
            if s.code == code and not s.is_deleted:
                return s
        return None

    async def list_active(self, *, limit: int = 100) -> list[Skill]:
        return await self.list(status="enabled", limit=limit)


__all__ = ["MemorySkillRepository"]
