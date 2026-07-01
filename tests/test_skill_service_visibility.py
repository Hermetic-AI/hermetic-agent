"""tests/test_skill_service_visibility.py — SkillService visibility/list paths.

Phase 4 of asset-registry plan: Service-level wrapper around
``SkillRepository.list_visible_to`` / ``list_public`` / ``set_visibility``.

Only Memory backend is exercised (no external DB dependency).
"""
from __future__ import annotations

import uuid

import pytest

from hermetic_agent.store.dto._common import ActorContext
from hermetic_agent.store.models.skill import Skill
from hermetic_agent.store.repositories.memory.audit_log_repo_memory import (
    MemoryAuditLogRepository,
)
from hermetic_agent.store.repositories.memory.skill_repo_memory import (
    MemorySkillRepository,
)
from hermetic_agent.store.services.audit_log_service import AuditLogService
from hermetic_agent.store.services.skill_service import SkillService


@pytest.mark.asyncio
async def test_skill_service_list_visible_only_returns_owner_and_public() -> None:
    repo = MemorySkillRepository()
    audit = AuditLogService(MemoryAuditLogRepository())
    svc = SkillService(repo, audit)

    pub = Skill(
        id=uuid.uuid4(), code="pub", name="P",
        owner_user_id="bob", visibility="public", status="enabled",
        description="", version=1,
    )
    priv = Skill(
        id=uuid.uuid4(), code="priv", name="P",
        owner_user_id="bob", visibility="private", status="enabled",
        description="", version=1,
    )
    repo._store[pub.id] = pub
    repo._store[priv.id] = priv

    alice = ActorContext(user_id="alice")
    items = await svc.list(actor=alice, limit=10, offset=0)
    assert {s.code for s in items} == {"pub"}


@pytest.mark.asyncio
async def test_skill_service_list_public_returns_all_public() -> None:
    repo = MemorySkillRepository()
    audit = AuditLogService(MemoryAuditLogRepository())
    svc = SkillService(repo, audit)

    a = Skill(
        id=uuid.uuid4(), code="a", name="A",
        owner_user_id="alice", visibility="public", status="enabled",
        description="", version=1,
    )
    b = Skill(
        id=uuid.uuid4(), code="b", name="B",
        owner_user_id="bob", visibility="public", status="enabled",
        description="", version=1,
    )
    c = Skill(
        id=uuid.uuid4(), code="c", name="C",
        owner_user_id="alice", visibility="private", status="enabled",
        description="", version=1,
    )
    repo._store[a.id] = a
    repo._store[b.id] = b
    repo._store[c.id] = c

    items = await svc.list_public(limit=10, offset=0)
    assert {s.code for s in items} == {"a", "b"}


@pytest.mark.asyncio
async def test_skill_service_set_visibility_owner_only() -> None:
    repo = MemorySkillRepository()
    audit = AuditLogService(MemoryAuditLogRepository())
    svc = SkillService(repo, audit)
    a, b = ActorContext(user_id="alice"), ActorContext(user_id="bob")
    s = Skill(
        id=uuid.uuid4(), code="x", name="X", owner_user_id="alice",
        visibility="private", status="enabled",
        description="", version=1,
    )
    repo._store[s.id] = s
    assert (await svc.set_visibility(str(s.id), "public", actor=b)) is None
    assert (await svc.set_visibility(str(s.id), "public", actor=a)).visibility == "public"
