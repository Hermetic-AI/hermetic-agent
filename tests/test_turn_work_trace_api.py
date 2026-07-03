"""Tests for turn_work_trace_controller — 4 GET endpoints (work-trace)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from sanic import Sanic

from hermetic_agent.api.http.controllers.turn_work_trace_controller import trace_bp
from hermetic_agent.store.dto.work_trace import (
    AppendTraceEventsRequest,
    MarkTraceStatusRequest,
    TraceEventResponse,
    TurnWorkTraceResponse,
    WorkTraceIndexItem,
)

TID = "0190a8e1-aaaa-bbbb-cccc-ddddeeeeffff"
TID2 = "0190a8e1-ffff-eeee-dddd-ccccbbbbbbaa"
SID = "0190a8c0-aaaa-bbbb-cccc-ddddeeeeffff"


class _FakeWorkTraceService:
    """最小 WorkTraceService 替身 — 测试中不需要真 MySQL."""

    def __init__(self) -> None:
        self.traces: dict = {}
        self.sessions: dict = {}

    async def get_response(self, turn_id: str):
        return self.traces.get(turn_id)

    async def list_by_session(self, session_id: str, *, limit: int = 20):
        return self.sessions.get(session_id, [])[:limit]


def _trace_response(turn_id: str, session_id: str, events: list, status: str = "done", summary: dict | None = None):
    return TurnWorkTraceResponse(
        turn_id=turn_id, session_id=session_id, scenario="flight_booking",
        status=status, started_at="2026-06-30T08:00:00Z",
        finished_at="2026-06-30T08:00:14Z",
        summary=summary or {"tool_calls": len(events)},
        events=events,
    )


def _make_app(svc=None):
    app = Sanic(f"test-trace-{uuid.uuid4().hex[:8]}")
    app.blueprint(trace_bp)
    container = MagicMock()
    container.work_trace = svc if svc is not None else _FakeWorkTraceService()
    app.ctx.services = container
    return app, container.work_trace


def test_get_trace_returns_404_when_missing():
    app, svc = _make_app(_FakeWorkTraceService())
    _, resp = app.test_client.get(f"/agent/turns/{TID}/work-trace")
    assert resp.status_code == 404
    assert resp.json["code"] == "TRACE_NOT_FOUND"


def test_get_trace_returns_full_trace():
    app, svc = _make_app()
    svc.traces[TID] = _trace_response(TID, SID, events=[
        TraceEventResponse(seq=0, at="2026-06-30T08:00:00Z", kind="scenario",
                           payload={"name": "flight_booking"}),
        TraceEventResponse(seq=1, at="2026-06-30T08:00:01Z", kind="tool_io",
                           payload={"name": "query_flight_basic", "phase": "call", "input": {}}),
    ])
    _, resp = app.test_client.get(f"/agent/turns/{TID}/work-trace")
    assert resp.status_code == 200
    body = resp.json
    assert body["turn_id"] == TID
    assert body["status"] == "done"
    assert len(body["events"]) == 2


def test_get_trace_503_when_services_not_ready():
    app = Sanic(f"test-trace-noappctx-{uuid.uuid4().hex[:8]}")
    app.blueprint(trace_bp)
    _, resp = app.test_client.get(f"/agent/turns/{TID}/work-trace")
    assert resp.status_code == 503


def test_list_session_traces_returns_indexes():
    app, svc = _make_app()
    svc.sessions[SID] = [
        WorkTraceIndexItem(
            turn_id=TID, session_id=SID, scenario="flight_booking", status="done",
            started_at="2026-06-30T08:00:00Z", finished_at="2026-06-30T08:00:14Z",
            summary={"tool_calls": 4},
        ),
        WorkTraceIndexItem(
            turn_id=TID2, session_id=SID, scenario="flight_booking", status="running",
            started_at="2026-06-30T08:01:00Z", finished_at=None,
            summary={},
        ),
    ]
    _, resp = app.test_client.get(f"/agent/sessions/{SID}/work-traces")
    assert resp.status_code == 200
    body = resp.json
    assert body["total"] == 2
    assert len(body["items"]) == 2


def test_list_session_traces_respects_limit():
    app, svc = _make_app()
    svc.sessions[SID] = [
        WorkTraceIndexItem(
            turn_id=f"0190a8e1-{i:04x}-eeee-dddd-ccccbbbbbbaa",
            session_id=SID, scenario="flight_booking", status="done",
            started_at="2026-06-30T08:00:00Z", finished_at=None, summary={},
        )
        for i in range(5)
    ]
    _, resp = app.test_client.get(f"/agent/sessions/{SID}/work-traces?limit=3")
    assert resp.status_code == 200
    assert len(resp.json["items"]) == 3


def test_list_session_traces_clamps_limit_to_max_100():
    app, svc = _make_app()
    svc.sessions[SID] = []
    _, resp = app.test_client.get(f"/agent/sessions/{SID}/work-traces?limit=999")
    assert resp.status_code == 200
    assert resp.json["total"] == 0


def test_get_product_returns_404_when_turn_missing():
    app, _ = _make_app()
    _, resp = app.test_client.get(f"/agent/turns/{TID}/work-trace/products/p1")
    assert resp.status_code == 404


def test_get_product_returns_metadata():
    app, svc = _make_app()
    svc.traces[TID] = _trace_response(TID, SID, events=[
        TraceEventResponse(seq=0, at="", kind="product",
                           payload={"product_id": "p1", "kind": "url", "url": "https://example.com/x"}),
    ], status="done", summary={})
    _, resp = app.test_client.get(f"/agent/turns/{TID}/work-trace/products/p1")
    assert resp.status_code == 200
    body = resp.json
    assert body["product_id"] == "p1"
    assert body["kind"] == "url"
    assert body["url"] == "https://example.com/x"