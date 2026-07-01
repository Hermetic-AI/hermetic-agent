"""PromptService — Prompt 资产的业务编排.

业务规则:
- create: code 重复 -> DuplicateError
- update: 仅 owner 可改; 写 audit
- set_visibility: 委托 repo (owner 校验在 repo 内部, 非 owner 返 None)
- soft_delete: 写 audit
"""
from __future__ import annotations

import uuid

import structlog

from hermetic_agent.store.dto._common import ActorContext
from hermetic_agent.store.dto.prompt import (
    CreatePromptRequest,
    PromptResponse,
    UpdatePromptRequest,
)
from hermetic_agent.store.exceptions import DuplicateError, NotFoundError, PolicyError
from hermetic_agent.store.models.prompt import Prompt
from hermetic_agent.store.repositories.prompt_repo import PromptRepository
from hermetic_agent.store.services.audit_log_service import AuditLogService

logger = structlog.get_logger(__name__)


class PromptService:
    """Prompt 资产服务."""

    def __init__(self, repo: PromptRepository, audit: AuditLogService) -> None:
        self._repo = repo
        self._audit = audit

    async def get_by_id(self, prompt_id: str) -> Prompt:
        p = await self._repo.get_by_id(prompt_id)
        if p is None:
            raise NotFoundError("prompt", prompt_id)
        return p

    async def get_by_code(self, code: str) -> Prompt:
        p = await self._repo.get_by_code(code)
        if p is None:
            raise NotFoundError("prompt", code)
        return p

    async def list(
        self,
        *,
        actor: ActorContext,
        limit: int = 50,
        offset: int = 0,
        code: str | None = None,
        status: str | None = None,
    ) -> list[Prompt]:
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
    ) -> list[Prompt]:
        return await self._repo.list_public(limit=limit, offset=offset, code=code)

    async def create(
        self, req: CreatePromptRequest, *, actor: ActorContext,
    ) -> Prompt:
        existing = await self._repo.get_by_code(req.code)
        if existing is not None:
            raise DuplicateError(
                f"prompt {req.code} already exists: {existing.id}"
            )
        p = Prompt(
            id=uuid.uuid4(),
            code=req.code,
            name=req.name,
            version=req.version,
            description=req.description,
            content=req.content,
            owner_user_id=actor.user_id,
            visibility="private",
            status="enabled",
        )
        await self._repo.create(p)
        await self._audit.record(
            actor_type="user",
            actor_id=actor.user_id,
            action="create",
            resource_type="prompt",
            resource_id=str(p.id),
            after_data={"code": p.code, "name": p.name},
        )
        return p

    async def update(
        self,
        prompt_id: str,
        req: UpdatePromptRequest,
        *,
        actor: ActorContext,
    ) -> Prompt:
        p = await self.get_by_id(prompt_id)
        if p.owner_user_id != actor.user_id:
            raise PolicyError("FORBIDDEN", detail="non-owner cannot update prompt")
        fields: dict[str, object] = {}
        for field_name in ("name", "description", "content", "status"):
            val = getattr(req, field_name, None)
            if val is not None:
                fields[field_name] = val
        if not fields:
            return p
        before = {"name": p.name, "status": p.status}
        updated = await self._repo.update(prompt_id, **fields)
        if updated is None:
            raise NotFoundError("prompt", prompt_id)
        await self._audit.record(
            actor_type="user",
            actor_id=actor.user_id,
            action="update",
            resource_type="prompt",
            resource_id=prompt_id,
            before_data=before,
            after_data=fields,
        )
        return updated

    async def set_visibility(
        self, prompt_id: str, visibility: str, *, actor: ActorContext,
    ) -> Prompt | None:
        return await self._repo.set_visibility(
            prompt_id, visibility=visibility, actor_user_id=actor.user_id,
        )

    async def soft_delete(
        self, prompt_id: str, *, actor: ActorContext,
    ) -> None:
        p = await self.get_by_id(prompt_id)
        await self._repo.soft_delete(prompt_id)
        await self._audit.record(
            actor_type="user",
            actor_id=actor.user_id,
            action="delete",
            resource_type="prompt",
            resource_id=prompt_id,
            before_data={"code": p.code},
        )

    @staticmethod
    def to_response(p: Prompt) -> PromptResponse:
        return PromptResponse.from_model(p)


__all__ = ["PromptService"]
