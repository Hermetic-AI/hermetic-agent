"""Memory Scenario Repository."""

from __future__ import annotations

from typing import Any

from hermetic_agent.store.models.scenario import Scenario
from hermetic_agent.store.repositories.memory._base import MemoryRepository
from hermetic_agent.store.repositories.scenario_repo import ScenarioRepository


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
        self, parent, new_config: dict, new_name: str | None = None
    ) -> Scenario:
        """基于父版本创建新版本. ``parent`` 可传 ``Scenario`` 对象或 parent id 字符串.

        兼容老调用方 ``create_new_version(parent_id_str, ...)`` — 内部自动 fetch.

        注意: Tortoise 的 ``Model.__init__`` 不会处理 FK 列名 (``parent_id``),
        只处理 FK 关系名 (``parent``). 所以这里构造完 Model 后显式 ``setattr``
        设 ``parent_id``, 让 ``new.parent_id`` 可访问 (测试 / DTO 转换都靠这个).
        """
        if not isinstance(parent, Scenario):
            fetched = await self.get_by_id(str(parent))
            if fetched is None:
                raise ValueError(f"parent scenario not found: {parent}")
            parent = fetched
        new = Scenario(
            code=parent.code,
            name=new_name or parent.name,
            version=parent.version + 1,
            config=new_config,
            source=parent.source,
            status="draft",
        )
        new.parent_id = parent.id
        return await self.create(new)
