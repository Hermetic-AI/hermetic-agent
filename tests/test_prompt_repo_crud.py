"""tests/test_prompt_repo_crud.py — Prompt Repository CRUD + visibility tests.

Phase 1 of asset-registry plan: new Prompt model + dual repos.
Only Memory backend is exercised (no external DB dependency).
"""
from __future__ import annotations

import uuid

from hermetic_agent.store.models.prompt import Prompt
from hermetic_agent.store.repositories.memory.prompt_repo_memory import (
    MemoryPromptRepository,
)


async def test_create_and_get_by_code() -> None:
    repo = MemoryPromptRepository()
    p = Prompt(
        id=uuid.uuid4(), code="hello", name="Hello",
        description="greeting prompt", content="say hi",
        owner_user_id="alice", visibility="private", status="enabled",
    )
    await repo.create(p)
    got = await repo.get_by_code("hello")
    assert got is not None and got.content == "say hi"


async def test_soft_delete_and_get_by_code_returns_none() -> None:
    repo = MemoryPromptRepository()
    p = Prompt(
        id=uuid.uuid4(), code="bye", name="B",
        content="say bye", owner_user_id="alice", status="enabled",
    )
    await repo.create(p)
    assert await repo.soft_delete(str(p.id)) is True
    assert await repo.get_by_code("bye") is None
    assert await repo.soft_delete(str(p.id)) is False  # 幂等


async def test_set_visibility_owner_only() -> None:
    repo = MemoryPromptRepository()
    p = Prompt(
        id=uuid.uuid4(), code="x", name="X",
        content="c", owner_user_id="alice", status="enabled",
    )
    await repo.create(p)
    r = await repo.set_visibility(
        str(p.id), visibility="public", actor_user_id="bob",
    )
    assert r is None
    r = await repo.set_visibility(
        str(p.id), visibility="public", actor_user_id="alice",
    )
    assert r is not None and r.visibility == "public"
