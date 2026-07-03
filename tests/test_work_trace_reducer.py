"""Tests for work_trace_reducer — 8 SSE event kinds → TraceEvent."""

from __future__ import annotations

from hermetic_agent.auip.work_trace_reducer import (
    ReducerContext,
    ReducerState,
    reduce_event,
    redact_value,
)
from hermetic_agent.providers.streaming import StreamEvent


CTX = ReducerContext(
    turn_id="t1", session_id="s1", scenario="flight_booking", seq=0,
    started_at="2026-06-30T08:00:00Z",
)


def test_scenario_event_passes_through():
    ev = StreamEvent.scenario("flight_booking", version="1.2.0", matched_by="keyword")
    out = reduce_event(ev, CTX)
    assert len(out) == 1
    assert out[0].kind == "scenario"
    assert out[0].payload["name"] == "flight_booking"
    assert out[0].payload["matched_by"] == "keyword"


def test_state_event_passes_through():
    ev = StreamEvent(type="state", data={"from": "S00", "to": "S01"})
    out = reduce_event(ev, CTX)
    assert out[0].kind == "state"
    assert out[0].payload["from"] == "S00"
    assert out[0].payload["to"] == "S01"


def test_tool_use_emits_tool_io_call():
    ev = StreamEvent.tool_use("query_flight_basic", {"from": "北京", "to": "上海"})
    out = reduce_event(ev, CTX)
    assert out[0].kind == "tool_io"
    assert out[0].payload["phase"] == "call"
    assert out[0].payload["name"] == "query_flight_basic"
    assert out[0].payload["input"]["from"] == "北京"


def test_tool_result_redacts_secrets():
    ev = StreamEvent.tool_result(
        "query_flight_basic",
        {"raw": "ok", "key": "sk-abc1234567890abcdef", "data": [1, 2, 3]},
    )
    out = reduce_event(ev, CTX)
    payload = out[0].payload
    assert payload["phase"] == "result"
    assert "REDACTED" in str(payload["output_redacted"])
    assert payload["output_truncated"] is False


def test_tool_result_truncates_long_output():
    big = "x" * 5000
    ev = StreamEvent.tool_result("query_flight_basic", big)
    out = reduce_event(ev, CTX)
    assert out[0].payload["output_truncated"] is True
    # truncated output may include the suffix marker; bound = raw limit + suffix
    assert len(out[0].payload["output_redacted"]) <= 4096 + 20


def test_card_event_passes_through():
    ev = StreamEvent(type="card", data={"card_id": "c1", "card_type": "OD_INPUT", "title": "Pick"})
    out = reduce_event(ev, CTX)
    assert out[0].kind == "card"
    assert out[0].payload["card_id"] == "c1"


def test_suspend_event_passes_through():
    ev = StreamEvent(type="suspend", data={"checkpoint_id": "ck1"})
    out = reduce_event(ev, CTX)
    assert out[0].kind == "suspend"
    assert out[0].payload["checkpoint_id"] == "ck1"


def test_question_asked_passes_through():
    ev = StreamEvent.question_asked(
        request_id="r1", session_id="s1",
        questions=[{"question": "选航班?", "header": "Flight", "options": [{"label": "CA1501"}]}],
    )
    out = reduce_event(ev, CTX)
    assert out[0].kind == "question"
    assert out[0].payload["status"] == "asked"
    assert out[0].payload["prompt"] == [{"question": "选航班?", "header": "Flight", "options": [{"label": "CA1501"}]}]


def test_question_replied_passes_through():
    ev = StreamEvent.question_replied(
        session_id="s1", request_id="r1", answers=[["CA1501"]],
    )
    out = reduce_event(ev, CTX)
    assert out[0].kind == "question"
    assert out[0].payload["status"] == "replied"


def test_todo_updated_passes_through():
    ev = StreamEvent.todo_updated(
        session_id="s1",
        todos=[{"content": "查航班", "status": "in_progress", "priority": "high"}],
    )
    out = reduce_event(ev, CTX)
    assert out[0].kind == "todo"
    assert out[0].payload["items"] == [{"content": "查航班", "status": "in_progress", "priority": "high"}]


def test_error_passes_through():
    ev = StreamEvent.error("boom", code="INTERNAL")
    out = reduce_event(ev, CTX)
    assert out[0].kind == "error"
    assert out[0].payload["code"] == "INTERNAL"
    assert out[0].payload["message"] == "boom"


def test_text_event_returns_empty():
    ev = StreamEvent.text("hi")
    assert reduce_event(ev, CTX) == []


def test_reasoning_event_returns_empty():
    ev = StreamEvent.reasoning("because...")
    assert reduce_event(ev, CTX) == []


def test_done_event_returns_empty():
    ev = StreamEvent.done()
    assert reduce_event(ev, CTX) == []


def test_redact_value_handles_nested_dict():
    v, mod = redact_value({"a": "sk-1234567890123456", "b": "ok", "c": {"d": "Bearer xyz12345678901234"}})
    assert mod is True
    assert "REDACTED" in v["a"]
    assert v["b"] == "ok"
    assert "REDACTED" in v["c"]["d"]


def test_redact_value_no_change():
    v, mod = redact_value({"plain": "data", "list": [1, 2, 3]})
    assert mod is False
    assert v == {"plain": "data", "list": [1, 2, 3]}


def test_redact_value_handles_list():
    v, mod = redact_value(["ok", "sk-1234567890123456", "more"])
    assert mod is True
    assert "REDACTED" in v[1]


def test_seq_increments_per_reducer_run():
    state = ReducerState(seq=0)
    ev1 = StreamEvent.tool_use("t1", {})
    ev2 = StreamEvent.tool_result("t1", "ok")
    out1 = reduce_event(ev1, CTX, state)
    out2 = reduce_event(ev2, CTX, state)
    assert out1[0].seq == 0
    assert out2[0].seq == 1


def test_state_persists_across_calls():
    state = ReducerState(seq=0)
    reduce_event(StreamEvent.scenario("flight_booking"), CTX, state)
    reduce_event(StreamEvent(type="state", data={"from": "S00", "to": "S01"}), CTX, state)
    reduce_event(StreamEvent.tool_use("t1", {}), CTX, state)
    assert state.seq == 3