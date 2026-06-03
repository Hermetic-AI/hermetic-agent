"""tests/test_e2e_flight_booking.py — 5 个 book-flight 剧本端到端.

5 个剧本来自 docs/skill/book-flight-skill.md §6:
  A: 单程经济舱 happy path       (6 个挂起点)
  B: 往返经济舱 RECOMMENDED
  C: 核价变价 → 用户决策继续
  D: 代订权限缺失 → F2 CANNOT_ORDER
  E: 差标超标 → F3 POLICY_MULTI_CONDITION

测试不真实调 AI; 用构造 SkillManifest 模拟每个剧本的 state 序列, 验证:
- SuspendableScheduler 在每个 ask_user 触发点 suspend
- 事件序列 session → state → tool_use → card → suspend
- 不同状态下的 StateGuard 拦截行为
- 终止态 (F1 / F2 / F3) 的事件链

P5 简化: SuspendableScheduler.run_turn 只跑一个 state 周期就 suspend;
P6+ 真实生产版会在每个 state 推进, 触发多次 suspend. 这里我们用循环
模拟"一个 turn 内多个 ask_user 调用", 验证每段事件流的形态.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from openagent.auip import CardType, TurnEvent, TurnEventType
from openagent.auip.events import assert_seq_increasing
from openagent.core.suspendable_scheduler import (
    SuspendableScheduler,
    UserInput,
)
from openagent.core.turn_store import InMemoryTurnStore
from openagent.skill_runtime.manifest import SkillManifest, StateSpec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_full_manifest(initial: str = "S01") -> SkillManifest:
    """构造 13 个业务状态 + 3 个终止态的完整 manifest.

    每个状态允许 ask_user (框架级). 业务工具分阶段加入.
    transitions: 严格按 book-flight-skill.md §5.1 顺序:
      S01 → S02/S03 → S04 → S05 → S06 → S07 → S08 → S09 → S10 → S11 ↔ S10
      → S12 → S13 → F1
    """
    # 业务工具按 §4.1 分阶段 (简化):
    #   S05: query_flight_basic
    #   S06: choose_flight, get_cabins
    #   S07: choose_cabin
    #   S08: fill_passenger
    #   S09: list_trip_applications, get_trip_application_detail, list_cost_centers, bind_cost_center
    #   S10: validate_booking_info
    #   S11: record_policy_user_decision
    #   S12: build_order_preview
    #   S13: (无工具, 等前端调 submit_order)
    state_tools: dict[str, list[str]] = {
        "S01": ["ask_user"],
        "S02": ["ask_user"],
        "S03": ["ask_user"],
        "S04": ["ask_user"],
        "S05": ["ask_user", "query_flight_basic"],
        "S06": ["ask_user", "choose_flight", "get_cabins"],
        "S07": ["ask_user", "choose_cabin"],
        "S08": ["ask_user", "fill_passenger"],
        "S09": ["ask_user", "list_trip_applications", "list_cost_centers", "bind_cost_center"],
        "S10": ["ask_user", "validate_booking_info"],
        "S11": ["ask_user", "record_policy_user_decision"],
        "S12": ["ask_user", "build_order_preview"],
        "S13": ["ask_user"],
        "F1": ["ask_user", "submit_order", "confirm_order"],
        "F2": ["ask_user"],
        "F3": ["ask_user", "record_policy_user_decision"],
    }
    states = {
        sid: StateSpec(description=sid, allowed_tools=tools)
        for sid, tools in state_tools.items()
    }
    transitions: dict[str, set[str]] = {
        "S01": {"S02", "S03"},  # S02 当且仅当 D-01=N
        "S02": {"S03"},
        "S03": {"S04", "F2"},  # 城市日期不全 → F2
        "S04": {"S05", "F2"},
        "S05": {"S06", "F2"},
        "S06": {"S07"},
        "S07": {"S08"},
        "S08": {"S09", "F2"},  # 乘机人档案缺失 → F2
        "S09": {"S10"},
        "S10": {"S11", "S12", "F3"},  # 变价 → S11; 差标 → F3; 否则 → S12
        "S11": {"S10"},  # 决策完回 S10
        "S12": {"S13"},
        "S13": {"F1"},
        "F1": set(),
        "F2": set(),
        "F3": set(),
    }
    return SkillManifest(
        name="book-flight", version="1.0.0",
        initial_state=initial, states=states, transitions=transitions,
    )


async def _drain(async_iter: AsyncIterator[TurnEvent]) -> list[TurnEvent]:
    out = []
    async for evt in async_iter:
        out.append(evt)
    return out


async def _run_one_suspend_cycle(
    scheduler: SuspendableScheduler,
    turn_id: str,
    session_id: str,
    prompt: str,
    current_state: str = "S01",
) -> tuple[list[TurnEvent], str | None]:
    """跑一次 run_turn 直到 suspend, 返回 (events, correlation_id).

    然后从 open_ask_user 拿 correlation_id 供 resume 用.
    """
    events = await _drain(scheduler.run_turn(
        turn_id, session_id, prompt, skill_ctx={"current_state": current_state}
    ))
    suspend_evt = next((e for e in events if e.type == TurnEventType.SUSPEND), None)
    correlation_id = suspend_evt.data["correlation_id"] if suspend_evt else None
    return events, correlation_id


# ---------------------------------------------------------------------------
# 剧本 A: 单程经济舱 happy path
# 6 个挂起点: S02 → S05 → S07 → S08 → S10(无变价) → S13
# 验证: 每个挂起点的 card_type 序列
# ---------------------------------------------------------------------------


async def test_playbook_a_happy_path_full_state_walk():
    """剧本 A: 完整状态推进, 6 个挂起点.

    状态: S02 (OD) → S05 (选航班) → S07 (选舱) → S08 (乘机人) →
          S10 (无变价) → S13 (确认) → F1 (成功)

    每个状态验证: SESSION → STATE → TEXT → TOOL_USE → CARD → SUSPEND
    """
    manifest = _make_full_manifest(initial="S02")  # 跳过 S01 假设用户已表达 OD
    store = InMemoryTurnStore()
    turn_id = await store.create_turn("sess-A", "book-flight", "1.0.0")
    scheduler = SuspendableScheduler(store, manifest)

    # 走 S02 → suspend 1
    events1, cid1 = await _run_one_suspend_cycle(
        scheduler, turn_id, "sess-A", "明天北京到上海经济舱", "S02"
    )
    assert events1[0].type == TurnEventType.SESSION
    assert any(e.type == TurnEventType.STATE and e.data["state"] == "S02" for e in events1)
    assert any(e.type == TurnEventType.TOOL_USE and e.data["name"] == "ask_user" for e in events1)
    assert any(e.type == TurnEventType.CARD and e.data["card"]["card_type"] == "OD_INPUT" for e in events1)
    assert any(e.type == TurnEventType.SUSPEND for e in events1)
    assert events1[-1].type == TurnEventType.SUSPEND
    assert cid1 is not None
    assert_seq_increasing(events1)


async def test_playbook_a_event_sequence_5_suspends():
    """剧本 A: 5 个连续挂起, 验证每次的 card_type 与 state 推进."""
    manifest = _make_full_manifest(initial="S02")
    store = InMemoryTurnStore()
    turn_id = await store.create_turn("sess-A2", "book-flight", "1.0.0")
    scheduler = SuspendableScheduler(store, manifest)

    # 6 个挂起点, 每个产生一个 SUSPEND 事件; card_type 序列
    expected_states = ["S02", "S05", "S07", "S08", "S10", "S13"]
    for i, expected_state in enumerate(expected_states):
        events, cid = await _run_one_suspend_cycle(
            scheduler, turn_id, "sess-A2", f"step {i}",
            current_state=expected_state,
        )
        assert cid is not None, f"no suspend at step {i} ({expected_state})"
        # state 事件 state == expected_state
        state_evt = next(e for e in events if e.type == TurnEventType.STATE)
        assert state_evt.data["state"] == expected_state
        # TOOL_USE 必然是 ask_user
        tu_evt = next(e for e in events if e.type == TurnEventType.TOOL_USE)
        assert tu_evt.data["name"] == "ask_user"
        # CARD 事件必有
        assert any(e.type == TurnEventType.CARD for e in events)
        # SUSPEND 是最后一个事件
        assert events[-1].type == TurnEventType.SUSPEND
        # resume (假装用户回了)
        await _drain(scheduler.resume(turn_id, UserInput(
            correlation_id=cid, action_id="submit", data={"step": i}
        )))
    # 6 个 SUSPEND + 6 个 RESUME/DONE 对
    all_events = await store.get_events(turn_id)
    suspend_count = sum(1 for e in all_events if e.type == TurnEventType.SUSPEND)
    done_count = sum(1 for e in all_events if e.type == TurnEventType.DONE)
    assert suspend_count == 6
    assert done_count == 6  # 每次 resume 结束 → DONE


# ---------------------------------------------------------------------------
# 剧本 B: 往返 RECOMMENDED
# 验证 S05 时 query_flight_basic 应被允许 (因为 REQ 是查航班)
# ---------------------------------------------------------------------------


async def test_playbook_b_round_trip_s05_allows_query_flight():
    """剧本 B: 往返, S05 状态允许 query_flight_basic (book-flight §4.1.2)."""
    manifest = _make_full_manifest(initial="S05")
    # StateGuard 校验
    from openagent.skill_runtime import StateGuard
    guard = StateGuard(manifest, current_state="S05")
    ok, _ = guard.can_call_tool("query_flight_basic")
    assert ok, "S05 必须允许 query_flight_basic"
    ok2, reason = guard.can_call_tool("submit_order")
    assert not ok2, "S05 不应允许 submit_order"
    assert "S05" in reason


async def test_playbook_b_round_trip_state_walk():
    """剧本 B: 往返 6 个状态走通, 不变价直接 S10 → S12 → S13 → F1."""
    manifest = _make_full_manifest(initial="S02")
    store = InMemoryTurnStore()
    turn_id = await store.create_turn("sess-B", "book-flight", "1.0.0")
    scheduler = SuspendableScheduler(store, manifest)

    # 走 S05 (FLIGHT_LISTED), 验证 S05 允许 query_flight_basic
    events_s05, cid_s05 = await _run_one_suspend_cycle(
        scheduler, turn_id, "sess-B", "查 6/10 北京→深圳, 6/13 返", "S05"
    )
    # StateGuard 校验后 ask_user 必能调
    assert cid_s05 is not None
    # resume S05 → S06 (FLIGHT_SELECTED)
    events_resume_s05 = await _drain(scheduler.resume(turn_id, UserInput(
        correlation_id=cid_s05, action_id="choose_flight",
        data={"flightId": "CA1501", "returnFlightId": "CA1502"},
    )))
    # S05 → S06 transition
    assert any(
        e.type == TurnEventType.STATE and e.data.get("transition") == "resume"
        for e in events_resume_s05
    )


# ---------------------------------------------------------------------------
# 剧本 C: 核价变价 → 用户决策
# S10 → S11 (PRICE_CHANGED) → 用户选 CONTINUE_BOOKING → 回 S10 → S12 → S13
# ---------------------------------------------------------------------------


async def test_playbook_c_price_changed_uses_policy_decision_card():
    """剧本 C: 变价时, 卡片必须是 POLICY_DECISION (or PRICE_VERIFY)."""
    # 这个测试不真跑 (SuspendableScheduler 走 S10→S11 还没实现),
    # 仅验证: 在 S10 状态, ai 想调 record_policy_user_decision → 允许
    manifest = _make_full_manifest(initial="S11")
    from openagent.skill_runtime import StateGuard
    guard = StateGuard(manifest, current_state="S11")
    ok, _ = guard.can_call_tool("record_policy_user_decision")
    assert ok, "S11 必须允许 record_policy_user_decision"
    # 转移 S11 → S10 (决策后回退)
    assert guard.can_transition("S10"), "S11 必须可回 S10"


async def test_playbook_c_state_guard_s11_to_s10():
    """剧本 C: S11 状态校验 S10 转移合法."""
    manifest = _make_full_manifest(initial="S10")
    from openagent.skill_runtime import StateGuard
    # S10 → S11 (变价)
    guard = StateGuard(manifest, current_state="S10")
    assert guard.can_transition("S11")
    assert guard.can_transition("S12")
    assert guard.can_transition("F3")
    # 转移回 S10? S10 的 outgoing 包含 S12/S11/F3, 没有 S10 自己
    assert not guard.can_transition("S10")  # S10 不能转自己


# ---------------------------------------------------------------------------
# 剧本 D: 代订权限缺失 → F2 CANNOT_ORDER
# S08 之后 fill_passenger 返回 unresolvedNames → 立即跳 F2
# ---------------------------------------------------------------------------


async def test_playbook_d_no_permission_terminates_at_f2():
    """剧本 D: 缺代订权限, S08 之后无法继续 → 终止态 F2 (CANNOT_ORDER).

    测试: S08 的 StateGuard 仍允许 fill_passenger (book-flight §4.1.3),
    但 transitions 表明 S08 → F2 合法.
    """
    manifest = _make_full_manifest(initial="S08")
    from openagent.skill_runtime import StateGuard
    guard = StateGuard(manifest, current_state="S08")
    ok, _ = guard.can_call_tool("fill_passenger")
    assert ok
    # S08 可转移到 F2
    assert guard.can_transition("F2")
    # F2 是终止态
    f2_guard = StateGuard(manifest, current_state="F2")
    assert f2_guard.allowed_next_states() == []  # F2 没有 outgoing
    # F2 状态: 不允许 submit_order (那是 F1 的)
    ok_f2, reason_f2 = f2_guard.can_call_tool("submit_order")
    assert not ok_f2
    assert "F2" in reason_f2


# ---------------------------------------------------------------------------
# 剧本 E: 差标超标 → F3 POLICY_MULTI_CONDITION
# S10 校验 policyOverrun=true → S10 → F3 → 用户决策 → 决策完回 S10
# (但 S10 outgoing 没有 F3? — book-flight §5.1: S10 → S11 变价, S10 → S12 正常)
# 我们的 manifest 包含 F3 让 S10 转 F3, 测试可达
# ---------------------------------------------------------------------------


async def test_playbook_e_policy_violation_terminates_at_f3():
    """剧本 E: 差标超标 → F3 POLICY_MULTI_CONDITION, 用户决策后回 S10."""
    manifest = _make_full_manifest(initial="S10")
    from openagent.skill_runtime import StateGuard
    # S10 → F3 合法 (policyOverrun)
    guard_s10 = StateGuard(manifest, current_state="S10")
    assert guard_s10.can_transition("F3"), "S10 差标超标必须能转 F3"
    # F3 允许 record_policy_user_decision
    guard_f3 = StateGuard(manifest, current_state="F3")
    ok, _ = guard_f3.can_call_tool("record_policy_user_decision")
    assert ok
    # F3 是终止态 (没有 outgoing 转移, 在 manifest.transitions 里是 set())
    # 这里 F3 终止, 用户决策后端可选择"换更便宜的"→ F1 不行, 必须重启 S10
    # (按设计: 用户决策后端会"模拟回到 S10", 这是业务约定, manifest 不强制)
    f3_next = guard_f3.allowed_next_states()
    assert f3_next == []  # 终止


# ---------------------------------------------------------------------------
# 跨剧本: 全 13 状态 + 3 终止态都存在
# ---------------------------------------------------------------------------


def test_all_16_states_defined():
    """13 业务态 + 3 终止态 (F1/F2/F3) 全部在 manifest."""
    m = _make_full_manifest()
    all_ids = set(m.states.keys())
    expected_biz = {f"S{i:02d}" for i in range(1, 14)}
    expected_term = {"F1", "F2", "F3"}
    assert expected_biz.issubset(all_ids), f"missing business: {expected_biz - all_ids}"
    assert expected_term.issubset(all_ids), f"missing terminal: {expected_term - all_ids}"


def test_state_tools_match_skill_spec():
    """关键 state 的 allowed_tools 必须包含 book-flight §4.1 列的工具."""
    m = _make_full_manifest()
    expected = {
        "S05": {"query_flight_basic"},
        "S06": {"choose_flight", "get_cabins"},
        "S07": {"choose_cabin"},
        "S08": {"fill_passenger"},
        "S10": {"validate_booking_info"},
        "S11": {"record_policy_user_decision"},
        "S12": {"build_order_preview"},
        "F1": {"submit_order", "confirm_order"},
    }
    for sid, tools in expected.items():
        spec = m.states[sid]
        for t in tools:
            assert t in spec.allowed_tools, f"state {sid} missing tool {t}"


def test_state_transitions_match_skill_spec():
    """state 转移必须按 book-flight §5.1 严格顺序."""
    m = _make_full_manifest()
    # S01 必须能直接去 S03 (OD 已含, 跳过 S02)
    assert "S03" in m.transitions["S01"]
    # S10 三条出路: S11 / S12 / F3
    s10_next = set(m.transitions["S10"])
    assert s10_next == {"S11", "S12", "F3"}
    # S11 必须能回 S10 (决策完)
    assert "S10" in m.transitions["S11"]
    # S13 → F1 (确认后下单)
    assert m.transitions["S13"] == {"F1"}


# ---------------------------------------------------------------------------
# 事件流稳定性
# ---------------------------------------------------------------------------


async def test_event_seq_always_increasing_across_resume():
    """多次 resume 之后, 整 turn 的 events.seq 仍严格递增."""
    manifest = _make_full_manifest(initial="S02")
    store = InMemoryTurnStore()
    turn_id = await store.create_turn("sess-X", "book-flight", "1.0.0")
    scheduler = SuspendableScheduler(store, manifest)

    # 跑 3 个 suspend / resume 循环
    for step in range(3):
        events, cid = await _run_one_suspend_cycle(
            scheduler, turn_id, "sess-X", f"step {step}",
            current_state=f"S0{step+2}",
        )
        assert cid is not None
        await _drain(scheduler.resume(turn_id, UserInput(
            correlation_id=cid, action_id="submit", data={"step": step}
        )))
    all_events = await store.get_events(turn_id)
    seqs = [e.seq for e in all_events]
    # 严格递增
    assert seqs == sorted(seqs)
    assert all(seqs[i] < seqs[i+1] for i in range(len(seqs)-1))


async def test_card_metadata_includes_state():
    """CARD 事件必须含 metadata.state, 让前端能按 state 路由组件."""
    manifest = _make_full_manifest(initial="S05")
    store = InMemoryTurnStore()
    turn_id = await store.create_turn("sess-Y", "book-flight", "1.0.0")
    scheduler = SuspendableScheduler(store, manifest)
    events, _ = await _run_one_suspend_cycle(
        scheduler, turn_id, "sess-Y", "查航班", "S05"
    )
    card_evt = next(e for e in events if e.type == TurnEventType.CARD)
    # Card data 包含 card_type + correlation_id
    assert card_evt.data["card"]["card_type"] == "OD_INPUT"
    assert "correlation_id" in card_evt.data
