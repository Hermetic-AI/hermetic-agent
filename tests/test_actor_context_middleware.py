"""Tests for ActorContextMiddleware (L1).

The middleware reads identity headers from the request and populates
``request.ctx.actor`` with an ``ActorContext`` dataclass. Controllers
later read ``request.ctx.actor.user_id`` for permission checks.

These tests use Sanic's in-process ``asgi_client`` (no real socket,
httpx under the hood) and do not touch external services.
"""
from __future__ import annotations

import pytest
from sanic import Sanic
from sanic.response import JSONResponse

from hermetic_agent.api.http.middleware.actor_context import ActorContextMiddleware
from hermetic_agent.store.dto._common import ActorContext


@pytest.mark.asyncio
async def test_middleware_extracts_user_id_header():
    app = Sanic("test_actor_mw")
    seen: list[ActorContext] = []

    @app.get("/probe")
    async def probe(request):
        seen.append(request.ctx.actor)
        return JSONResponse({"ok": True})

    ActorContextMiddleware(app)
    _, response = await app.asgi_client.get("/probe", headers={"X-User-Id": "alice"})
    assert response.status == 200
    assert seen[0].user_id == "alice"
    assert seen[0].is_anonymous() is False


@pytest.mark.asyncio
async def test_anonymous_when_no_header():
    app = Sanic("test_actor_mw_anon")
    seen: list[ActorContext] = []

    @app.get("/probe")
    async def probe(request):
        seen.append(request.ctx.actor)
        return JSONResponse({"ok": True})

    ActorContextMiddleware(app)
    _, response = await app.asgi_client.get("/probe")
    assert seen[0].user_id == "anonymous"
    assert seen[0].is_anonymous()
