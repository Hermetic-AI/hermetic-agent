"""tests/test_auip_events.py — TurnEvent 单元测试."""

from __future__ import annotations

import pytest

from openagent.auip.events import (
    TurnEvent,
    TurnEventType,
    assert_seq_increasing,
)


def test_turn_event_types_enum() -> None:
    """枚举值与字符串一致, 覆盖协议中所有事件类型."""
    expected = {
        "session", "text", "reasoning", "tool_use", "tool_result",
        "card", "state", "suspend", "resume", "done", "error",
    }
    actual = {e.value for e in TurnEventType}
    assert actual == expected
    # 枚举成员是 str 子类
    assert TurnEventType.SUSPEND == "suspend"


def test_turn_event_to_from_dict_roundtrip() -> None:
    """to_dict / from_dict 互逆."""
    evt = TurnEvent(
        seq=3,
        turn_id="t-1",
        type=TurnEventType.SUSPEND,
        data={"checkpoint_id": "cp-1", "card": {"x": 1}},
        ts=1234.5,
    )
    d = evt.to_dict()
    assert d["seq"] == 3
    assert d["turn_id"] == "t-1"
    assert d["type"] == "suspend"
    assert d["data"] == {"checkpoint_id": "cp-1", "card": {"x": 1}}
    assert d["ts"] == 1234.5

    evt2 = TurnEvent.from_dict(d)
    assert evt2.seq == evt.seq
    assert evt2.turn_id == evt.turn_id
    assert evt2.type == evt.type
    assert evt2.data == evt.data
    assert evt2.ts == evt.ts


def test_turn_event_from_dict_uses_default_ts() -> None:
    """缺 ts 时用 time.time() 兜底."""
    d = {"seq": 0, "turn_id": "t", "type": "text", "data": {}}
    evt = TurnEvent.from_dict(d)
    assert evt.ts > 0
    assert isinstance(evt.ts, float)


def test_turn_event_from_dict_invalid_type_raises() -> None:
    """非法 type 抛 ValueError."""
    with pytest.raises(ValueError):
        TurnEvent.from_dict({"seq": 0, "turn_id": "t", "type": "BOGUS", "data": {}})


def test_turn_event_from_dict_missing_required_raises() -> None:
    """缺 seq 抛 KeyError."""
    with pytest.raises(KeyError):
        TurnEvent.from_dict({"turn_id": "t", "type": "text", "data": {}})


def test_assert_seq_increasing_ok() -> None:
    """严格递增的 events 校验通过."""
    events = [
        TurnEvent(seq=0, turn_id="t", type=TurnEventType.SESSION, data={}),
        TurnEvent(seq=1, turn_id="t", type=TurnEventType.STATE, data={}),
        TurnEvent(seq=2, turn_id="t", type=TurnEventType.DONE, data={}),
    ]
    assert_seq_increasing(events)  # 不抛


def test_assert_seq_increasing_unsorted_input_raises() -> None:
    """乱序输入不被自动排序, 仍按 list 顺序校验 → 抛 ValueError."""
    events = [
        TurnEvent(seq=2, turn_id="t", type=TurnEventType.DONE, data={}),
        TurnEvent(seq=0, turn_id="t", type=TurnEventType.SESSION, data={}),
        TurnEvent(seq=1, turn_id="t", type=TurnEventType.STATE, data={}),
    ]
    with pytest.raises(ValueError, match="strictly increasing"):
        assert_seq_increasing(events)


def test_assert_seq_increasing_duplicate_seq_raises() -> None:
    """重复 seq 抛 ValueError."""
    events = [
        TurnEvent(seq=0, turn_id="t", type=TurnEventType.SESSION, data={}),
        TurnEvent(seq=0, turn_id="t", type=TurnEventType.STATE, data={}),
    ]
    with pytest.raises(ValueError, match="strictly increasing"):
        assert_seq_increasing(events)


def test_assert_seq_increasing_decreasing_seq_raises() -> None:
    """逆序 seq 抛 ValueError."""
    events = [
        TurnEvent(seq=1, turn_id="t", type=TurnEventType.STATE, data={}),
        TurnEvent(seq=0, turn_id="t", type=TurnEventType.SESSION, data={}),
    ]
    with pytest.raises(ValueError, match="strictly increasing"):
        assert_seq_increasing(events)


def test_assert_seq_increasing_empty() -> None:
    """空列表直接通过."""
    assert_seq_increasing([])
