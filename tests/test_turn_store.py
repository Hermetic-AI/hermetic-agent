"""tests/test_turn_store.py — InMemoryTurnStore 单元测试."""

from __future__ import annotations

import time

import pytest

from openagent.auip.events import TurnEvent, TurnEventType
from openagent.core.turn_store import (
    TURN_STATUS_DONE,
    TURN_STATUS_ERROR,
    TURN_STATUS_RUNNING,
    TURN_STATUS_SUSPENDED,
    Checkpoint,
    InMemoryTurnStore,
    status_implies_terminal,
)


# ---------------------------------------------------------------------------
# Turn lifecycle
# ---------------------------------------------------------------------------


async def test_in_memory_create_turn() -> None:
    """create_turn 返回 turn_id, 默认 status=running, state=None."""
    store = InMemoryTurnStore()
    turn_id = await store.create_turn(
        session_id="s-1", skill_name="book-flight", skill_version="1.0.0",
    )
    assert isinstance(turn_id, str) and turn_id
    meta = await store.get_turn(turn_id)
    assert meta is not None
    assert meta["session_id"] == "s-1"
    assert meta["skill_name"] == "book-flight"
    assert meta["skill_version"] == "1.0.0"
    assert meta["status"] == TURN_STATUS_RUNNING
    assert meta["state"] is None


async def test_in_memory_get_turn_unknown_returns_none() -> None:
    """未创建的 turn 返回 None."""
    store = InMemoryTurnStore()
    assert await store.get_turn("nonexistent") is None


async def test_in_memory_create_turn_unique_ids() -> None:
    """每次 create_turn 返回不同 id."""
    store = InMemoryTurnStore()
    ids = {
        await store.create_turn("s", "sk", "1") for _ in range(5)
    }
    assert len(ids) == 5


# ---------------------------------------------------------------------------
# update_turn_status
# ---------------------------------------------------------------------------


async def test_in_memory_update_status() -> None:
    """update_turn_status 改 status + 可选 state."""
    store = InMemoryTurnStore()
    turn_id = await store.create_turn("s", "sk", "1")
    await store.update_turn_status(turn_id, TURN_STATUS_SUSPENDED, "S02")
    meta = await store.get_turn(turn_id)
    assert meta["status"] == TURN_STATUS_SUSPENDED
    assert meta["state"] == "S02"
    # 再切到 done
    await store.update_turn_status(turn_id, TURN_STATUS_DONE)
    meta = await store.get_turn(turn_id)
    assert meta["status"] == TURN_STATUS_DONE
    assert meta["state"] == "S02"  # state 保留


async def test_in_memory_update_status_unknown_turn_is_noop() -> None:
    """未知 turn_id 静默忽略, 不抛异常."""
    store = InMemoryTurnStore()
    # 不抛
    await store.update_turn_status("unknown", TURN_STATUS_DONE)


async def test_in_memory_update_status_invalid_raises() -> None:
    """非法 status 抛 ValueError."""
    store = InMemoryTurnStore()
    turn_id = await store.create_turn("s", "sk", "1")
    with pytest.raises(ValueError, match="Invalid turn status"):
        await store.update_turn_status(turn_id, "BOGUS")


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


async def test_in_memory_save_get_events() -> None:
    """save_event 追加, get_events 按 seq 升序返回."""
    store = InMemoryTurnStore()
    turn_id = await store.create_turn("s", "sk", "1")
    # 乱序写入
    for seq, t in [(2, TurnEventType.STATE), (0, TurnEventType.SESSION), (1, TurnEventType.TEXT)]:
        await store.save_event(turn_id, TurnEvent(
            seq=seq, turn_id=turn_id, type=t, data={"seq": seq},
        ))
    events = await store.get_events(turn_id)
    assert [e.seq for e in events] == [0, 1, 2]


async def test_in_memory_get_events_after_seq() -> None:
    """after_seq 过滤."""
    store = InMemoryTurnStore()
    turn_id = await store.create_turn("s", "sk", "1")
    for seq in range(5):
        await store.save_event(turn_id, TurnEvent(
            seq=seq, turn_id=turn_id, type=TurnEventType.TEXT, data={},
        ))
    events = await store.get_events(turn_id, after_seq=2)
    assert [e.seq for e in events] == [3, 4]


async def test_in_memory_get_events_empty() -> None:
    """无事件返回空列表."""
    store = InMemoryTurnStore()
    turn_id = await store.create_turn("s", "sk", "1")
    assert await store.get_events(turn_id) == []


async def test_in_memory_get_events_after_seq_zero_returns_all() -> None:
    """after_seq=0 (或负数) 返回所有."""
    store = InMemoryTurnStore()
    turn_id = await store.create_turn("s", "sk", "1")
    await store.save_event(turn_id, TurnEvent(
        seq=0, turn_id=turn_id, type=TurnEventType.SESSION, data={},
    ))
    events = await store.get_events(turn_id, after_seq=0)
    assert len(events) == 1


# ---------------------------------------------------------------------------
# Checkpoint
# ---------------------------------------------------------------------------


async def test_in_memory_save_get_latest_checkpoint() -> None:
    """save_checkpoint 保留历史, get_latest_checkpoint 返回最新."""
    store = InMemoryTurnStore()
    turn_id = await store.create_turn("s", "sk", "1")
    cp1 = Checkpoint(
        checkpoint_id="cp-1", turn_id=turn_id, state="S02",
        skill_ctx={"k": 1}, open_tool_calls=[], messages_snapshot=[],
        last_event_seq=2, created_at=time.time() - 100,
    )
    cp2 = Checkpoint(
        checkpoint_id="cp-2", turn_id=turn_id, state="S05",
        skill_ctx={"k": 2}, open_tool_calls=[], messages_snapshot=[],
        last_event_seq=5, created_at=time.time(),
    )
    await store.save_checkpoint(cp1)
    await store.save_checkpoint(cp2)
    latest = await store.get_latest_checkpoint(turn_id)
    assert latest is not None
    assert latest.checkpoint_id == "cp-2"
    assert latest.state == "S05"


async def test_in_memory_get_latest_checkpoint_empty_returns_none() -> None:
    """无 checkpoint 返回 None."""
    store = InMemoryTurnStore()
    turn_id = await store.create_turn("s", "sk", "1")
    assert await store.get_latest_checkpoint(turn_id) is None


async def test_in_memory_get_latest_checkpoint_unknown_turn_returns_none() -> None:
    """未知 turn 返回 None."""
    store = InMemoryTurnStore()
    assert await store.get_latest_checkpoint("unknown") is None


# ---------------------------------------------------------------------------
# status_implies_terminal
# ---------------------------------------------------------------------------


def test_status_implies_terminal() -> None:
    """done / error 是终止态."""
    assert status_implies_terminal(TURN_STATUS_DONE) is True
    assert status_implies_terminal(TURN_STATUS_ERROR) is True
    assert status_implies_terminal(TURN_STATUS_RUNNING) is False
    assert status_implies_terminal(TURN_STATUS_SUSPENDED) is False
    assert status_implies_terminal("BOGUS") is False
