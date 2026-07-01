"""Tests for /agent/agents/* CRUD endpoints (L1 AgentsController).

Mirror of test_prompts_controller_endpoint.py for the Agent composite
asset (system_prompt / model / tool_level / network + 4 *_codes lists).

AgentService requires PromptService + CommandService + SkillService +
optional McpConfigService. Tests build minimal stand-ins so we don't
need a full DB.
"""
from __future__ import annotations

import pytest
from sanic import Sanic

from hermetic_agent.api.http.controllers.agents_controller import agent_bp
from hermetic_agent.store.dto._common import ActorContext
from hermetic_agent.store.dto.agent import AgentResponse
from hermetic_agent.store.models._common import utcnow
from hermetic_agent.store.repositories.memory.agent_repo_memory import (
    MemoryAgentRepository,
)
from hermetic_agent.store.repositories.memory.audit_log_repo_memory import (
    MemoryAuditLogRepository,
)
from hermetic_agent.store.repositories.memory.command_repo_memory import (
    MemoryCommandRepository,
)
from hermetic_agent.store.repositories.memory.mcp_config_repo_memory import (
    MemoryMcpConfigRepository,
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
from hermetic_agent.store.services.mcp_config_service import McpConfigService
from hermetic_agent.store.services.prompt_service import PromptService
from hermetic_agent.store.services.skill_service import SkillService


def _patch_repo_timestamps(repo):
    original_create = repo.create

    async def patched_create(model):
        if getattr(model, "created_at", None) is None:
            model.created_at = utcnow()
        if getattr(model, "updated_at", None) is None:
            model.updated_at = utcnow()
        return await original_create(model)

    repo.create = patched_create  # type: ignore[method-assign]
    return repo


class _AgentSvcForTest(AgentService):
    @staticmethod
    def to_response(a):
        # Bypass AgentResponse.from_model (UUID id coercion in-memory).
        return AgentResponse(
            id=str(a.id),
            code=a.code,
            name=a.name,
            description=a.description,
            system_prompt=a.system_prompt,
            model=a.model,
            tool_level=a.tool_level,
            network=a.network,
            skill_codes=list(a.skill_codes),
            mcp_server_codes=list(a.mcp_server_codes),
            prompt_codes=list(a.prompt_codes),
            command_codes=list(a.command_codes),
            owner_user_id=a.owner_user_id,
            visibility=a.visibility,
            status=a.status,
            created_at=a.created_at,
            updated_at=a.updated_at,
        )


@pytest.fixture
async def app():
    import uuid as _uuid
    app = Sanic(f"test_agents_app_{_uuid.uuid4().hex[:8]}")
    app.blueprint(agent_bp)

    audit = AuditLogService(MemoryAuditLogRepository())
    skill_svc = SkillService(_patch_repo_timestamps(MemorySkillRepository()), audit)
    mcp_svc = McpConfigService(_patch_repo_timestamps(MemoryMcpConfigRepository()), audit)
    prompt_svc = PromptService(_patch_repo_timestamps(MemoryPromptRepository()), audit)
    command_svc = CommandService(_patch_repo_timestamps(MemoryCommandRepository()), audit)
    agent_repo = _patch_repo_timestamps(MemoryAgentRepository())
    agent_svc = _AgentSvcForTest(
        agent_repo, audit,
        skill_service=skill_svc,
        mcp_config_service=mcp_svc,
        prompt_service=prompt_svc,
        command_service=command_svc,
    )

    class C:  # noqa: D401 — minimal stand-in for ServiceContainer
        pass

    c = C()
    c.agent = agent_svc
    app.ctx.service_container = c

    async def fake_actor_mw(request):
        request.ctx.actor = ActorContext(
            user_id=request.headers.get("X-User-Id", "anonymous"),
        )

    app.register_middleware(fake_actor_mw, "request")
    return app


@pytest.mark.asyncio
async def test_create_then_get_agent(app):
    client = app.asgi_client
    _, r = await client.post(
        "/agent/agents/",
        json={
            "code": "helper",
            "name": "Helper",
            "description": "general helper",
            "system_prompt": "You are a helper.",
            "model": "openai/gpt-4o-mini",
            "tool_level": "standard",
            "network": "local",
            "skill_codes": ["write-file"],
            "prompt_codes": ["hi"],
        },
        headers={"X-User-Id": "alice"},
    )
    assert r.status == 201
    body = r.json
    assert body["owner_user_id"] == "alice"
    assert body["tool_level"] == "standard"
    assert body["skill_codes"] == ["write-file"]
    assert body["prompt_codes"] == ["hi"]
    _, r2 = await client.get("/agent/agents/helper")
    assert r2.status == 200
    assert r2.json["system_prompt"] == "You are a helper."


@pytest.mark.asyncio
async def test_publish_makes_visible_to_others(app):
    client = app.asgi_client
    _, _ = await client.post(
        "/agent/agents/",
        json={
            "code": "shared-agent",
            "name": "Shared",
            "system_prompt": "shared",
            "skill_codes": [],
        },
        headers={"X-User-Id": "alice"},
    )
    _, r2 = await client.post(
        "/agent/agents/shared-agent/publish",
        json={"visibility": "public"},
        headers={"X-User-Id": "alice"},
    )
    assert r2.status == 200
    _, r3 = await client.get(
        "/agent/agents/", headers={"X-User-Id": "bob"},
    )
    codes = [p["code"] for p in r3.json["items"]]
    assert "shared-agent" in codes


@pytest.mark.asyncio
async def test_publish_denies_non_owner(app):
    client = app.asgi_client
    _, _ = await client.post(
        "/agent/agents/",
        json={
            "code": "private-agent",
            "name": "Private",
            "system_prompt": "private",
            "skill_codes": [],
        },
        headers={"X-User-Id": "alice"},
    )
    _, r = await client.post(
        "/agent/agents/private-agent/publish",
        json={"visibility": "public"},
        headers={"X-User-Id": "bob"},
    )
    assert r.status == 403
    assert r.json["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_get_missing_agent_returns_404(app):
    client = app.asgi_client
    _, r = await client.get("/agent/agents/nope")
    assert r.status == 404
    assert r.json["code"] == "AGENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_invalid_tool_level_returns_400(app):
    client = app.asgi_client
    _, r = await client.post(
        "/agent/agents/",
        json={
            "code": "bad",
            "name": "Bad",
            "system_prompt": "x",
            "tool_level": "ultra",
            "skill_codes": [],
        },
        headers={"X-User-Id": "alice"},
    )
    assert r.status == 400
    assert r.json["code"] == "VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_duplicate_code_returns_409(app):
    client = app.asgi_client
    _, _ = await client.post(
        "/agent/agents/",
        json={
            "code": "dup",
            "name": "X",
            "system_prompt": "x",
            "skill_codes": [],
        },
        headers={"X-User-Id": "alice"},
    )
    _, r1 = await client.post(
        "/agent/agents/",
        json={
            "code": "dup",
            "name": "Y",
            "system_prompt": "y",
            "skill_codes": [],
        },
        headers={"X-User-Id": "alice"},
    )
    assert r1.status == 409
    assert r1.json["code"] == "DUPLICATE_AGENT"
