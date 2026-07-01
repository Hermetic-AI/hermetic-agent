"""tests/test_command_service_crud.py — CommandService business orchestration tests.

Phase 4 of asset-registry plan: CommandService CRUD + owner policy + visibility.
Only Memory backend is exercised (no external DB dependency).
"""
from __future__ import annotations

import pytest

from hermetic_agent.store.dto._common import ActorContext
from hermetic_agent.store.dto.command import CreateCommandRequest, UpdateCommandRequest
from hermetic_agent.store.exceptions import DuplicateError
from hermetic_agent.store.repositories.memory.audit_log_repo_memory import (
    MemoryAuditLogRepository,
)
from hermetic_agent.store.repositories.memory.command_repo_memory import (
    MemoryCommandRepository,
)
from hermetic_agent.store.services.audit_log_service import AuditLogService
from hermetic_agent.store.services.command_service import CommandService


@pytest.fixture
def svc() -> CommandService:
    repo = MemoryCommandRepository()
    audit = AuditLogService(MemoryAuditLogRepository())
    return CommandService(repo, audit)


@pytest.mark.asyncio
async def test_create_ok(svc: CommandService) -> None:
    actor = ActorContext(user_id="alice")
    c = await svc.create(
        CreateCommandRequest(
            code="summarize", name="Summarize",
            slash_command="/summarize", system_prompt_addendum="summarize text",
        ),
        actor=actor,
    )
    assert c.owner_user_id == "alice"
    assert c.slash_command == "/summarize"
    assert c.enabled is True


@pytest.mark.asyncio
async def test_create_duplicate_code_raises(svc: CommandService) -> None:
    actor = ActorContext(user_id="alice")
    await svc.create(
        CreateCommandRequest(
            code="x", name="x", slash_command="/a", system_prompt_addendum="a",
        ),
        actor=actor,
    )
    with pytest.raises(DuplicateError):
        await svc.create(
            CreateCommandRequest(
                code="x", name="y", slash_command="/b", system_prompt_addendum="b",
            ),
            actor=actor,
        )


@pytest.mark.asyncio
async def test_create_duplicate_slash_raises(svc: CommandService) -> None:
    actor = ActorContext(user_id="alice")
    await svc.create(
        CreateCommandRequest(
            code="a", name="a", slash_command="/dup", system_prompt_addendum="a",
        ),
        actor=actor,
    )
    with pytest.raises(DuplicateError):
        await svc.create(
            CreateCommandRequest(
                code="b", name="b", slash_command="/dup", system_prompt_addendum="b",
            ),
            actor=actor,
        )


@pytest.mark.asyncio
async def test_set_visibility_non_owner_rejected(svc: CommandService) -> None:
    a = ActorContext(user_id="alice")
    b = ActorContext(user_id="bob")
    c = await svc.create(
        CreateCommandRequest(
            code="x", name="x", slash_command="/x", system_prompt_addendum="x",
        ),
        actor=a,
    )
    result = await svc.set_visibility(str(c.id), "public", actor=b)
    assert result is None
    pub = await svc.set_visibility(str(c.id), "public", actor=a)
    assert pub is not None
    assert pub.visibility == "public"