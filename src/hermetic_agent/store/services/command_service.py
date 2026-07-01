"""CommandService — Command 资产的业务编排.

业务规则:
- create: code 重复或 slash_command 重复 -> DuplicateError
- update: 仅 owner 可改; 写 audit
- set_visibility: 委托 repo (非 owner 返 None)
- soft_delete: 写 audit
"""
from __future__ import annotations

import uuid

import structlog

from hermetic_agent.store.dto._common import ActorContext
from hermetic_agent.store.dto.command import (
    CommandResponse,
    CreateCommandRequest,
    UpdateCommandRequest,
)
from hermetic_agent.store.exceptions import DuplicateError, NotFoundError, PolicyError
from hermetic_agent.store.models.command import Command
from hermetic_agent.store.repositories.command_repo import CommandRepository
from hermetic_agent.store.services.audit_log_service import AuditLogService

logger = structlog.get_logger(__name__)


class CommandService:
    """Command 资产服务."""

    def __init__(self, repo: CommandRepository, audit: AuditLogService) -> None:
        self._repo = repo
        self._audit = audit

    async def get_by_id(self, command_id: str) -> Command:
        c = await self._repo.get_by_id(command_id)
        if c is None:
            raise NotFoundError("command", command_id)
        return c

    async def get_by_code(self, code: str) -> Command:
        c = await self._repo.get_by_code(code)
        if c is None:
            raise NotFoundError("command", code)
        return c

    async def get_by_slash(self, slash_command: str) -> Command:
        c = await self._repo.get_by_slash(slash_command)
        if c is None:
            raise NotFoundError("command_slash", slash_command)
        return c

    async def list(
        self,
        *,
        actor: ActorContext,
        limit: int = 50,
        offset: int = 0,
        code: str | None = None,
        status: str | None = None,
    ) -> list[Command]:
        return await self._repo.list_visible_to(
            actor_user_id=actor.user_id,
            limit=limit,
            offset=offset,
            code=code,
            status=status,
        )

    async def list_public(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        code: str | None = None,
    ) -> list[Command]:
        return await self._repo.list_public(limit=limit, offset=offset, code=code)

    async def create(
        self, req: CreateCommandRequest, *, actor: ActorContext,
    ) -> Command:
        existing_code = await self._repo.get_by_code(req.code)
        if existing_code is not None:
            raise DuplicateError(
                f"command {req.code} already exists: {existing_code.id}"
            )
        existing_slash = await self._repo.get_by_slash(req.slash_command)
        if existing_slash is not None:
            raise DuplicateError(
                f"slash {req.slash_command} already exists: {existing_slash.id}"
            )
        c = Command(
            id=uuid.uuid4(),
            code=req.code,
            name=req.name,
            description=req.description,
            slash_command=req.slash_command,
            system_prompt_addendum=req.system_prompt_addendum,
            enabled=True,
            owner_user_id=actor.user_id,
            visibility="private",
            status="enabled",
        )
        await self._repo.create(c)
        await self._audit.record(
            actor_type="user",
            actor_id=actor.user_id,
            action="create",
            resource_type="command",
            resource_id=str(c.id),
            after_data={"code": c.code, "slash_command": c.slash_command},
        )
        return c

    async def update(
        self,
        command_id: str,
        req: UpdateCommandRequest,
        *,
        actor: ActorContext,
    ) -> Command:
        c = await self.get_by_id(command_id)
        if c.owner_user_id != actor.user_id:
            raise PolicyError("FORBIDDEN", detail="non-owner cannot update command")
        fields: dict[str, object] = {}
        for field_name in (
            "name", "description", "slash_command",
            "system_prompt_addendum", "enabled", "status",
        ):
            val = getattr(req, field_name, None)
            if val is not None:
                fields[field_name] = val
        if not fields:
            return c
        before = {"name": c.name, "status": c.status}
        updated = await self._repo.update(command_id, **fields)
        if updated is None:
            raise NotFoundError("command", command_id)
        await self._audit.record(
            actor_type="user",
            actor_id=actor.user_id,
            action="update",
            resource_type="command",
            resource_id=command_id,
            before_data=before,
            after_data=fields,
        )
        return updated

    async def set_visibility(
        self, command_id: str, visibility: str, *, actor: ActorContext,
    ) -> Command | None:
        return await self._repo.set_visibility(
            command_id, visibility=visibility, actor_user_id=actor.user_id,
        )

    async def soft_delete(
        self, command_id: str, *, actor: ActorContext,
    ) -> None:
        c = await self.get_by_id(command_id)
        await self._repo.soft_delete(command_id)
        await self._audit.record(
            actor_type="user",
            actor_id=actor.user_id,
            action="delete",
            resource_type="command",
            resource_id=command_id,
            before_data={"code": c.code},
        )

    @staticmethod
    def to_response(c: Command) -> CommandResponse:
        return CommandResponse.from_model(c)


__all__ = ["CommandService"]
