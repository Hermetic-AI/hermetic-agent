"""tests/test_todo_controller.py — P7: /agent/sessions/{id}/todo 端点."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from sanic import Sanic

from hermetic_agent.api.http.controllers.todo_controller import todo_bp
from hermetic_agent.config.settings import Settings


class _FakeAdapter:
    def __init__(self, session_info):
        self._session_info = session_info
        # 持久 dict, 让 opencode_chat.get_client 能按 ``agent:base_url`` 键缓存
        self._clients: dict = {}

    async def get_session(self, session_id: str):
        return self._session_info if session_id == self._session_info.session_id else None


@pytest.fixture
def fake_session():
    info = MagicMock()
    info.session_id = "ses_t1"
    info.agent_name = "opencode-core"
    info.agent_base_url = "http://localhost:4096"
    info.directory = "/work/proj"
    return info


@pytest.fixture
def app(fake_session):
    app = Sanic(f"test-todo-{uuid.uuid4().hex[:8]}")
    app.blueprint(todo_bp)
    bridge = MagicMock()
    adapter = _FakeAdapter(fake_session)
    bridge.get_agent_for_session = MagicMock(return_value="opencode-core")
    bridge.get_provider = MagicMock(return_value=adapter)
    app.ctx.bridge = bridge
    app.ctx.settings = Settings(
        opencode_base_url="http://localhost:4096",
        log_level="WARNING",
        log_format="text",
    )
    return app, bridge, adapter


def _wire_client(adapter, fake_client):
    adapter._clients["opencode-core:http://localhost:4096"] = fake_client


def _make_todo_response(todos):
    resp = MagicMock(spec=httpx.Response)
    resp.content = b"non-empty"
    resp.json.return_value = todos
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_list_todos_session_not_found():
    """agent 不存在时返 404."""
    app = Sanic(f"test-todo-noagent-{uuid.uuid4().hex[:8]}")
    app.blueprint(todo_bp)
    bridge = MagicMock()
    bridge.get_agent_for_session = MagicMock(return_value=None)
    app.ctx.bridge = bridge
    _, resp = app.test_client.get("/agent/sessions/ses_missing/todo")
    assert resp.status_code == 404


def test_list_todos_success(app):
    s_app, _, adapter = app
    fake_client = MagicMock()
    fake_client.get = AsyncMock(return_value=_make_todo_response([
        {"content": "T1", "status": "in_progress", "priority": "high"},
        {"content": "T2", "status": "pending", "priority": "low"},
    ]))
    _wire_client(adapter, fake_client)
    _, resp = s_app.test_client.get("/agent/sessions/ses_t1/todo")
    assert resp.status_code == 200
    body = resp.json
    assert body["success"] is True
    assert body["session_id"] == "ses_t1"
    assert len(body["todos"]) == 2
    call = fake_client.get.await_args
    assert call.args[0] == "/session/ses_t1/todo"


def test_list_todos_empty(app):
    s_app, _, adapter = app
    fake_client = MagicMock()
    fake_client.get = AsyncMock(return_value=_make_todo_response([]))
    _wire_client(adapter, fake_client)
    _, resp = s_app.test_client.get("/agent/sessions/ses_t1/todo")
    assert resp.status_code == 200
    assert resp.json["todos"] == []


def test_list_todos_opencode_error_returns_502(app):
    s_app, _, adapter = app
    fake_client = MagicMock()
    fake_client.get = AsyncMock(side_effect=RuntimeError("opencode unreachable"))
    _wire_client(adapter, fake_client)
    _, resp = s_app.test_client.get("/agent/sessions/ses_t1/todo")
    assert resp.status_code == 502
    assert "opencode" in resp.json["error"]


def test_list_todos_no_provider(app):
    s_app, bridge, _ = app
    bridge.get_provider = MagicMock(return_value=None)
    _, resp = s_app.test_client.get("/agent/sessions/ses_t1/todo")
    assert resp.status_code == 404
