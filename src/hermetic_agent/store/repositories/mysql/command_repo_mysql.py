"""MySQL Command Repository — Tortoise ORM 实现."""
from __future__ import annotations

from typing import Any

from tortoise.expressions import Q

from hermetic_agent.store.models._common import utcnow
from hermetic_agent.store.models.command import Command
from hermetic_agent.store.repositories.command_repo import CommandRepository


class MySQLCommandRepository(CommandRepository):
    """Command 仓储 — Tortoise ORM (asyncmy) 实现."""

    async def get_by_id(self, command_id: str) -> Command | None:
        return await Command.get_or_none(id=command_id, is_deleted=False)

    async def get_by_code(self, code: str) -> Command | None:
        return await Command.get_or_none(code=code, is_deleted=False)

    async def get_by_slash(self, slash_command: str) -> Command | None:
        """按 slash 字符串 (例 ``/summarize``) 查 Command, 走 ``slash_command`` 索引."""
        return await Command.get_or_none(
            slash_command=slash_command, is_deleted=False,
        )

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[Command]:
        qs = Command.all()
        if not include_deleted:
            qs = qs.filter(is_deleted=False)
        for k in ("code", "status"):
            if k in filters and filters[k] is not None:
                qs = qs.filter(**{k: filters[k]})
        return await qs.order_by("-updated_at", "-id").offset(offset).limit(limit)

    async def count(
        self, *, include_deleted: bool = False, **filters: Any,
    ) -> int:
        qs = Command.all()
        if not include_deleted:
            qs = qs.filter(is_deleted=False)
        for k in ("code", "status"):
            if k in filters and filters[k] is not None:
                qs = qs.filter(**{k: filters[k]})
        return await qs.count()

    async def create(self, command: Command) -> Command:
        await command.save()
        return command

    async def update(self, command_id: str, **fields: Any) -> Command | None:
        # Tortoise ``auto_now=True`` 只在 ``Model.save()`` 触发, ``.update()`` 不会.
        # 显式 stamp updated_at, 跟 Memory 路径行为一致.
        if not fields:
            return await self.get_by_id(command_id)
        await Command.filter(id=command_id).update(**fields, updated_at=utcnow())
        return await self.get_by_id(command_id)

    async def soft_delete(self, command_id: str) -> bool:
        rc = await Command.filter(id=command_id, is_deleted=False).update(
            is_deleted=True, deleted_at=utcnow(),
        )
        return rc > 0

    async def hard_delete(self, command_id: str) -> bool:
        rc = await Command.filter(id=command_id).delete()
        return rc > 0

    async def list_visible_to(
        self,
        *,
        actor_user_id: str,
        limit: int = 50,
        offset: int = 0,
        code: str | None = None,
        status: str | None = None,
    ) -> list[Command]:
        qs = Command.filter(is_deleted=False).filter(
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
    ) -> list[Command]:
        qs = Command.filter(is_deleted=False, visibility="public")
        if code is not None:
            qs = qs.filter(code=code)
        return await qs.order_by("-updated_at", "-id").offset(offset).limit(limit)

    async def set_visibility(
        self,
        command_id: str,
        *,
        visibility: str,
        actor_user_id: str,
    ) -> Command | None:
        if visibility not in ("private", "public"):
            raise ValueError("invalid visibility")
        rc = await Command.filter(
            id=command_id, is_deleted=False, owner_user_id=actor_user_id,
        ).update(visibility=visibility)
        if rc == 0:
            return None
        return await self.get_by_id(command_id)


__all__ = ["MySQLCommandRepository"]
