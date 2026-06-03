"""tests/test_auip_smoke.py — AUIP + SuspendableScheduler 端到端烟囱测试.

完整跑一遍: 创建 turn → run_turn (走完整挂起流程) → 验证 Card + Checkpoint
→ 用户填表 → resume → 验证 done 终态.
"""

from __future__ import annotations

import pytest

from openagent.auip import (
    CARD_TYPES_SET,
    Card,
    CardType,
    TurnEventType,
    compile_skill_md,
)
from openagent.core.suspendable_scheduler import (
    SuspendableScheduler,
    UserInput,
)
from openagent.core.turn_store import (
    TURN_STATUS_DONE,
    TURN_STATUS_SUSPENDED,
    InMemoryTurnStore,
)
from openagent.skill_runtime.manifest import SkillManifest, StateSpec


# ---------------------------------------------------------------------------
# Smoke 1: Card 协议 (YAML → Card → to_dict)
# ---------------------------------------------------------------------------


def test_smoke_card_yaml_to_event(tmp_path) -> None:
    """Card YAML → Card → to_dict, 喂给 SuspendableScheduler 走完."""
    yaml_text = """
card_type: FLIGHT_LIST
schema_version: "1.0"
title: "请选择航班"
body:
  message: "为您找到以下航班"
options:
  - id: ca1501
    label: "CA1501 09:00-11:20 ¥820"
  - id: mu5102
    label: "MU5102 14:00-16:15 ¥1,250"
actions:
  - id: select
    label: "确认选择"
    style: primary
metadata:
  state: S05
  skill: book-flight
"""
    p = tmp_path / "FLIGHT_LIST.card.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    card = Card.from_yaml(p)
    d = card.to_dict()
    assert d["card_type"] == "FLIGHT_LIST"
    assert len(d["options"]) == 2
    assert d["metadata"]["state"] == "S05"
    # CardType 枚举必须含 FLIGHT_LIST
    assert CardType.FLIGHT_LIST.value in CARD_TYPES_SET


# ---------------------------------------------------------------------------
# Smoke 2: compile_skill_md (P5 简化路径)
# ---------------------------------------------------------------------------


def test_smoke_compile_skill_md_realistic(tmp_path) -> None:
    """编译一个真实形态的 SKILL.md (含 13 状态 + 6 工具)."""
    fm = (
        "---\n"
        "name: book-flight\n"
        "version: \"1.0.0\"\n"
        "description: 飞鹤 AI 订票\n"
        "---\n"
        "\n"
        "# Book Flight\n"
        "\n"
        "## 2. 状态机\n"
        "\n"
        "### 2.1 状态一览 (13 个状态)\n"
        "\n"
        "| # | State ID | 名称 | 类别 |\n"
        "|---|---|---|---|\n"
        "| 1 | S01 | INIT | 起点 |\n"
        "| 2 | S02 | OD_PENDING | 等待 |\n"
        "| 3 | S05 | FLIGHT_LISTED | 中间 |\n"
        "| 4 | S11 | PRICE_CONFIRMED | 等待 |\n"
        "| 5 | F1 | AUTO_SUBMIT | 终止 |\n"
        "\n"
        "## 3. MCP 工具\n"
        "\n"
        "### 3.1 工具白名单\n"
        "\n"
        "- `query_flight_basic`\n"
        "- `choose_flight`\n"
        "- `choose_cabin`\n"
        "- `fill_passenger`\n"
        "- `validate_booking_info`\n"
        "- `submit_order`\n"
    )
    p = tmp_path / "SKILL.md"
    p.write_text(fm, encoding="utf-8")
    out = compile_skill_md(p)
    assert out["name"] == "book-flight"
    assert out["version"] == "1.0.0"
    # 5 状态
    sids = [s["id"] for s in out["states"]]
    assert sids == ["S01", "S02", "S05", "S11", "F1"]
    # 6 工具
    assert out["allowed_tools"] == [
        "query_flight_basic", "choose_flight", "choose_cabin",
        "fill_passenger", "validate_booking_info", "submit_order",
    ]
    # prompt_template 包含 §3 章节
    assert "MCP 工具" in out["prompt_template"]


