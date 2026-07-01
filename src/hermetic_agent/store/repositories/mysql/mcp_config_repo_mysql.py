"""MySQL MCP Config Repository — Tortoise ORM 实现."""

from __future__ import annotations

from typing import Any

from tortoise.expressions import Q

from hermetic_agent.store.models.mcp_config import McpConfig
from hermetic_agent.store.repositories.mcp_config_repo import McpConfigRepository


class MySQLMcpConfigRepository(McpConfigRepository):
    """MCP 配置仓储 — Tortoise ORM (asyncmy) 实现."""

    async def get_by_id(self, entity_id: str) -> McpConfig | None:
        return await McpConfig.get_or_none(id=entity_id, is_deleted=False)

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[McpConfig]:
        qs = McpConfig.all()
        if not include_deleted:
            qs = qs.filter(is_deleted=False)
        for k in ("code", "status", "source", "mcp_type"):
            if k in filters and filters[k] is not None:
                qs = qs.filter(**{k: filters[k]})
        return await qs.order_by("-updated_at", "-id").offset(offset).limit(limit)

    async def count(
        self, *, include_deleted: bool = False, **filters: Any
    ) -> int:
        qs = McpConfig.all()
        if not include_deleted:
            qs = qs.filter(is_deleted=False)
        for k in ("code", "status", "source"):
            if k in filters and filters[k] is not None:
                qs = qs.filter(**{k: filters[k]})
        return await qs.count()

    async def create(self, model: McpConfig) -> McpConfig:
        await model.save()
        return model

    async def update(self, entity_id: str, **fields: Any) -> McpConfig | None:
        if not fields:
            return await self.get_by_id(entity_id)
        await McpConfig.filter(id=entity_id).update(**fields)
        return await self.get_by_id(entity_id)

    async def soft_delete(self, entity_id: str) -> bool:
        from hermetic_agent.store.models._common import utcnow

        rc = await McpConfig.filter(id=entity_id, is_deleted=False).update(
            is_deleted=True, deleted_at=utcnow(),
        )
        return rc > 0

    async def hard_delete(self, entity_id: str) -> bool:
        rc = await McpConfig.filter(id=entity_id).delete()
        return rc > 0

    async def get_by_code(self, code: str) -> McpConfig | None:
        return await McpConfig.get_or_none(code=code, is_deleted=False)

    async def list_active(self, *, limit: int = 100) -> list[McpConfig]:
        return await McpConfig.filter(
            is_deleted=False, status="enabled", disabled=False,
        ).order_by("-updated_at", "-id").limit(limit)

    async def list_visible_to(
        self,
        *,
        actor_user_id: str,
        limit: int = 50,
        offset: int = 0,
        code: str | None = None,
        status: str | None = None,
    ) -> list[McpConfig]:
        qs = McpConfig.filter(is_deleted=False).filter(
            Q(owner_user_id=actor_user_id) | Q(visibility="public")
        )
        if code is not None:
            qs = qs.filter(code=code)
        if status is not None:
            qs = qs.filter(status=status)
        return await qs.order_by("code").offset(offset).limit(limit)

    async def list_public(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        code: str | None = None,
    ) -> list[McpConfig]:
        qs = McpConfig.filter(is_deleted=False, visibility="public")
        if code is not None:
            qs = qs.filter(code=code)
        return await qs.order_by("code").offset(offset).limit(limit)

    async def set_visibility(
        self,
        config_id: str,
        *,
        visibility: str,
        actor_user_id: str,
    ) -> McpConfig | None:
        if visibility not in ("private", "public"):
            raise ValueError("invalid visibility")
        rc = await McpConfig.filter(
            id=config_id, is_deleted=False, owner_user_id=actor_user_id,
        ).update(visibility=visibility)
        return (await self.get_by_id(config_id)) if rc else None


__all__ = ["MySQLMcpConfigRepository"]
