"""Memory Agent Repository."""
from __future__ import annotations

from typing import Any

from hermetic_agent.store.models.agent import Agent
from hermetic_agent.store.repositories.agent_repo import AgentRepository
from hermetic_agent.store.repositories.memory._base import MemoryRepository


class MemoryAgentRepository(MemoryRepository[Agent], AgentRepository):
    """内存版 Agent 仓储 — 测试 + dev 用.

    ``get_by_id`` / ``create`` / ``update`` / ``soft_delete`` / ``hard_delete``
    全部继承自 :class:`MemoryRepository`, 内部统一把 key 规范成 ``str(id)``,
    保证 ``UUID`` / ``str`` / Tortoise ``Model.id`` 三种形态互查.
    """

    async def get_by_code(self, code: str) -> Agent | None:
        for a in self._store.values():
            if a.code == code and not a.is_deleted:
                return a
        return None

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[Agent]:
        items = list(self._store.values())
        if not include_deleted:
            items = [a for a in items if not a.is_deleted]
        for k in ("code", "status"):
            if k in filters and filters[k] is not None:
                items = [a for a in items if getattr(a, k) == filters[k]]
        items.sort(key=lambda a: (a.updated_at, a.id), reverse=True)
        return items[offset : offset + limit]

    async def count(
        self, *, include_deleted: bool = False, **filters: Any,
    ) -> int:
        items = list(self._store.values())
        if not include_deleted:
            items = [a for a in items if not a.is_deleted]
        for k in ("code", "status"):
            if k in filters and filters[k] is not None:
                items = [a for a in items if getattr(a, k) == filters[k]]
        return len(items)

    async def list_visible_to(
        self,
        *,
        actor_user_id: str,
        limit: int = 50,
        offset: int = 0,
        code: str | None = None,
        status: str | None = None,
    ) -> list[Agent]:
        items = [
            a for a in self._store.values()
            if not a.is_deleted and (
                a.owner_user_id == actor_user_id or a.visibility == "public"
            )
        ]
        if code is not None:
            items = [a for a in items if a.code == code]
        if status is not None:
            items = [a for a in items if a.status == status]
        items.sort(key=lambda a: (a.updated_at, a.id), reverse=True)
        return items[offset : offset + limit]

    async def list_public(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        code: str | None = None,
    ) -> list[Agent]:
        items = [
            a for a in self._store.values()
            if not a.is_deleted and a.visibility == "public"
        ]
        if code is not None:
            items = [a for a in items if a.code == code]
        items.sort(key=lambda a: (a.updated_at, a.id), reverse=True)
        return items[offset : offset + limit]

    async def set_visibility(
        self,
        agent_id: str,
        *,
        visibility: str,
        actor_user_id: str,
    ) -> Agent | None:
        if visibility not in ("private", "public"):
            raise ValueError("invalid visibility")
        target = str(agent_id) if agent_id is not None else agent_id
        a = None
        for k, m in self._store.items():
            if str(k) == target:
                a = m
                break
        if a is None or a.is_deleted:
            return None
        if a.owner_user_id != actor_user_id:
            return None
        a.visibility = visibility
        return a


__all__ = ["MemoryAgentRepository"]
