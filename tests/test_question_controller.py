"""tests/test_question_controller.py — P7: /agent/questions/* 端点.

每个测试用独立 ``Sanic(f"test-question-{uuid}")`` 实例避免 Sanic
app name 冲突, 单独注册 question_bp, 桥接 / adapter 用 mock。
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from sanic import Sanic

from openagent.api.controllers.question_controller import question_bp
from openagent.config.settings import Settings


class _FakeAdapter:
    """持久 _clients 字典, 模拟 ``get_client(adapter, agent, base_url)`` 的缓存行为."""

    def __init__(self, session_info):
        self._session_info = session_info
        # 持久 dict, get_client 会按 ``agent:base_url`` 键写入再读出
        self._clients: dict = {}

    async def get_session(self, session_id: str):
        return self._session_info if session_id == self._session_info.session_id else None


@pytest.fixture
def fake_session():
    info = MagicMock()
    info.session_id = "ses_q1"
    info.agent_name = "opencode-core"
    info.agent_base_url = "http://localhost:4096"
    info.directory = "/work/proj"
    return info


@pytest.fixture
def app(fake_session):
    """独立 Sanic app, 注册 question_bp, 注入 mock bridge."""
    app = Sanic(f"test-question-{uuid.uuid4().hex[:8]}")
    app.blueprint(question_bp)

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


def _wire_opencode_client(adapter: _FakeAdapter, fake_client: MagicMock) -> None:
    """把 fake_client 写进 adapter._clients 缓存, 让 get_client 返回 mock."""
    adapter._clients["opencode-core:http://localhost:4096"] = fake_client


def _make_question_response(requests: list[dict]) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.content = b"non-empty"
    resp.json.return_value = requests
    return resp


def _make_status_response(status: int) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.content = b"true" if status == 200 else b"err"
    return resp


# ---------------------------------------------------------------------------
# GET /agent/questions
# ---------------------------------------------------------------------------


def test_list_questions_missing_session_id(app):
    s_app, _, _ = app
    _, resp = s_app.test_client.get("/agent/questions")
    assert resp.status_code == 400
    assert "session_id" in resp.json["error"]


def test_list_questions_session_not_found():
    """agent 没注册时返 404."""
    s_app = Sanic(f"test-q-noagent-{uuid.uuid4().hex[:8]}")
    s_app.blueprint(question_bp)
    bridge = MagicMock()
    bridge.get_agent_for_session = MagicMock(return_value=None)
    s_app.ctx.bridge = bridge
    _, resp = s_app.test_client.get("/agent/questions?session_id=ses_missing")
    assert resp.status_code == 404


def test_list_questions_filters_by_session_id(app):
    s_app, _, _ = app
    fake_client = MagicMock()
    fake_client.get = AsyncMock(return_value=_make_question_response([
        {"id": "q1", "sessionID": "ses_q1", "questions": [{"question": "Q1", "header": "h", "options": []}]},
        {"id": "q2", "sessionID": "ses_other", "questions": []},
    ]))
    _wire_opencode_client(app[2], fake_client)

    _, resp = s_app.test_client.get("/agent/questions?session_id=ses_q1")
    assert resp.status_code == 200
    body = resp.json
    assert body["success"] is True
    assert len(body["questions"]) == 1
    assert body["questions"][0]["id"] == "q1"
    call = fake_client.get.await_args
    assert call.args[0] == "/question"


def test_list_questions_returns_empty_on_empty_response(app):
    s_app, _, _ = app
    fake_client = MagicMock()
    fake_client.get = AsyncMock(return_value=_make_question_response([]))
    _wire_opencode_client(app[2], fake_client)
    _, resp = s_app.test_client.get("/agent/questions?session_id=ses_q1")
    assert resp.status_code == 200
    assert resp.json["questions"] == []


# ---------------------------------------------------------------------------
# POST /agent/questions/{id}/reply
# ---------------------------------------------------------------------------


def test_reply_missing_session_id(app, fake_session):
    s_app, _, _ = app
    fake_client = MagicMock()
    fake_client.post = AsyncMock(return_value=_make_status_response(200))
    _wire_opencode_client(app[2], fake_client)
    _, resp = s_app.test_client.post(
        "/agent/questions/que_1/reply",
        data=json.dumps({"answers": [["a"]]}),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400
    assert "session_id" in resp.json["error"]


def test_reply_missing_answers(app):
    s_app, _, _ = app
    _, resp = s_app.test_client.post(
        "/agent/questions/que_1/reply",
        data=json.dumps({"session_id": "ses_q1"}),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400
    assert "answers" in resp.json["error"]


def test_reply_bad_answers_shape(app):
    s_app, _, _ = app
    _, resp = s_app.test_client.post(
        "/agent/questions/que_1/reply",
        data=json.dumps({"session_id": "ses_q1", "answers": "not a list"}),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400
    assert "list of lists" in resp.json["error"]


def test_reply_success(app):
    s_app, _, _ = app
    fake_client = MagicMock()
    fake_client.post = AsyncMock(return_value=_make_status_response(200))
    _wire_opencode_client(app[2], fake_client)
    _, resp = s_app.test_client.post(
        "/agent/questions/que_1/reply",
        data=json.dumps({"session_id": "ses_q1", "answers": [["单程"], ["经济舱"]]}),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    body = resp.json
    assert body["success"] is True
    assert body["replied"] is True
    call = fake_client.post.await_args
    assert call.args[0] == "/question/que_1/reply"
    assert call.kwargs["body"] == {"answers": [["单程"], ["经济舱"]]}


def test_reply_retries_without_directory_on_not_found(app):
    """兼容旧 session: question 创建在默认 directory 时, 带 workspace reply 404 后无目录重试。"""
    s_app, _, _ = app
    fake_client = MagicMock()
    fake_client.post = AsyncMock(
        side_effect=[
            httpx.HTTPStatusError(
                "404",
                request=httpx.Request("POST", "http://localhost/question/que_1/reply"),
                response=httpx.Response(404),
            ),
            _make_status_response(200),
        ]
    )
    _wire_opencode_client(app[2], fake_client)

    _, resp = s_app.test_client.post(
        "/agent/questions/que_1/reply",
        data=json.dumps({"session_id": "ses_q1", "answers": [["明天出发"]]}),
        headers={"Content-Type": "application/json"},
    )

    assert resp.status_code == 200
    assert resp.json["replied"] is True
    calls = fake_client.post.await_args_list
    assert calls[0].kwargs["options"]["extra_query"] == {"directory": "/work/proj"}
    assert calls[1].kwargs["options"] == {}


# ---------------------------------------------------------------------------
# POST /agent/questions/{id}/reject
# ---------------------------------------------------------------------------


def test_reject_missing_session_id(app):
    s_app, _, _ = app
    _, resp = s_app.test_client.post(
        "/agent/questions/que_1/reject",
        data=json.dumps({}),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400


def test_reject_success(app):
    s_app, _, _ = app
    fake_client = MagicMock()
    fake_client.post = AsyncMock(return_value=_make_status_response(200))
    _wire_opencode_client(app[2], fake_client)
    _, resp = s_app.test_client.post(
        "/agent/questions/que_1/reject",
        data=json.dumps({"session_id": "ses_q1"}),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json["rejected"] is True
    call = fake_client.post.await_args
    assert call.args[0] == "/question/que_1/reject"
    assert call.kwargs["body"] == {}
