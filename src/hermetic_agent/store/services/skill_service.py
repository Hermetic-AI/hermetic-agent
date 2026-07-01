"""SkillService — 技能定义/快照的业务编排."""

from __future__ import annotations

from typing import Any

import structlog

from hermetic_agent.store.dto._common import ActorContext
from hermetic_agent.store.dto.skill import (
    CreateSkillRequest,
    SkillResponse,
    UpdateSkillRequest,
)
from hermetic_agent.store.exceptions import DuplicateError, NotFoundError
from hermetic_agent.store.models.skill import Skill
from hermetic_agent.store.repositories.skill_repo import SkillRepository
from hermetic_agent.store.services.audit_log_service import AuditLogService

logger = structlog.get_logger(__name__)


class SkillService:
    """技能服务."""

    def __init__(
        self,
        repo: SkillRepository,
        audit: AuditLogService,
    ) -> None:
        self._repo = repo
        self._audit = audit

    async def get_by_id(self, skill_id: str) -> Skill:
        s = await self._repo.get_by_id(skill_id)
        if s is None:
            raise NotFoundError("skill", skill_id)
        return s

    async def get_by_code(self, code: str) -> Skill:
        s = await self._repo.get_by_code(code)
        if s is None:
            raise NotFoundError("skill", code)
        return s

    async def list_active(self, *, limit: int = 100) -> list[Skill]:
        return await self._repo.list_active(limit=limit)

    async def create(
        self,
        req: CreateSkillRequest,
        *,
        actor_id: str | None = None,
    ) -> Skill:
        existing = await self._repo.get_by_code(req.code)
        if existing is not None:
            raise DuplicateError(
                f"skill {req.code} already exists: {existing.id}"
            )
        s = Skill(
            code=req.code,
            name=req.name,
            version=req.version,
            description=req.description,
            triggers=req.triggers,
            input_schema=req.input_schema,
            output_schema=req.output_schema,
            prompt_template=req.prompt_template,
            mcp_tools=req.mcp_tools,
            required_envs=req.required_envs,
            config=req.config,
            source=req.source,
            status=req.status,
        )
        s = await self._repo.create(s)
        await self._audit.record(
            actor_type="user",
            actor_id=actor_id,
            action="create",
            resource_type="skill",
            resource_id=s.id,
            after_data={"code": s.code, "version": s.version, "name": s.name},
        )
        return s

    async def update(
        self,
        skill_id: str,
        req: UpdateSkillRequest,
        *,
        actor_id: str | None = None,
    ) -> Skill:
        s = await self.get_by_id(skill_id)
        fields: dict[str, Any] = {}
        for field_name in (
            "name", "description", "triggers", "input_schema",
            "output_schema", "prompt_template", "mcp_tools",
            "required_envs", "config", "status",
        ):
            val = getattr(req, field_name, None)
            if val is not None:
                fields[field_name] = val
        if not fields:
            return s
        before = {"name": s.name, "status": s.status}
        updated = await self._repo.update(skill_id, **fields)
        if updated is None:
            raise NotFoundError("skill", skill_id)
        await self._audit.record(
            actor_type="user",
            actor_id=actor_id,
            action="update",
            resource_type="skill",
            resource_id=skill_id,
            before_data=before,
            after_data=fields,
        )
        return updated

    async def soft_delete(
        self, skill_id: str, *, actor_id: str | None = None
    ) -> None:
        s = await self.get_by_id(skill_id)
        ok = await self._repo.soft_delete(skill_id)
        if not ok:
            return
        await self._audit.record(
            actor_type="user",
            actor_id=actor_id,
            action="delete",
            resource_type="skill",
            resource_id=skill_id,
            before_data={"code": s.code, "version": s.version},
        )

    async def list(
        self,
        *,
        actor: ActorContext,
        limit: int = 50,
        offset: int = 0,
        code: str | None = None,
        status: str | None = None,
    ) -> list[Skill]:
        return await self._repo.list_visible_to(
            actor_user_id=actor.user_id, limit=limit, offset=offset,
            code=code, status=status,
        )

    async def list_public(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        code: str | None = None,
    ) -> list[Skill]:
        return await self._repo.list_public(
            limit=limit, offset=offset, code=code,
        )

    async def set_visibility(
        self,
        skill_id: str,
        visibility: str,
        *,
        actor: ActorContext,
    ) -> Skill | None:
        return await self._repo.set_visibility(
            skill_id, visibility=visibility, actor_user_id=actor.user_id,
        )

    @staticmethod
    def to_response(s: Skill) -> SkillResponse:
        return SkillResponse.from_model(s)


__all__ = ["SkillService"]
