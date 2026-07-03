"""Memory Prompt Repository."""
from __future__ import annotations

from typing import Any

from hermetic_agent.store.models.prompt import Prompt
from hermetic_agent.store.repositories.memory._base import MemoryRepository
from hermetic_agent.store.repositories.prompt_repo import PromptRepository


class MemoryPromptRepository(MemoryRepository[Prompt], PromptRepository):
    """内存版 Prompt 仓储 — 测试 + dev 用.

    ``get_by_id`` / ``create`` / ``update`` / ``soft_delete`` / ``hard_delete``
    全部继承自 :class:`MemoryRepository`, 内部统一把 key 规范成 ``str(id)``,
    保证 ``UUID`` / ``str`` / Tortoise ``Model.id`` 三种形态互查.
    """

    async def get_by_code(self, code: str) -> Prompt | None:
        for p in self._store.values():
            if p.code == code and not p.is_deleted:
                return p
        return None

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[Prompt]:
        items = list(self._store.values())
        if not include_deleted:
            items = [p for p in items if not p.is_deleted]
        for k in ("code", "status"):
            if k in filters and filters[k] is not None:
                items = [p for p in items if getattr(p, k) == filters[k]]
        items.sort(key=lambda p: (p.updated_at, p.id), reverse=True)
        return items[offset : offset + limit]

    async def count(
        self, *, include_deleted: bool = False, **filters: Any,
    ) -> int:
        items = list(self._store.values())
        if not include_deleted:
            items = [p for p in items if not p.is_deleted]
        for k in ("code", "status"):
            if k in filters and filters[k] is not None:
                items = [p for p in items if getattr(p, k) == filters[k]]
        return len(items)

    async def list_visible_to(
        self,
        *,
        actor_user_id: str,
        limit: int = 50,
        offset: int = 0,
        code: str | None = None,
        status: str | None = None,
    ) -> list[Prompt]:
        items = [
            p for p in self._store.values()
            if not p.is_deleted and (
                p.owner_user_id == actor_user_id or p.visibility == "public"
            )
        ]
        if code is not None:
            items = [p for p in items if p.code == code]
        if status is not None:
            items = [p for p in items if p.status == status]
        items.sort(key=lambda p: (p.updated_at, p.id), reverse=True)
        return items[offset : offset + limit]

    async def list_public(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        code: str | None = None,
    ) -> list[Prompt]:
        items = [
            p for p in self._store.values()
            if not p.is_deleted and p.visibility == "public"
        ]
        if code is not None:
            items = [p for p in items if p.code == code]
        items.sort(key=lambda p: (p.updated_at, p.id), reverse=True)
        return items[offset : offset + limit]

    async def set_visibility(
        self,
        prompt_id: str,
        *,
        visibility: str,
        actor_user_id: str,
    ) -> Prompt | None:
        if visibility not in ("private", "public"):
            raise ValueError("invalid visibility")
        target = str(prompt_id) if prompt_id is not None else prompt_id
        p = None
        for k, m in self._store.items():
            if str(k) == target:
                p = m
                break
        if p is None or p.is_deleted:
            return None
        if p.owner_user_id != actor_user_id:
            return None
        p.visibility = visibility
        return p


__all__ = ["MemoryPromptRepository"]
