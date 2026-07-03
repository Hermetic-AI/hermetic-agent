"""tests/test_skill_repo_owner_visibility.py — Skill Repository 资产可见性测试.

Phase 1 of asset-registry plan: owner/visibility/file_fingerprint 字段 + 4 个新抽象方法.
只跑 Memory 版本 (无外部 DB 依赖).
"""

from __future__ import annotations

import uuid

import pytest

from hermetic_agent.store.models.skill import Skill
from hermetic_agent.store.repositories.memory.skill_repo_memory import (
    MemorySkillRepository,
)


@pytest.mark.asyncio
async def test_list_visible_to_returns_owner_private_and_public() -> None:
    repo = MemorySkillRepository()
    own = Skill(
        id=uuid.uuid4(), code="my-skill", name="My", status="enabled",
        owner_user_id="alice", visibility="private",
    )
    other_priv = Skill(
        id=uuid.uuid4(), code="hidden", name="H", status="enabled",
        owner_user_id="bob", visibility="private",
    )
    other_pub = Skill(
        id=uuid.uuid4(), code="public", name="P", status="enabled",
        owner_user_id="bob", visibility="public",
    )
    repo._store[own.id] = own
    repo._store[other_priv.id] = other_priv
    repo._store[other_pub.id] = other_pub

    items = await repo.list_visible_to(actor_user_id="alice", limit=50, offset=0)
    codes = {s.code for s in items}
    assert codes == {"my-skill", "public"}


@pytest.mark.asyncio
async def test_list_public_only_returns_public() -> None:
    repo = MemorySkillRepository()
    pub = Skill(
        id=uuid.uuid4(), code="pub", name="P", status="enabled",
        owner_user_id="alice", visibility="public",
    )
    priv = Skill(
        id=uuid.uuid4(), code="priv", name="P", status="enabled",
        owner_user_id="alice", visibility="private",
    )
    repo._store[pub.id] = pub
    repo._store[priv.id] = priv

    items = await repo.list_public(limit=50, offset=0)
    assert [s.code for s in items] == ["pub"]


@pytest.mark.asyncio
async def test_set_visibility_owner_only() -> None:
    repo = MemorySkillRepository()
    s = Skill(
        id=uuid.uuid4(), code="x", name="X", status="enabled",
        owner_user_id="alice", visibility="private",
    )
    repo._store[s.id] = s

    result = await repo.set_visibility(
        str(s.id), visibility="public", actor_user_id="alice",
    )
    assert result is not None and result.visibility == "public"

    s.visibility = "private"
    result = await repo.set_visibility(
        str(s.id), visibility="public", actor_user_id="bob",
    )
    assert result is None
    assert (await repo.get_by_id(str(s.id))).visibility == "private"
