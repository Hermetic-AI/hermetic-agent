"""tests/test_command_repo_crud.py — Command Repository CRUD + visibility tests.

Phase 2 of asset-registry plan: new Command model + dual repos.
Only Memory backend is exercised (no external DB dependency).
"""
from __future__ import annotations

import uuid

import pytest

from hermetic_agent.store.models.command import Command
from hermetic_agent.store.repositories.memory.command_repo_memory import (
    MemoryCommandRepository,
)


@pytest.mark.asyncio
async def test_create_command_stores_slash_and_prompt() -> None:
    repo = MemoryCommandRepository()
    c = Command(
        id=uuid.uuid4(), code="summarizer", name="Summarizer",
        slash_command="/summarize",
        system_prompt_addendum="When user types /summarize, output 3 bullet points.",
        owner_user_id="alice", visibility="private", status="enabled",
    )
    await repo.create(c)
    got = await repo.get_by_code("summarizer")
    assert got is not None
    assert got.slash_command == "/summarize"
    assert got.system_prompt_addendum.startswith("When user types")


@pytest.mark.asyncio
async def test_get_by_slash_returns_command() -> None:
    repo = MemoryCommandRepository()
    c = Command(
        id=uuid.uuid4(), code="x", name="X",
        slash_command="/x", system_prompt_addendum="...",
        owner_user_id="alice", status="enabled",
    )
    await repo.create(c)
    got = await repo.get_by_slash("/x")
    assert got is not None and got.code == "x"


@pytest.mark.asyncio
async def test_set_visibility_owner_only() -> None:
    repo = MemoryCommandRepository()
    c = Command(
        id=uuid.uuid4(), code="x", name="X",
        slash_command="/x", system_prompt_addendum="...",
        owner_user_id="alice", status="enabled",
    )
    await repo.create(c)
    assert (await repo.set_visibility(
        str(c.id), visibility="public", actor_user_id="bob",
    )) is None
    assert (await repo.set_visibility(
        str(c.id), visibility="public", actor_user_id="alice",
    )).visibility == "public"
