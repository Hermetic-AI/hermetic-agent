"""Tests for /agent/skills/<code>/files/* endpoints (L1 SkillFilesController).

Uses Sanic ``asgi_client`` for in-process HTTP, with MemorySkillFiles as
the backend (no MinIO required). Mirrors the production wiring where
``app.ctx.asset_clients`` is set in ``lifecycle.startup()``.
"""
from __future__ import annotations

import base64
import tempfile
from pathlib import Path

import pytest
from sanic import Sanic

from hermetic_agent.api.http.controllers.skill_files_controller import skill_files_bp
from hermetic_agent.store.dto._common import ActorContext
from hermetic_agent.store.object.memory_skill_files import MemorySkillFiles


@pytest.fixture
async def app():
    with tempfile.TemporaryDirectory() as tmp:
        sf = MemorySkillFiles(Path(tmp))
        app = Sanic("test_skill_files_app")
        app.blueprint(skill_files_bp)
        app.ctx.asset_clients = {"minio": None, "skill_files": sf}

        async def fake_actor_mw(request):
            request.ctx.actor = ActorContext(
                user_id=request.headers.get("X-User-Id", "alice"))

        app.register_middleware(fake_actor_mw, "request")
        yield app


@pytest.mark.asyncio
async def test_upload_then_download(app):
    body = b"hello world"
    _, r = await app.asgi_client.put(
        "/agent/skills/sample/files/SKILL.md",
        headers={"X-User-Id": "alice",
                 "Content-Type": "application/octet-stream"},
        data=body,
    )
    assert r.status == 201
    assert r.json["code"] == "sample"
    assert r.json["path"] == "SKILL.md"

    _, r2 = await app.asgi_client.get("/agent/skills/sample/files/SKILL.md")
    assert r2.status == 200
    assert base64.b64decode(r2.json["content_b64"]) == body


@pytest.mark.asyncio
async def test_list_files(app):
    client = app.asgi_client
    _, r1 = await client.put(
        "/agent/skills/lst/files/a.md",
        headers={"X-User-Id": "alice"},
        data=b"AAA",
    )
    assert r1.status == 201
    _, r2 = await client.put(
        "/agent/skills/lst/files/sub/b.md",
        headers={"X-User-Id": "alice"},
        data=b"BBBB",
    )
    assert r2.status == 201
    _, r = await client.get("/agent/skills/lst/files")
    assert r.status == 200
    paths = sorted(item["path"] for item in r.json["items"])
    assert paths == ["a.md", "sub/b.md"]
    assert r.json["total"] == 2


@pytest.mark.asyncio
async def test_delete_file(app):
    client = app.asgi_client
    _, r1 = await client.put(
        "/agent/skills/del/files/SKILL.md",
        headers={"X-User-Id": "alice"},
        data=b"x",
    )
    assert r1.status == 201
    _, r = await client.delete("/agent/skills/del/files/SKILL.md")
    assert r.status == 200
    assert r.json["success"] is True
    _, r2 = await client.get("/agent/skills/del/files/SKILL.md")
    assert r2.status == 404


@pytest.mark.asyncio
async def test_get_missing_returns_404(app):
    _, r = await app.asgi_client.get("/agent/skills/none/files/SKILL.md")
    assert r.status == 404
    assert r.json["code"] == "FILE_NOT_FOUND"


@pytest.mark.asyncio
async def test_batch_upload(app):
    client = app.asgi_client
    payload = {
        "files": [
            {"path": "a.md", "content_b64": base64.b64encode(b"A").decode()},
            {"path": "b.md", "content_b64": base64.b64encode(b"BB").decode()},
        ],
    }
    _, r = await client.post(
        "/agent/skills/bat/files/batch",
        json=payload,
        headers={"X-User-Id": "alice"},
    )
    assert r.status == 200
    assert r.json["code"] == "bat"
    ok_results = [x for x in r.json["results"] if x["ok"]]
    assert len(ok_results) == 2


@pytest.mark.asyncio
async def test_batch_too_many_returns_413(app):
    client = app.asgi_client
    files = [
        {"path": f"f{i}.md", "content_b64": base64.b64encode(b"x").decode()}
        for i in range(9)
    ]
    _, r = await client.post(
        "/agent/skills/bat/files/batch",
        json={"files": files},
        headers={"X-User-Id": "alice"},
    )
    assert r.status == 413
    assert r.json["code"] == "VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_path_traversal_rejected(app):
    _, r = await app.asgi_client.put(
        "/agent/skills/sample/files/..%2Fetc%2Fpasswd",
        headers={"X-User-Id": "alice"},
        data=b"x",
    )
    assert r.status in (400, 404)