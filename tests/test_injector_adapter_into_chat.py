"""tests/test_injector_adapter_into_chat.py — Task 16 RED→GREEN for chat_inject.injector_adapter.

覆盖两种情形:
1. 无 agent_code → system_prompt / extra_opencode_mcp 保持不变 (noop).
2. 有 agent_code → system_prompt 拼接 agent 自身 system_prompt.

不依赖真实 Scenario 中间件 / Sanic app — 用 SimpleNamespace 模拟.
"""
from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

from hermetic_agent.chat_inject.injector_adapter import inject_agent_into_chat
from hermetic_agent.store.dto._common import ActorContext
from hermetic_agent.store.models.agent import Agent
from hermetic_agent.store.repositories.memory.agent_repo_memory import MemoryAgentRepository
from hermetic_agent.store.repositories.memory.audit_log_repo_memory import MemoryAuditLogRepository
from hermetic_agent.store.repositories.memory.command_repo_memory import MemoryCommandRepository
from hermetic_agent.store.repositories.memory.mcp_config_repo_memory import (
    MemoryMcpConfigRepository,
)
from hermetic_agent.store.repositories.memory.prompt_repo_memory import MemoryPromptRepository
from hermetic_agent.store.repositories.memory.skill_repo_memory import MemorySkillRepository
from hermetic_agent.store.services.agent_service import AgentService
from hermetic_agent.store.services.audit_log_service import AuditLogService
from hermetic_agent.store.services.command_service import CommandService
from hermetic_agent.store.services.mcp_config_service import McpConfigService
from hermetic_agent.store.services.prompt_service import PromptService
from hermetic_agent.store.services.skill_service import SkillService


def _build() -> AgentService:
    audit = AuditLogService(MemoryAuditLogRepository())
    skill = SkillService(MemorySkillRepository(), audit)
    mcp = McpConfigService(MemoryMcpConfigRepository(), audit)
    p = PromptService(MemoryPromptRepository(), audit)
    c = CommandService(MemoryCommandRepository(), audit)
    return AgentService(
        MemoryAgentRepository(), audit,
        skill_service=skill, mcp_config_service=mcp,
        prompt_service=p, command_service=c,
    )


def test_inject_agent_into_chat_noop_when_no_agent() -> None:
    agent = _build()
    actor = ActorContext(user_id="alice")
    request = SimpleNamespace(
        ctx=SimpleNamespace(actor=actor),
        json=None, headers={},
    )
    chat_request = SimpleNamespace(
        system_prompt="orig", extra_opencode_mcp={},
    )

    out = asyncio.run(
        inject_agent_into_chat(
            request=request,
            chat_request=chat_request,
            agent_service=agent,
        )
    )
    assert out.system_prompt == "orig"
    assert out.extra_opencode_mcp == {}


def test_inject_agent_into_chat_returns_new_object_when_data_set() -> None:
    agent_service = _build()
    actor = ActorContext(user_id="alice")
    a = Agent(
        id=uuid.uuid4(), code="x", name="X", system_prompt="AP.",
        model="openai/mini", tool_level="standard", network="local",
        owner_user_id="alice", visibility="private", status="enabled",
        skill_codes=[], mcp_server_codes=[],
        prompt_codes=[], command_codes=[],
    )
    asyncio.run(agent_service._repo.create(a))

    request = SimpleNamespace(
        ctx=SimpleNamespace(actor=actor),
        json={"agent_code": "x"},
        headers={"X-Agent-Code": "x"},
    )
    chat_request = SimpleNamespace(
        system_prompt="SC.", extra_opencode_mcp={},
    )

    out = asyncio.run(
        inject_agent_into_chat(
            request=request,
            chat_request=chat_request,
            agent_service=agent_service,
        )
    )
    assert "SC." in out.system_prompt
    assert "AP." in out.system_prompt
