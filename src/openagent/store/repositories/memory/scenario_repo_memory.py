"""Memory Scenario Repository."""

from __future__ import annotations

from typing import Any

from openagent.store.models.scenario import Scenario
from openagent.store.repositories.memory._base import MemoryRepository
from openagent.store.repositories.scenario_repo import ScenarioRepository


class MemoryScenarioRepository(MemoryRepository[Scenario], ScenarioRepository):
    def __init__(self) -> None:
        super().__init__()

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[Scenario]:
        items = list(self._store.values())
        if not include_deleted:
            items = [s for s in items if not s.is_deleted]
        for k in ("code", "status", "source", "parent_id"):
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

    async def get_by_code_version(self, code: str, version: int) -> Scenario | None:
        for s in self._store.values():
            if s.code == code and s.version == version and not s.is_deleted:
                return s
        return None

    async def list_active(self, *, limit: int = 100) -> list[Scenario]:
        return await self.list(status="enabled", limit=limit)

    async def create_new_version(
        self, parent: Scenario, new_config: dict, new_name: str | None = None
    ) -> Scenario:
        new = Scenario(
            code=parent.code,
            name=new_name or parent.name,
            version=parent.version + 1,
            parent_id=parent.id,
            config=new_config,
            source=parent.source,
            status="draft",
        )
        return await self.create(new)