# ---------------------------------------------------------------------------
# Smoke 3: 完整挂起/恢复循环
# ---------------------------------------------------------------------------


def _make_manifest() -> SkillManifest:
    """P5 测试用: S01 only ask_user, 状态机可走 S01→S02."""
    return SkillManifest(
        name="book-flight",
        version="1.0.0",
        initial_state="S01",
        states={
            "S01": StateSpec(description="init", allowed_tools=["ask_user"]),
            "S02": StateSpec(
                description="ask", allowed_tools=["ask_user", "query_flight_basic"],
            ),
        },
        transitions={"S01": {"S02"}, "S02": set()},
    )


async def test_smoke_suspend_resume_full_cycle() -> None:
    """端到端: create_turn → run_turn (suspend) → resume (done)."""
    store = InMemoryTurnStore()
    turn_id = await store.create_turn("sess-1", "book-flight", "1.0.0")
    sched = SuspendableScheduler(turn_store=store, manifest=_make_manifest())

    # 1) run_turn
    run_events = []
    async for evt in sched.run_turn(turn_id, "sess-1", "帮我订北京到上海的机票, 明早出发"):
        run_events.append(evt)
    # 校验事件流
    types = [e.type for e in run_events]
    assert types == [
        TurnEventType.SESSION,
        TurnEventType.STATE,
        TurnEventType.TEXT,
        TurnEventType.TOOL_USE,  # ask_user
        TurnEventType.CARD,
        TurnEventType.SUSPEND,
    ]
    # 校验 seq 严格递增
    assert [e.seq for e in run_events] == list(range(len(run_events)))
    # 校验 turn 状态
    assert (await store.get_turn(turn_id))["status"] == TURN_STATUS_SUSPENDED
    # 校验 Checkpoint
    cp = await store.get_latest_checkpoint(turn_id)
    assert cp is not None
    assert cp.state == "S01"
    assert cp.open_tool_calls[0]["name"] == "ask_user"

    # 2) 模拟前端拿到 card
    card_evt = run_events[4]
    card = card_evt.data["card"]
    assert card["card_type"] == "OD_INPUT"
    correlation_id = card_evt.data["correlation_id"]

    # 3) 用户填表 + resume
    user_input = UserInput(
        correlation_id=correlation_id,
        action_id="select",
        data={"origin": "PEK", "destination": "SHA", "date": "2026-06-10"},
    )
    resume_events = []
    async for evt in sched.resume(turn_id, user_input):
        resume_events.append(evt)
    # 校验 resume 事件流
    resume_types = [e.type for e in resume_events]
    assert resume_types == [
        TurnEventType.RESUME,
        TurnEventType.TOOL_RESULT,
        TurnEventType.STATE,
        TurnEventType.DONE,
    ]
    # 校验 tool_result 回填
    tr = resume_events[1]
    assert tr.data["id"] == correlation_id
    assert tr.data["output"]["action_id"] == "select"
    assert tr.data["output"]["user_input"]["origin"] == "PEK"
    # 校验 turn 终态
    assert (await store.get_turn(turn_id))["status"] == TURN_STATUS_DONE

    # 4) 全程事件 (run + resume) 严格递增
    all_events = run_events + resume_events
    all_seqs = [e.seq for e in all_events]
    assert all_seqs == sorted(all_seqs) and len(set(all_seqs)) == len(all_seqs)


# ---------------------------------------------------------------------------
# Smoke 4: 反向 (resume 一个从未挂起的 turn)
# ---------------------------------------------------------------------------


async def test_smoke_resume_without_suspend_raises() -> None:
    """用户刷新页面后重新提交, 旧 turn 找不到挂起点 → TurnNotFound."""
    store = InMemoryTurnStore()
    turn_id = await store.create_turn("sess-2", "book-flight", "1.0.0")
    sched = SuspendableScheduler(turn_store=store, manifest=_make_manifest())
    with pytest.raises(Exception) as exc_info:
        async for _ in sched.resume(turn_id, UserInput(correlation_id="x")):
            pass
    # 必须是 TurnNotFound
    from openagent.auip.errors import TurnNotFound
    assert isinstance(exc_info.value, TurnNotFound)
