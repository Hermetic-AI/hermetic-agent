"""tests/test_prompt_service_crud.py — PromptService business orchestration tests.

Phase 4 of asset-registry plan: PromptService CRUD + owner policy + visibility.
Only Memory backend is exercised (no external DB dependency).
"""
from __future__ import annotations

import pytest

from hermetic_agent.store.dto._common import ActorContext
from hermetic_agent.store.dto.prompt import CreatePromptRequest, UpdatePromptRequest
from hermetic_agent.store.exceptions import DuplicateError, NotFoundError
from hermetic_agent.store.repositories.memory.audit_log_repo_memory import (
    MemoryAuditLogRepository,
)
from hermetic_agent.store.repositories.memory.prompt_repo_memory import (
    MemoryPromptRepository,
)
from hermetic_agent.store.services.audit_log_service import AuditLogService
from hermetic_agent.store.services.prompt_service import PromptService


@pytest.fixture
def svc() -> PromptService:
    repo = MemoryPromptRepository()
    audit = AuditLogService(MemoryAuditLogRepository())
    return PromptService(repo, audit)


@pytest.mark.asyncio
async def test_create_ok(svc: PromptService) -> None:
    actor = ActorContext(user_id="alice")
    p = await svc.create(
        CreatePromptRequest(code="hi", name="hi", description="d", content="c"),
        actor=actor,
    )
    assert p.owner_user_id == "alice"
    assert p.visibility == "private"
    assert p.status == "enabled"


@pytest.mark.asyncio
async def test_create_duplicate_raises(svc: PromptService) -> None:
    actor = ActorContext(user_id="alice")
    await svc.create(
        CreatePromptRequest(code="hi", name="x", content="c"), actor=actor,
    )
    with pytest.raises(DuplicateError):
        await svc.create(
            CreatePromptRequest(code="hi", name="y", content="d"), actor=actor,
        )


@pytest.mark.asyncio
async def test_update_owner_only(svc: PromptService) -> None:
    a = ActorContext(user_id="alice")
    b = ActorContext(user_id="bob")
    p = await svc.create(
        CreatePromptRequest(code="x", name="x", content="c"), actor=a,
    )
    with pytest.raises(Exception) as exc_info:
        await svc.update(
            str(p.id), UpdatePromptRequest(name="evil"), actor=b,
        )
    assert exc_info.value.__class__.__name__ == "PolicyError"
    updated = await svc.update(
        str(p.id), UpdatePromptRequest(name="good"), actor=a,
    )
    assert updated.name == "good"


@pytest.mark.asyncio
async def test_set_visibility_and_list_visible(svc: PromptService) -> None:
    a = ActorContext(user_id="alice")
    b = ActorContext(user_id="bob")
    p = await svc.create(
        CreatePromptRequest(code="x", name="x", content="c"), actor=a,
    )
    pub = await svc.set_visibility(str(p.id), "public", actor=a)
    assert pub is not None
    assert pub.visibility == "public"
    items = await svc.list(actor=b, limit=50, offset=0)
    assert any(x.id == p.id for x in items)
    no_op = await svc.set_visibility(str(p.id), "private", actor=b)
    assert no_op is None