"""tests/test_agent_resolver_resolves_components.py — AgentResolver 薄包装测试.

AgentResolver 是 chat_inject (L3) 对 AgentService.resolve_for_chat 的薄封装.
这里通过真实 service stack (memory repos) 验证 4 个关键分支:
- agent 不存在 → None
- agent 禁用 → None
- owner 视角 → ResolvedAgent 完整, 无 warnings
- 其他 actor 视角 → owner-private skill 被过滤, warning 记录
"""
from __future__ import annotations

import pytest

from hermetic_agent.chat_inject.agent_resolver import AgentResolver
from hermetic_agent.store.dto._common import ActorContext
from hermetic_agent.store.dto.agent import CreateAgentRequest
from hermetic_agent.store.dto.skill import CreateSkillRequest
from hermetic_agent.store.repositories.memory.agent_repo_memory import (
    MemoryAgentRepository,
)
from hermetic_agent.store.repositories.memory.audit_log_repo_memory import (
    MemoryAuditLogRepository,
)
from hermetic_agent.store.repositories.memory.command_repo_memory import (
    MemoryCommandRepository,
)
from hermetic_agent.store.repositories.memory.prompt_repo_memory import (
    MemoryPromptRepository,
)
from hermetic_agent.store.repositories.memory.skill_repo_memory import (
    MemorySkillRepository,
)
from hermetic_agent.store.services.agent_service import AgentService
from hermetic_agent.store.services.audit_log_service import AuditLogService
from hermetic_agent.store.services.command_service import CommandService
from hermetic_agent.store.services.prompt_service import PromptService
from hermetic_agent.store.services.skill_service import SkillService


@pytest.fixture
def setup():
    audit = AuditLogService(MemoryAuditLogRepository())
    skill_svc = SkillService(MemorySkillRepository(), audit)
    prompt_svc = PromptService(MemoryPromptRepository(), audit)
    command_svc = CommandService(MemoryCommandRepository(), audit)
    agent_svc = AgentService(
        MemoryAgentRepository(), audit,
        skill_service=skill_svc, mcp_config_service=None,  # type: ignore[arg-type]
        prompt_service=prompt_svc, command_service=command_svc,
    )
    return AgentResolver(agent_svc), agent_svc, skill_svc


async def test_resolve_returns_none_when_agent_missing(setup) -> None:
    resolver, *_ = setup
    actor = ActorContext(user_id="alice")
    out = await resolver.resolve(actor=actor, agent_code="nope")
    assert out is None


async def test_resolve_returns_none_when_agent_disabled(setup) -> None:
    resolver, agent_svc, _ = setup
    actor = ActorContext(user_id="alice")
    a = await agent_svc.create(
        CreateAgentRequest(code="off", name="Off"), actor=actor,
    )
    a.status = "disabled"  # type: ignore[misc]
    out = await resolver.resolve(actor=actor, agent_code="off")
    assert out is None


async def test_resolve_returns_full_resolved_agent_for_owner(setup) -> None:
    resolver, agent_svc, _ = setup
    actor = ActorContext(user_id="alice")
    await agent_svc.create(
        CreateAgentRequest(code="travel", name="Travel"), actor=actor,
    )
    out = await resolver.resolve(actor=actor, agent_code="travel")
    assert out is not None
    assert out.agent.code == "travel"
    assert out.system_prompt == ""
    assert out.resolved_skills == []
    assert out.warnings == []


async def test_resolve_filters_owner_private_skill_for_other_actor(setup) -> None:
    resolver, agent_svc, skill_svc = setup
    owner = ActorContext(user_id="alice")
    other = ActorContext(user_id="bob")
    await skill_svc.create(
        CreateSkillRequest(
            code="private-skill", name="p",
            description="x", prompt_template="x",
        ),
        actor_id=owner.user_id,
    )
    await agent_svc.create(
        CreateAgentRequest(
            code="agent-x", name="X", skill_codes=["private-skill"],
        ),
        actor=owner,
    )
    out = await resolver.resolve(actor=other, agent_code="agent-x")
    assert out is not None
    assert out.resolved_skills == []
    assert any("private-skill" in w for w in out.warnings)

