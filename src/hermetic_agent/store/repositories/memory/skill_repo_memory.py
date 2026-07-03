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

    async def list_visible_to(
        self,
        *,
        actor_user_id: str,
        limit: int = 50,
        offset: int = 0,
        code: str | None = None,
        status: str | None = None,
    ) -> list[Skill]:
        items = [
            s for s in self._store.values()
            if not s.is_deleted and (
                s.owner_user_id == actor_user_id or s.visibility == "public"
            )
        ]
        if code is not None:
            items = [s for s in items if s.code == code]
        if status is not None:
            items = [s for s in items if s.status == status]
        items.sort(key=lambda s: (s.updated_at, s.id), reverse=True)
        return items[offset : offset + limit]

    async def list_public(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        code: str | None = None,
    ) -> list[Skill]:
        items = [
            s for s in self._store.values()
            if not s.is_deleted and s.visibility == "public"
        ]
        if code is not None:
            items = [s for s in items if s.code == code]
        items.sort(key=lambda s: (s.updated_at, s.id), reverse=True)
        return items[offset : offset + limit]

    async def update_file_fingerprint(
        self,
        skill_id: str,
        *,
        file_count: int,
        file_fingerprint: str,
    ) -> Skill | None:
        s = self._find(skill_id)
        if s is None or s.is_deleted:
            return None
        s.file_count = file_count
        s.file_fingerprint = file_fingerprint
        return s

    async def set_visibility(
        self,
        skill_id: str,
        *,
        visibility: str,
        actor_user_id: str,
    ) -> Skill | None:
        if visibility not in ("private", "public"):
            raise ValueError("invalid visibility")
        s = self._find(skill_id)
        if s is None or s.is_deleted:
            return None
        if s.owner_user_id != actor_user_id:
            return None
        s.visibility = visibility
        return s

    def _find(self, skill_id: str) -> Skill | None:
        """按 ID 查找, 同时兼容 str / UUID key (跟 MemoryRepository.get_by_id 一致)."""
        target = str(skill_id) if skill_id is not None else skill_id
        for k, m in self._store.items():
            if str(k) == target:
                return m
        return None


__all__ = ["MemorySkillRepository"]
