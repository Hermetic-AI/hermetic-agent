"""MySQL Agent Repository — Tortoise ORM 实现."""
from __future__ import annotations

from typing import Any

from tortoise.expressions import Q

from hermetic_agent.store.models._common import utcnow
from hermetic_agent.store.models.agent import Agent
from hermetic_agent.store.repositories.agent_repo import AgentRepository


class MySQLAgentRepository(AgentRepository):
    """Agent 仓储 — Tortoise ORM (asyncmy) 实现."""

    async def get_by_id(self, agent_id: str) -> Agent | None:
        return await Agent.get_or_none(id=agent_id, is_deleted=False)

    async def get_by_code(self, code: str) -> Agent | None:
        return await Agent.get_or_none(code=code, is_deleted=False)

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[Agent]:
        qs = Agent.all()
        if not include_deleted:
            qs = qs.filter(is_deleted=False)
        for k in ("code", "status"):
            if k in filters and filters[k] is not None:
                qs = qs.filter(**{k: filters[k]})
        return await qs.order_by("-updated_at", "-id").offset(offset).limit(limit)

    async def count(
        self, *, include_deleted: bool = False, **filters: Any,
    ) -> int:
        qs = Agent.all()
        if not include_deleted:
            qs = qs.filter(is_deleted=False)
        for k in ("code", "status"):
            if k in filters and filters[k] is not None:
                qs = qs.filter(**{k: filters[k]})
        return await qs.count()

    async def create(self, agent: Agent) -> Agent:
        await agent.save()
        return agent

    async def update(self, agent_id: str, **fields: Any) -> Agent | None:
        if not fields:
            return await self.get_by_id(agent_id)
        await Agent.filter(id=agent_id).update(**fields, updated_at=utcnow())
        return await self.get_by_id(agent_id)

    async def soft_delete(self, agent_id: str) -> bool:
        rc = await Agent.filter(id=agent_id, is_deleted=False).update(
            is_deleted=True, deleted_at=utcnow(),
        )
        return rc > 0

    async def hard_delete(self, agent_id: str) -> bool:
        rc = await Agent.filter(id=agent_id).delete()
        return rc > 0

    async def list_visible_to(
        self,
        *,
        actor_user_id: str,
        limit: int = 50,
        offset: int = 0,
        code: str | None = None,
        status: str | None = None,
    ) -> list[Agent]:
        qs = Agent.filter(is_deleted=False).filter(
            Q(owner_user_id=actor_user_id) | Q(visibility="public")
        )
        if code is not None:
            qs = qs.filter(code=code)
        if status is not None:
            qs = qs.filter(status=status)
        return await qs.order_by("-updated_at", "-id").offset(offset).limit(limit)

    async def list_public(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        code: str | None = None,
    ) -> list[Agent]:
        qs = Agent.filter(is_deleted=False, visibility="public")
        if code is not None:
            qs = qs.filter(code=code)
        return await qs.order_by("-updated_at", "-id").offset(offset).limit(limit)

    async def set_visibility(
        self,
        agent_id: str,
        *,
        visibility: str,
        actor_user_id: str,
    ) -> Agent | None:
        if visibility not in ("private", "public"):
            raise ValueError("invalid visibility")
        rc = await Agent.filter(
            id=agent_id, is_deleted=False, owner_user_id=actor_user_id,
        ).update(visibility=visibility)
        if rc == 0:
            return None
        return await self.get_by_id(agent_id)


__all__ = ["MySQLAgentRepository"]
