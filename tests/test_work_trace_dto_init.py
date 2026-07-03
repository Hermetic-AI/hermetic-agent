"""Tests for WorkTrace DTO init + serialization."""

from __future__ import annotations

from hermetic_agent.store.dto.work_trace import (
    AppendTraceEventsRequest,
    TraceEventResponse,
    TurnWorkTraceResponse,
    WorkTraceIndexItem,
)


def test_append_trace_events_request_round_trip():
    req = AppendTraceEventsRequest(
        turn_id="0190a8e1-1111-2222-3333-444455556666",
        session_id="0190a8c0-1111-2222-3333-444455556666",
        scenario="flight_booking",
        events=[
            TraceEventResponse(
                seq=1, at="2026-06-30T08:00:00Z", kind="scenario",
                payload={"name": "flight_booking", "version": "1.2.0", "matched_by": "keyword"},
            )
        ],
    )
    dumped = req.model_dump()
    assert dumped["turn_id"] == "0190a8e1-1111-2222-3333-444455556666"
    assert dumped["events"][0]["kind"] == "scenario"
    assert dumped["events"][0]["payload"]["matched_by"] == "keyword"


def test_trace_event_payload_is_dict():
    evt = TraceEventResponse(
        seq=2, at="2026-06-30T08:00:01Z", kind="state",
        payload={"from": "S00", "to": "S01"},
    )
    assert isinstance(evt.payload, dict)


def test_index_item_minimal():
    item = WorkTraceIndexItem(
        turn_id="t1", session_id="s1", scenario=None, status="running",
        started_at="2026-06-30T08:00:00Z", finished_at=None, summary={},
    )
    assert item.finished_at is None
    assert item.scenario is None


def test_trace_event_response_seq_ge_zero():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TraceEventResponse(seq=-1, at="2026-06-30T08:00:00Z", kind="state", payload={})


def test_append_request_default_events_empty():
    req = AppendTraceEventsRequest(
        turn_id="0190a8e1-aaaa-bbbb-cccc-ddddeeeeffff",
        session_id="0190a8c0-aaaa-bbbb-cccc-ddddeeeeffff",
    )
    assert req.events == []
    assert req.scenario is None


def test_turn_work_trace_response_full():
    resp = TurnWorkTraceResponse(
        turn_id="0190a8e1-aaaa-bbbb-cccc-ddddeeeeffff",
        session_id="0190a8c0-aaaa-bbbb-cccc-ddddeeeeffff",
        scenario="flight_booking",
        status="done",
        started_at="2026-06-30T08:00:00Z",
        finished_at="2026-06-30T08:00:14Z",
        summary={"tool_calls": 4},
        events=[
            TraceEventResponse(seq=1, at="2026-06-30T08:00:00Z", kind="scenario",
                               payload={"name": "flight_booking"}),
            TraceEventResponse(seq=2, at="2026-06-30T08:00:01Z", kind="state",
                               payload={"from": "S00", "to": "S01"}),
        ],
    )
    dumped = resp.model_dump()
    assert dumped["summary"]["tool_calls"] == 4
    assert len(dumped["events"]) == 2