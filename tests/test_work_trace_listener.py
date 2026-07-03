"""Tests for WorkTraceListener — one-way sink contract."""

from __future__ import annotations

import pytest

from hermetic_agent.api.http.streaming.work_trace_listener import WorkTraceListener
from hermetic_agent.providers.streaming import StreamEvent
from hermetic_agent.store.repositories.memory.work_trace_repo_memory import (
    MemoryWorkTraceRepository,
)
from hermetic_agent.store.services.work_trace_service import WorkTraceService

TID = "11111111-2222-3333-4444-555555555555"
SID = "99999999-8888-7777-6666-555555555555"


@pytest.fixture
def listener():
    repo = MemoryWorkTraceRepository()
    svc = WorkTraceService(repo)
    return WorkTraceListener(
        turn_id=TID, session_id=SID, scenario="flight_booking", service=svc,
    )


def test_listener_initializes_seq_at_zero(listener):
    assert listener.state.seq == 0


def test_listener_creates_turn_on_first_event(listener):
    listener.on_event(StreamEvent.scenario("flight_booking", matched_by="kw"))
    assert listener.state.seq == 1


def test_listener_appends_multiple_events(listener):
    listener.on_event(StreamEvent.scenario("flight_booking"))
    listener.on_event(StreamEvent(type="state", data={"from": "S00", "to": "S01"}))
    listener.on_event(StreamEvent.tool_use("query_flight_basic", {"from": "BJ"}))
    listener.on_event(StreamEvent.tool_result("query_flight_basic", {"flights": 10}))
    assert listener.state.seq == 4


def test_listener_text_event_does_not_increment_seq(listener):
    listener.on_event(StreamEvent.text("hi"))
    listener.on_event(StreamEvent.reasoning("because"))
    listener.on_event(StreamEvent.done())
    assert listener.state.seq == 0


async def test_listener_persists_to_store(listener):
    listener.on_event(StreamEvent.scenario("flight_booking"))
    await listener.flush()
    resp = await listener._service.get_response(TID)
    assert resp is not None
    assert len(resp.events) == 1
    assert resp.events[0].kind == "scenario"


async def test_listener_persists_multiple_events(listener):
    listener.on_event(StreamEvent.scenario("flight_booking"))
    listener.on_event(StreamEvent(type="state", data={"from": "S00", "to": "S01"}))
    listener.on_event(StreamEvent.tool_use("t1", {"a": 1}))
    await listener.flush()
    resp = await listener._service.get_response(TID)
    assert resp is not None
    assert len(resp.events) == 3


async def test_listener_mark_done_finalizes(listener):
    listener.on_event(StreamEvent.scenario("flight_booking"))
    await listener.mark_done()
    resp = await listener._service.get_response(TID)
    assert resp is not None
    assert resp.status == "done"
    assert resp.finished_at is not None


async def test_listener_mark_error_finalizes_with_error_status(listener):
    listener.on_event(StreamEvent.scenario("flight_booking"))
    await listener.mark_error("boom")
    resp = await listener._service.get_response(TID)
    assert resp is not None
    assert resp.status == "error"


async def test_listener_finalize_is_idempotent(listener):
    listener.on_event(StreamEvent.scenario("flight_booking"))
    await listener.mark_done()
    await listener.mark_done()
    await listener.mark_error("ignored")
    resp = await listener._service.get_response(TID)
    assert resp.status == "done"


async def test_listener_handles_listener_error_gracefully(monkeypatch):
    repo = MemoryWorkTraceRepository()
    svc = WorkTraceService(repo)
    listener = WorkTraceListener(turn_id=TID, session_id=SID, scenario=None, service=svc)

    async def _boom(*_a, **_kw):
        raise RuntimeError("store down")

    monkeypatch.setattr(svc, "append", _boom)
    # Should NOT raise — listener must keep chat flow alive
    listener.on_event(StreamEvent.scenario("flight_booking"))
    await listener.flush()
    await listener.mark_done()


async def test_listener_reducer_error_does_not_raise(monkeypatch):
    """如果 reducer 抛错, listener 吞掉, seq 继续 + 不影响后续 event."""
    repo = MemoryWorkTraceRepository()
    svc = WorkTraceService(repo)
    listener = WorkTraceListener(turn_id=TID, session_id=SID, scenario=None, service=svc)

    from hermetic_agent.auip.work_trace_reducer import reduce_event

    def _boom(*_a, **_kw):
        raise RuntimeError("reducer exploded")

    monkeypatch.setattr(
        "hermetic_agent.api.http.streaming.work_trace_listener.reduce_event",
        _boom,
    )
    listener.on_event(StreamEvent.scenario("flight_booking"))
    listener.on_event(StreamEvent(type="state", data={"from": "S00", "to": "S01"}))
    # reducer 抛错 → seq 不增加 (state 在 reduce 内被改) → events list 空
    assert listener.state.seq == 0