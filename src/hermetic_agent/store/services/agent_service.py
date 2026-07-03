"""AgentService — Agent 复合体资产的业务编排.

业务规则:
- create / update / soft_delete / set_visibility: 仅 owner 可改
- resolve_for_chat: 委托给 ``_agent_resolve.resolve_agent``, 过滤缺失/不可见/禁用资产
"""
from __future__ import annotations

import uuid

import structlog

from hermetic_agent.store.dto._common import ActorContext
from hermetic_agent.store.dto.agent import (
    AgentResponse,
    CreateAgentRequest,
    UpdateAgentRequest,
)
from hermetic_agent.store.exceptions import (
    DuplicateError,
    NotFoundError,
    PolicyError,
)
from hermetic_agent.store.models.agent import Agent
from hermetic_agent.store.repositories.agent_repo import AgentRepository
from hermetic_agent.store.services._agent_resolve import ResolvedAgent, resolve_agent
from hermetic_agent.store.services.audit_log_service import AuditLogService
from hermetic_agent.store.services.command_service import CommandService
from hermetic_agent.store.services.mcp_config_service import McpConfigService
from hermetic_agent.store.services.prompt_service import PromptService
from hermetic_agent.store.services.skill_service import SkillService

logger = structlog.get_logger(__name__)


_UPDATE_FIELDS = (
    "name", "description", "system_prompt", "model", "tool_level", "network",
    "skill_codes", "mcp_server_codes", "prompt_codes", "command_codes", "status",
)


class AgentService:
    """Agent 资产服务."""

    def __init__(
        self,
        repo: AgentRepository,
        audit: AuditLogService,
        *,
        skill_service: SkillService,
        mcp_config_service: McpConfigService | None,
        prompt_service: PromptService,
        command_service: CommandService,
    ) -> None:
        self._repo = repo
        self._audit = audit
        self._skill_service = skill_service
        self._mcp_service = mcp_config_service
        self._prompt_service = prompt_service
        self._command_service = command_service

    async def get_by_id(self, agent_id: str) -> Agent:
        a = await self._repo.get_by_id(agent_id)
        if a is None:
            raise NotFoundError("agent", agent_id)
        return a

    async def get_by_code(self, code: str) -> Agent:
        a = await self._repo.get_by_code(code)
        if a is None:
            raise NotFoundError("agent", code)
        return a

    async def list(
        self,
        *,
        actor: ActorContext,
        limit: int = 50,
        offset: int = 0,
        code: str | None = None,
        status: str | None = None,
    ) -> list[Agent]:
        return await self._repo.list_visible_to(
            actor_user_id=actor.user_id,
            limit=limit, offset=offset, code=code, status=status,
        )

    async def list_public(
        self, *, limit: int = 50, offset: int = 0, code: str | None = None,
    ) -> list[Agent]:
        return await self._repo.list_public(limit=limit, offset=offset, code=code)

    async def create(
        self, req: CreateAgentRequest, *, actor: ActorContext,
    ) -> Agent:
        existing = await self._repo.get_by_code(req.code)
        if existing is not None:
            raise DuplicateError(f"agent {req.code} already exists: {existing.id}")
        a = Agent(
            id=uuid.uuid4(), code=req.code, name=req.name,
            description=req.description, system_prompt=req.system_prompt,
            model=req.model, tool_level=req.tool_level, network=req.network,
            skill_codes=req.skill_codes, mcp_server_codes=req.mcp_server_codes,
            prompt_codes=req.prompt_codes, command_codes=req.command_codes,
            owner_user_id=actor.user_id, visibility="private", status="enabled",
        )
        await self._repo.create(a)
        await self._audit.record(
            actor_type="user", actor_id=actor.user_id,
            action="create", resource_type="agent", resource_id=str(a.id),
            after_data={"code": a.code, "name": a.name},
        )
        return a

    async def update(
        self, agent_id: str, req: UpdateAgentRequest, *, actor: ActorContext,
    ) -> Agent:
        a = await self.get_by_id(agent_id)
        if a.owner_user_id != actor.user_id:
            raise PolicyError("FORBIDDEN", detail="non-owner cannot update agent")
        fields: dict[str, object] = {
            k: v for k in _UPDATE_FIELDS
            if (v := getattr(req, k, None)) is not None
        }
        if not fields:
            return a
        before = {"name": a.name, "status": a.status}
        updated = await self._repo.update(agent_id, **fields)
        if updated is None:
            raise NotFoundError("agent", agent_id)
        await self._audit.record(
            actor_type="user", actor_id=actor.user_id,
            action="update", resource_type="agent", resource_id=agent_id,
            before_data=before, after_data=fields,
        )
        return updated

    async def set_visibility(
        self, agent_id: str, visibility: str, *, actor: ActorContext,
    ) -> Agent | None:
        return await self._repo.set_visibility(
            agent_id, visibility=visibility, actor_user_id=actor.user_id,
        )

    async def soft_delete(self, agent_id: str, *, actor: ActorContext) -> None:
        a = await self.get_by_id(agent_id)
        await self._repo.soft_delete(agent_id)
        await self._audit.record(
            actor_type="user", actor_id=actor.user_id,
            action="delete", resource_type="agent", resource_id=agent_id,
            before_data={"code": a.code},
        )

    @staticmethod
    def to_response(a: Agent) -> AgentResponse:
        return AgentResponse.from_model(a)

    async def resolve_for_chat(
        self, *, actor: ActorContext, agent_code: str,
    ) -> ResolvedAgent | None:
        """agent 不存在 / 已删 / 禁用返 None; 否则委托 resolve_agent 过滤引用."""
        a = await self._repo.get_by_code(agent_code)
        if a is None or a.is_deleted or a.status != "enabled":
            return None
        return await resolve_agent(
            agent=a, actor=actor,
            skill_service=self._skill_service,
            mcp_service=self._mcp_service,
            prompt_service=self._prompt_service,
            command_service=self._command_service,
        )


__all__ = ["AgentService"]
