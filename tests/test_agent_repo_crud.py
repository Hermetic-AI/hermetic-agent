"""tests/test_agent_repo_crud.py — Agent Repository CRUD + visibility tests.

Phase 3 of asset-registry plan: new Agent composite model + dual repos.
Only Memory backend is exercised (no external DB dependency).
"""
from __future__ import annotations

import uuid

import pytest

from hermetic_agent.store.models.agent import Agent
from hermetic_agent.store.repositories.memory.agent_repo_memory import (
    MemoryAgentRepository,
)


@pytest.mark.asyncio
async def test_create_agent_with_reference_lists() -> None:
    repo = MemoryAgentRepository()
    a = Agent(
        id=uuid.uuid4(), code="travel-agent", name="Travel",
        description="helps with travel",
        system_prompt="You are a travel assistant.",
        model="openai/gpt-4o-mini", tool_level="standard", network="local",
        skill_codes=["flight-query", "booking"],
        mcp_server_codes=["default_mcp"],
        prompt_codes=["safety"],
        command_codes=["summarize"],
        owner_user_id="alice", visibility="private", status="enabled",
    )
    await repo.create(a)
    got = await repo.get_by_code("travel-agent")
    assert got is not None
    assert got.skill_codes == ["flight-query", "booking"]
    assert got.prompt_codes == ["safety"]


@pytest.mark.asyncio
async def test_set_visibility_owner_only_and_list_public() -> None:
    repo = MemoryAgentRepository()
    a = Agent(
        id=uuid.uuid4(), code="x", name="X", system_prompt="p",
        model="openai/mini", tool_level="standard", network="local",
        owner_user_id="alice", visibility="private", status="enabled",
        skill_codes=[], mcp_server_codes=[], prompt_codes=[], command_codes=[],
    )
    await repo.create(a)
    assert (await repo.set_visibility(
        str(a.id), visibility="public", actor_user_id="bob",
    )) is None
    assert (await repo.set_visibility(
        str(a.id), visibility="public", actor_user_id="alice",
    )).visibility == "public"
    pub_list = await repo.list_public(limit=10, offset=0)
    assert len(pub_list) == 1
