"""tests/test_skill_runtime_state_guard.py — StateGuard 单元测试."""

from __future__ import annotations

import pytest

from openagent.skills.runtime.errors import StateGuardViolation
from openagent.skills.runtime.manifest import SkillManifest, StateSpec
from openagent.skills.runtime.state_guard import StateGuard


def _manifest() -> SkillManifest:
    return SkillManifest(
        name="book-flight",
        initial_state="S01",
        states={
            "S01": StateSpec(description="init", allowed_tools=["ask_user", "echo"]),
            "S02": StateSpec(
                description="ask",
                allowed_tools=["ask_user", "query_flight_basic"],
            ),
            "S05": StateSpec(description="choose", allowed_tools=["ask_user", "choose_flight"]),
        },
        transitions={
            "S01": {"S02", "S05"},
            "S02": {"S03", "S04"},
            "S05": set(),
        },
    )


def test_state_guard_allows_listed_tool() -> None:
    g = StateGuard(_manifest(), current_state="S02")
    ok, reason = g.can_call_tool("query_flight_basic")
    assert ok is True
    assert reason == "ok"


def test_state_guard_blocks_unlisted_tool() -> None:
    g = StateGuard(_manifest(), current_state="S01")
    ok, reason = g.can_call_tool("query_flight_basic")
    assert ok is False
    assert "S01" in reason
    assert "query_flight_basic" in reason


def test_state_guard_always_allows_ask_user() -> None:
    g = StateGuard(_manifest(), current_state="S05")
    ok, reason = g.can_call_tool("ask_user")
    assert ok is True
    assert "framework-level" in reason


def test_state_guard_unknown_state_blocks() -> None:
    g = StateGuard(_manifest(), current_state="S99")
    ok, reason = g.can_call_tool("any_tool")
    assert ok is False
    assert "S99" in reason


def test_state_guard_default_state_from_manifest() -> None:
    g = StateGuard(_manifest())
    assert g.get_state() == "S01"


def test_state_guard_transition_allowed() -> None:
    g = StateGuard(_manifest(), current_state="S01")
    assert g.can_transition("S02") is True
    assert g.can_transition("S05") is True


def test_state_guard_transition_blocked() -> None:
    g = StateGuard(_manifest(), current_state="S01")
    assert g.can_transition("S03") is False
    assert g.can_transition("S99") is False


def test_state_guard_no_outgoing_transitions() -> None:
    g = StateGuard(_manifest(), current_state="S05")
    assert g.allowed_next_states() == []
    assert g.can_transition("S01") is False


def test_state_guard_assert_can_transition_raises() -> None:
    g = StateGuard(_manifest(), current_state="S01")
    with pytest.raises(StateGuardViolation):
        g.assert_can_transition("S99")
    # success path
    g.assert_can_transition("S02")


def test_state_guard_set_state() -> None:
    g = StateGuard(_manifest())
    g.set_state("S05")
    assert g.get_state() == "S05"
    ok, _ = g.can_call_tool("choose_flight")
    assert ok is True
