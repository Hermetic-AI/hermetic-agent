"""Tests for WorkTrace Repository implementations (Memory + MySQL).

Run with::

    pytest tests/test_work_trace_store.py -v

默认只跑 Memory 类 (无外部 DB 依赖); MySQL 类用 pytest.mark.skip 守门。
"""

from __future__ import annotations

import pytest

from hermetic_agent.store.dto.work_trace import (
    AppendTraceEventsRequest,
    MarkTraceStatusRequest,
    TraceEventResponse,
)
from hermetic_agent.store.repositories.memory.work_trace_repo_memory import (
    MemoryWorkTraceRepository,
)

TID = "0190a8e1-aaaa-bbbb-cccc-ddddeeeeffff"
TID2 = "0190a8e1-ffff-eeee-dddd-ccccbbbbbbaa"
SID = "0190a8c0-aaaa-bbbb-cccc-ddddeeeeffff"


@pytest.fixture
def repo():
    r = MemoryWorkTraceRepository()
    yield r
    r.clear()


async def test_append_events_creates_turn(repo):
    req = AppendTraceEventsRequest(
        turn_id=TID, session_id=SID, scenario="flight_booking",
        events=[TraceEventResponse(seq=1, at="2026-06-30T08:00:00Z", kind="scenario",
                                   payload={"name": "flight_booking"})],
    )
    t = await repo.append_events(req)
    assert str(t.turn_id) == TID
    assert t.status == "running"
    assert len(t.events) == 1


async def test_append_events_appends_to_existing(repo):
    req1 = AppendTraceEventsRequest(
        turn_id=TID, session_id=SID,
        events=[TraceEventResponse(seq=1, at="2026-06-30T08:00:00Z", kind="state",
                                   payload={"from": "S00", "to": "S01"})],
    )
    req2 = AppendTraceEventsRequest(
        turn_id=TID, session_id=SID,
        events=[TraceEventResponse(seq=2, at="2026-06-30T08:00:01Z", kind="state",
                                   payload={"from": "S01", "to": "S02"})],
    )
    await repo.append_events(req1)
    t = await repo.append_events(req2)
    assert len(t.events) == 2
    assert t.events[1]["payload"]["to"] == "S02"


async def test_append_events_dedups_by_seq(repo):
    req1 = AppendTraceEventsRequest(
        turn_id=TID, session_id=SID,
        events=[TraceEventResponse(seq=1, at="2026-06-30T08:00:00Z", kind="state", payload={})],
    )
    req2 = AppendTraceEventsRequest(
        turn_id=TID, session_id=SID,
        events=[TraceEventResponse(seq=1, at="2026-06-30T08:00:00Z", kind="state", payload={})],
    )
    await repo.append_events(req1)
    t = await repo.append_events(req2)
    assert len(t.events) == 1


async def test_mark_status_sets_finished_at(repo):
    await repo.append_events(AppendTraceEventsRequest(turn_id=TID, session_id=SID, events=[]))
    t = await repo.mark_status(TID, MarkTraceStatusRequest(status="done"))
    assert t is not None
    assert t.status == "done"
    assert t.finished_at is not None


async def test_mark_status_missing_returns_none(repo):
    t = await repo.mark_status("nonexistent-id", MarkTraceStatusRequest(status="done"))
    assert t is None


async def test_list_by_session_returns_indexes(repo):
    for tid in [TID, TID2]:
        await repo.append_events(AppendTraceEventsRequest(
            turn_id=tid, session_id=SID, scenario="flight_booking",
            events=[TraceEventResponse(seq=1, at="2026-06-30T08:00:00Z", kind="scenario", payload={})],
        ))
    items = await repo.list_by_session(SID, limit=10)
    assert len(items) == 2
    assert {i.turn_id for i in items} == {TID, TID2}


async def test_list_by_session_respects_limit(repo):
    for i in range(5):
        tid = f"0190a8e1-{i:04x}-eeee-dddd-ccccbbbbbbaa"
        await repo.append_events(AppendTraceEventsRequest(
            turn_id=tid, session_id=SID, scenario=None,
            events=[TraceEventResponse(seq=1, at="2026-06-30T08:00:00Z", kind="state", payload={})],
        ))
    items = await repo.list_by_session(SID, limit=3)
    assert len(items) == 3


async def test_get_by_turn_returns_none_when_missing(repo):
    assert await repo.get_by_turn("nonexistent-id") is None


async def test_append_merges_summary(repo):
    req1 = AppendTraceEventsRequest(turn_id=TID, session_id=SID, events=[], summary={"a": 1})
    req2 = AppendTraceEventsRequest(turn_id=TID, session_id=SID, events=[], summary={"b": 2})
    await repo.append_events(req1)
    t = await repo.append_events(req2)
    assert t.summary == {"a": 1, "b": 2}