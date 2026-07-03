"""Memory Command Repository."""
from __future__ import annotations

from typing import Any

from hermetic_agent.store.models.command import Command
from hermetic_agent.store.repositories.command_repo import CommandRepository
from hermetic_agent.store.repositories.memory._base import MemoryRepository


class MemoryCommandRepository(MemoryRepository[Command], CommandRepository):
    """内存版 Command 仓储 — 测试 + dev 用.

    ``get_by_id`` / ``create`` / ``update`` / ``soft_delete`` / ``hard_delete``
    全部继承自 :class:`MemoryRepository`, 内部统一把 key 规范成 ``str(id)``,
    保证 ``UUID`` / ``str`` / Tortoise ``Model.id`` 三种形态互查.
    """

    async def get_by_code(self, code: str) -> Command | None:
        for c in self._store.values():
            if c.code == code and not c.is_deleted:
                return c
        return None

    async def get_by_slash(self, slash_command: str) -> Command | None:
        """按 slash 字符串 (例 ``/summarize``) 查 Command. 用户输入路由时用."""
        for c in self._store.values():
            if c.slash_command == slash_command and not c.is_deleted:
                return c
        return None

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[Command]:
        items = list(self._store.values())
        if not include_deleted:
            items = [c for c in items if not c.is_deleted]
        for k in ("code", "status"):
            if k in filters and filters[k] is not None:
                items = [c for c in items if getattr(c, k) == filters[k]]
        items.sort(key=lambda c: (c.updated_at, c.id), reverse=True)
        return items[offset : offset + limit]

    async def count(
        self, *, include_deleted: bool = False, **filters: Any,
    ) -> int:
        items = list(self._store.values())
        if not include_deleted:
            items = [c for c in items if not c.is_deleted]
        for k in ("code", "status"):
            if k in filters and filters[k] is not None:
                items = [c for c in items if getattr(c, k) == filters[k]]
        return len(items)

    async def list_visible_to(
        self,
        *,
        actor_user_id: str,
        limit: int = 50,
        offset: int = 0,
        code: str | None = None,
        status: str | None = None,
    ) -> list[Command]:
        items = [
            c for c in self._store.values()
            if not c.is_deleted and (
                c.owner_user_id == actor_user_id or c.visibility == "public"
            )
        ]
        if code is not None:
            items = [c for c in items if c.code == code]
        if status is not None:
            items = [c for c in items if c.status == status]
        items.sort(key=lambda c: (c.updated_at, c.id), reverse=True)
        return items[offset : offset + limit]

    async def list_public(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        code: str | None = None,
    ) -> list[Command]:
        items = [
            c for c in self._store.values()
            if not c.is_deleted and c.visibility == "public"
        ]
        if code is not None:
            items = [c for c in items if c.code == code]
        items.sort(key=lambda c: (c.updated_at, c.id), reverse=True)
        return items[offset : offset + limit]

    async def set_visibility(
        self,
        command_id: str,
        *,
        visibility: str,
        actor_user_id: str,
    ) -> Command | None:
        if visibility not in ("private", "public"):
            raise ValueError("invalid visibility")
        target = str(command_id) if command_id is not None else command_id
        c = None
        for k, m in self._store.items():
            if str(k) == target:
                c = m
                break
        if c is None or c.is_deleted:
            return None
        if c.owner_user_id != actor_user_id:
            return None
        c.visibility = visibility
        return c


__all__ = ["MemoryCommandRepository"]
