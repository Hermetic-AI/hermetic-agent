"""MySQL Scenario Repository — Tortoise ORM 实现."""
from __future__ import annotations

from typing import Any

from hermetic_agent.store.models.scenario import Scenario
from hermetic_agent.store.repositories.scenario_repo import ScenarioRepository


class MySQLScenarioRepository(ScenarioRepository):
    """场景仓储 — Tortoise ORM (asyncmy) 实现."""

    async def get_by_id(self, entity_id: str) -> Scenario | None:
        return await Scenario.get_or_none(id=entity_id, is_deleted=False)

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[Scenario]:
        qs = Scenario.all()
        if not include_deleted:
            qs = qs.filter(is_deleted=False)
        for k in ("code", "status", "source", "parent_id"):
            if k in filters and filters[k] is not None:
                qs = qs.filter(**{k: filters[k]})
        return await qs.order_by("-updated_at", "-id").offset(offset).limit(limit)

    async def count(
        self, *, include_deleted: bool = False, **filters: Any
    ) -> int:
        qs = Scenario.all()
        if not include_deleted:
            qs = qs.filter(is_deleted=False)
        for k in ("code", "status", "source", "parent_id"):
            if k in filters and filters[k] is not None:
                qs = qs.filter(**{k: filters[k]})
        return await qs.count()

    async def create(self, model: Scenario) -> Scenario:
        await model.save()
        return model

    async def update(self, entity_id: str, **fields: Any) -> Scenario | None:
        if not fields:
            return await self.get_by_id(entity_id)
        await Scenario.filter(id=entity_id).update(**fields)
        return await self.get_by_id(entity_id)

    async def soft_delete(self, entity_id: str) -> bool:
        from hermetic_agent.store.models._common import utcnow

        rc = await Scenario.filter(id=entity_id, is_deleted=False).update(
            is_deleted=True, deleted_at=utcnow(),
        )
        return rc > 0

    async def hard_delete(self, entity_id: str) -> bool:
        rc = await Scenario.filter(id=entity_id).delete()
        return rc > 0

    async def get_by_code_version(self, code: str, version: int) -> Scenario | None:
        return await Scenario.get_or_none(
            code=code, version=version, is_deleted=False,
        )

    async def list_active(self, *, limit: int = 100) -> list[Scenario]:
        return await self.list(status="enabled", limit=limit)

    async def create_new_version(
        self, parent: Scenario, new_config: dict[str, Any], new_name: str | None = None
    ) -> Scenario:
        """基于父版本创建新版本(同 code, version+1, parent_id 指向父)."""
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


__all__ = ["MySQLScenarioRepository"]
