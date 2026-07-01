"""tests/test_agent_service_crud.py — AgentService CRUD + resolve_for_chat tests.

Phase 4 of asset-registry plan: AgentService CRUD + composite asset resolution.
Only Memory backend is exercised (no external DB dependency).
"""
from __future__ import annotations

import pytest

from hermetic_agent.store.dto._common import ActorContext
from hermetic_agent.store.dto.agent import CreateAgentRequest, UpdateAgentRequest
from hermetic_agent.store.dto.command import CreateCommandRequest
from hermetic_agent.store.dto.prompt import CreatePromptRequest
from hermetic_agent.store.dto.skill import CreateSkillRequest
from hermetic_agent.store.exceptions import DuplicateError
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
    """Wire all 5 services sharing one audit log."""
    audit = AuditLogService(MemoryAuditLogRepository())
    skill_svc = SkillService(MemorySkillRepository(), audit)
    prompt_svc = PromptService(MemoryPromptRepository(), audit)
    command_svc = CommandService(MemoryCommandRepository(), audit)
    agent_svc = AgentService(
        MemoryAgentRepository(), audit,
        skill_service=skill_svc, mcp_config_service=None,  # type: ignore[arg-type]
        prompt_service=prompt_svc, command_service=command_svc,
    )
    return audit, skill_svc, prompt_svc, command_svc, agent_svc


@pytest.mark.asyncio
async def test_create_owner_private(setup) -> None:
    _, _, _, _, agent_svc = setup
    actor = ActorContext(user_id="alice")
    a = await agent_svc.create(
        CreateAgentRequest(code="travel", name="Travel"),
        actor=actor,
    )
    assert a.owner_user_id == "alice"
    assert a.visibility == "private"
    assert a.status == "enabled"


@pytest.mark.asyncio
async def test_create_duplicate_raises(setup) -> None:
    _, _, _, _, agent_svc = setup
    actor = ActorContext(user_id="alice")
    await agent_svc.create(
        CreateAgentRequest(code="x", name="x"), actor=actor,
    )
    with pytest.raises(DuplicateError):
        await agent_svc.create(
            CreateAgentRequest(code="x", name="y"), actor=actor,
        )


@pytest.mark.asyncio
async def test_resolve_for_chat_miss_returns_none(setup) -> None:
    _, _, _, _, agent_svc = setup
    actor = ActorContext(user_id="alice")
    out = await agent_svc.resolve_for_chat(
        actor=actor, agent_code="nope",
    )
    assert out is None


@pytest.mark.asyncio
async def test_resolve_filters_owner_private_skill(setup) -> None:
    """Agent 引用 owner-private skill → resolve 时被过滤, warning 记录."""
    _, skill_svc, _, _, agent_svc = setup
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
    out = await agent_svc.resolve_for_chat(
        actor=other, agent_code="agent-x",
    )
    assert out is not None
    assert out.resolved_skills == []
    assert any("private-skill" in w for w in out.warnings)