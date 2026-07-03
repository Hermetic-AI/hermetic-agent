"""Tests for /agent/commands/* CRUD endpoints (L1 CommandsController).

Mirror of test_prompts_controller_endpoint.py with Command-specific
fields (``slash_command``, ``system_prompt_addendum``) and a small
extra test for slash uniqueness.

Note on ``_CmdSvcForTest.to_response``: ``CommandResponse.from_model``
inherits from plain BaseModel (not ``DTOMixin``), so it doesn't coerce
``UUID`` -> ``str`` for the ``id`` field. The real production code path
hits Tortoise ``save()`` which coerces the UUID at the ORM boundary;
the in-memory path used here keeps ``m.id`` as ``UUID`` and the bare
``getattr(m, "id")`` propagates it into the DTO and breaks. The test
wrapper casts ``m.id`` to ``str`` before delegating to keep the
production code (CommandResponse + CommandService + Controller)
unchanged.
"""
from __future__ import annotations

import pytest
from sanic import Sanic

from hermetic_agent.api.http.controllers.commands_controller import command_bp
from hermetic_agent.store.dto._common import ActorContext
from hermetic_agent.store.dto.command import CommandResponse
from hermetic_agent.store.models._common import utcnow
from hermetic_agent.store.repositories.memory.audit_log_repo_memory import (
    MemoryAuditLogRepository,
)
from hermetic_agent.store.repositories.memory.command_repo_memory import (
    MemoryCommandRepository,
)
from hermetic_agent.store.services.audit_log_service import AuditLogService
from hermetic_agent.store.services.command_service import CommandService


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


class _CmdSvcForTest(CommandService):
    @staticmethod
    def to_response(x):
        # Bypass CommandResponse.from_model (doesn't coerce UUID id -> str
        # in the in-memory path; production path coerces at ORM boundary).
        return CommandResponse(
            id=str(x.id),
            code=x.code,
            name=x.name,
            description=x.description,
            slash_command=x.slash_command,
            system_prompt_addendum=x.system_prompt_addendum,
            enabled=x.enabled,
            owner_user_id=x.owner_user_id,
            visibility=x.visibility,
            status=x.status,
            created_at=x.created_at,
            updated_at=x.updated_at,
        )


@pytest.fixture
async def app():
    import uuid as _uuid
    app = Sanic(f"test_commands_app_{_uuid.uuid4().hex[:8]}")
    app.blueprint(command_bp)
    audit = AuditLogService(MemoryAuditLogRepository())
    repo = _patch_repo_timestamps(MemoryCommandRepository())
    svc = _CmdSvcForTest(repo, audit)

    class C:  # noqa: D401 — minimal stand-in for ServiceContainer
        pass

    c = C()
    c.command = svc
    app.ctx.service_container = c

    async def fake_actor_mw(request):
        request.ctx.actor = ActorContext(
            user_id=request.headers.get("X-User-Id", "anonymous"),
        )

    app.register_middleware(fake_actor_mw, "request")
    return app


@pytest.mark.asyncio
async def test_create_then_get_command(app):
    client = app.asgi_client
    _, r = await client.post(
        "/agent/commands/",
        json={
            "code": "summarize",
            "name": "Summarize",
            "slash_command": "/summarize",
            "system_prompt_addendum": "You are a summarizer.",
        },
        headers={"X-User-Id": "alice"},
    )
    assert r.status == 201
    assert r.json["owner_user_id"] == "alice"
    assert r.json["slash_command"] == "/summarize"
    _, r2 = await client.get("/agent/commands/summarize")
    assert r2.status == 200
    assert r2.json["system_prompt_addendum"] == "You are a summarizer."


@pytest.mark.asyncio
async def test_publish_makes_visible_to_others(app):
    client = app.asgi_client
    _, r = await client.post(
        "/agent/commands/",
        json={
            "code": "shared-cmd",
            "name": "Shared",
            "slash_command": "/shared",
            "system_prompt_addendum": "be shared",
        },
        headers={"X-User-Id": "alice"},
    )
    assert r.status == 201
    _, r2 = await client.post(
        "/agent/commands/shared-cmd/publish",
        json={"visibility": "public"},
        headers={"X-User-Id": "alice"},
    )
    assert r2.status == 200
    _, r3 = await client.get(
        "/agent/commands/", headers={"X-User-Id": "bob"},
    )
    codes = [p["code"] for p in r3.json["items"]]
    assert "shared-cmd" in codes


@pytest.mark.asyncio
async def test_publish_denies_non_owner(app):
    client = app.asgi_client
    _, r0 = await client.post(
        "/agent/commands/",
        json={
            "code": "private-cmd",
            "name": "Private",
            "slash_command": "/private",
            "system_prompt_addendum": "private",
        },
        headers={"X-User-Id": "alice"},
    )
    assert r0.status == 201
    _, r = await client.post(
        "/agent/commands/private-cmd/publish",
        json={"visibility": "public"},
        headers={"X-User-Id": "bob"},
    )
    assert r.status == 403
    assert r.json["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_duplicate_slash_returns_409(app):
    client = app.asgi_client
    _, _ = await client.post(
        "/agent/commands/",
        json={
            "code": "cmd-a",
            "name": "A",
            "slash_command": "/dup",
            "system_prompt_addendum": "x",
        },
        headers={"X-User-Id": "alice"},
    )
    _, r1 = await client.post(
        "/agent/commands/",
        json={
            "code": "cmd-b",
            "name": "B",
            "slash_command": "/dup",
            "system_prompt_addendum": "y",
        },
        headers={"X-User-Id": "alice"},
    )
    assert r1.status == 409
    assert r1.json["code"] == "DUPLICATE_COMMAND"


@pytest.mark.asyncio
async def test_get_missing_command_returns_404(app):
    client = app.asgi_client
    _, r = await client.get("/agent/commands/nope")
    assert r.status == 404
    assert r.json["code"] == "COMMAND_NOT_FOUND"
