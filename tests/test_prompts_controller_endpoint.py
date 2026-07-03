"""Tests for /agent/prompts/* CRUD endpoints (L1 PromptsController).

Covers the asset-registry asset: create + get + publish flow.
Uses Sanic ``asgi_client`` for in-process HTTP, with ``X-User-Id`` header
acting as the actor (mirrors ActorContextMiddleware in production).
"""
from __future__ import annotations

import pytest
from sanic import Sanic

from hermetic_agent.api.http.controllers.prompts_controller import prompt_bp
from hermetic_agent.store.dto._common import ActorContext
from hermetic_agent.store.models._common import utcnow
from hermetic_agent.store.repositories.memory.audit_log_repo_memory import (
    MemoryAuditLogRepository,
)
from hermetic_agent.store.repositories.memory.prompt_repo_memory import (
    MemoryPromptRepository,
)
from hermetic_agent.store.services.audit_log_service import AuditLogService
from hermetic_agent.store.services.prompt_service import PromptService


def _patch_repo_timestamps(repo):
    """In-memory repo doesn't fire Tortoise auto_now_add/auto_now.

    Wrap ``repo.create`` so any Model dropped into the store gets
    ``created_at`` + ``updated_at`` filled in. Avoids modifying the
    production MemoryRepository (zero-modification rule).
    """
    original_create = repo.create

    async def patched_create(model):
        if getattr(model, "created_at", None) is None:
            model.created_at = utcnow()
        if getattr(model, "updated_at", None) is None:
            model.updated_at = utcnow()
        return await original_create(model)

    repo.create = patched_create  # type: ignore[method-assign]
    return repo


@pytest.fixture
async def app():
    import uuid as _uuid
    app = Sanic(f"test_prompts_app_{_uuid.uuid4().hex[:8]}")
    app.blueprint(prompt_bp)
    audit = AuditLogService(MemoryAuditLogRepository())
    repo = _patch_repo_timestamps(MemoryPromptRepository())
    svc = PromptService(repo, audit)

    class C:  # noqa: D401 — minimal stand-in for ServiceContainer
        pass

    c = C()
    c.prompt = svc
    app.ctx.service_container = c

    async def fake_actor_mw(request):
        request.ctx.actor = ActorContext(
            user_id=request.headers.get("X-User-Id", "anonymous"),
        )

    app.register_middleware(fake_actor_mw, "request")
    return app


@pytest.mark.asyncio
async def test_create_then_get_prompt(app):
    client = app.asgi_client
    _, r = await client.post(
        "/agent/prompts/",
        json={
            "code": "hi",
            "name": "Hi",
            "description": "test",
            "content": "say hi",
        },
        headers={"X-User-Id": "alice"},
    )
    assert r.status == 201
    assert r.json["owner_user_id"] == "alice"
    _, r2 = await client.get("/agent/prompts/hi")
    assert r2.status == 200
    assert r2.json["content"] == "say hi"


@pytest.mark.asyncio
async def test_publish_makes_visible_to_others(app):
    client = app.asgi_client
    _, r = await client.post(
        "/agent/prompts/",
        json={"code": "shared", "name": "S", "content": "c"},
        headers={"X-User-Id": "alice"},
    )
    assert r.status == 201
    _, r2 = await client.post(
        "/agent/prompts/shared/publish",
        json={"visibility": "public"},
        headers={"X-User-Id": "alice"},
    )
    assert r2.status == 200
    _, r3 = await client.get(
        "/agent/prompts/", headers={"X-User-Id": "bob"},
    )
    codes = [p["code"] for p in r3.json["items"]]
    assert "shared" in codes


@pytest.mark.asyncio
async def test_publish_denies_non_owner(app):
    client = app.asgi_client
    _, r0 = await client.post(
        "/agent/prompts/",
        json={"code": "private-x", "name": "P", "content": "c"},
        headers={"X-User-Id": "alice"},
    )
    assert r0.status == 201
    _, r = await client.post(
        "/agent/prompts/private-x/publish",
        json={"visibility": "public"},
        headers={"X-User-Id": "bob"},
    )
    assert r.status == 403
    assert r.json["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_get_missing_prompt_returns_404(app):
    client = app.asgi_client
    _, r = await client.get("/agent/prompts/nope")
    assert r.status == 404
    assert r.json["code"] == "PROMPT_NOT_FOUND"


@pytest.mark.asyncio
async def test_create_duplicate_returns_409(app):
    client = app.asgi_client
    _, r0 = await client.post(
        "/agent/prompts/",
        json={"code": "dup", "name": "D", "content": "x"},
        headers={"X-User-Id": "alice"},
    )
    assert r0.status == 201
    _, r1 = await client.post(
        "/agent/prompts/",
        json={"code": "dup", "name": "D2", "content": "x"},
        headers={"X-User-Id": "alice"},
    )
    assert r1.status == 409
    assert r1.json["code"] == "DUPLICATE_PROMPT"


@pytest.mark.asyncio
async def test_community_lists_only_public(app):
    client = app.asgi_client
    _, _ = await client.post(
        "/agent/prompts/",
        json={"code": "p1", "name": "P1", "content": "x"},
        headers={"X-User-Id": "alice"},
    )
    _, r_pub = await client.post(
        "/agent/prompts/",
        json={"code": "p2", "name": "P2", "content": "x"},
        headers={"X-User-Id": "alice"},
    )
    assert r_pub.status == 201
    _, r_publish = await client.post(
        "/agent/prompts/p2/publish",
        json={"visibility": "public"},
        headers={"X-User-Id": "alice"},
    )
    assert r_publish.status == 200

    _, r = await client.get("/agent/prompts/community")
    assert r.status == 200
    codes = [p["code"] for p in r.json["items"]]
    assert "p2" in codes
    assert "p1" not in codes
