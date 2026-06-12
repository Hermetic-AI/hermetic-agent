"""tests/test_skill_runtime_smoke.py — 5 个端到端关键场景的烟囱测试.

5 个最关键场景:
1. SkillManifest 从 YAML 加载, StateGuard 校验工具
2. FragmentLoader on_demand 策略, 按 state 加载片段
3. FragmentLoader budget 强制 (error policy)
4. PromptBuilder 6 段拼装
5. StateGuard 状态转移 + manifest empty() 兜底
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from openagent.skills.runtime import (
    FragmentLoader,
    PromptBuilder,
    SkillManifest,
    StateGuard,
    StateSpec,
)
from openagent.skills.runtime.errors import (
    FragmentNotFoundError,
    SkillBudgetExceeded,
    SkillNotFoundError,
    StateGuardViolation,
)
from openagent.skills.runtime.fragments import FragmentLoadReport
from openagent.skills.runtime.prompt_builder import PromptBuilder as _PB
from openagent.skills.registry import Skill, SkillRegistry


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_skill(tmp_path: Path, name: str, fragments: dict[str, str]) -> Skill:
    sd = tmp_path / "skills" / name
    sd.mkdir(parents=True, exist_ok=True)
    (sd / "SKILL.md").write_text(f"## {name}\nmain body", encoding="utf-8")
    (sd / "fragments").mkdir(exist_ok=True)
    for fid, body in fragments.items():
        (sd / "fragments" / f"{fid}.md").write_text(body, encoding="utf-8")
    return Skill(
        name=name,
        description=f"desc {name}",
        source=str(sd / "SKILL.md"),
    )


def _scenario(
    *,
    name: str = "flight_booking",
    strategy: str = "on_demand",
    system_prompt: str = "SCEN-PROMPT",
    a2ui_enabled: bool = False,
    initial_skills: list[dict] | None = None,
    load_on_state: dict[str, list[str]] | None = None,
    skills_in_execution: list[str] | None = None,
) -> SimpleNamespace:
    a2ui = SimpleNamespace(enabled=a2ui_enabled)
    exec_ = SimpleNamespace(
        system_prompt=system_prompt, skills=skills_in_execution or []
    )
    prog = SimpleNamespace(
        strategy=strategy,
        initial_skills=initial_skills or [],
        load_on_state=load_on_state or {},
    )
    return SimpleNamespace(
        name=name, a2ui=a2ui, execution=exec_, progressive_skill=prog
    )


# ---------------------------------------------------------------------------
# Smoke tests — 5 critical scenarios
# ---------------------------------------------------------------------------


def test_smoke_1_manifest_yaml_and_state_guard(tmp_path: Path) -> None:
    """1. SkillManifest 加载 + StateGuard 校验工具 + 状态转移."""
    yaml = """
name: book-flight
version: "1.0.0"
initial_state: S01
states:
  - id: S01
    description: init
    allowed_tools: [ask_user]
  - id: S02
    description: ask
    allowed_tools: [ask_user, query_flight_basic]
  - id: S05
    description: choose
    allowed_tools: [ask_user, choose_flight]
transitions:
  S01: [S02, S05]
  S02: [S03]
  S05: []
"""
    p = tmp_path / "m.yaml"
    p.write_text(yaml, encoding="utf-8")
    m = SkillManifest.from_yaml(p)
    g = StateGuard(m)
    # default state = S01
    assert g.get_state() == "S01"
    # ask_user always allowed
    ok, _ = g.can_call_tool("ask_user")
    assert ok
    # query_flight_basic not allowed in S01
    ok, reason = g.can_call_tool("query_flight_basic")
    assert not ok and "S01" in reason
    # transition S01 → S05
    g.assert_can_transition("S05")
    g.set_state("S05")
    assert g.get_state() == "S05"
    # now choose_flight is allowed
    ok, _ = g.can_call_tool("choose_flight")
    assert ok
    # bad transition
    with pytest.raises(StateGuardViolation):
        g.assert_can_transition("S01")


def test_smoke_2_fragment_loader_on_demand(tmp_path: Path) -> None:
    """2. FragmentLoader on_demand: 按 state 加载, 初始 + 当前态."""
    reg = SkillRegistry()
    reg.register(
        _make_skill(
            tmp_path,
            "book-flight",
            {
                "summary": "SUMMARY-TEXT",
                "state-s02": "S02-TEXT",
                "state-s05": "S05-TEXT",
            },
        )
    )
    loader = FragmentLoader(reg, budget=4000, policy="error")
    scn = _scenario(
        strategy="on_demand",
        initial_skills=[{"name": "book-flight", "mode": "summary"}],
        load_on_state={
            "S02": ["book-flight:state-s02"],
            "S05": ["book-flight:state-s05"],
        },
    )
    # state S05 → summary + state-s05
    text, report = loader.load(scn, current_state="S05")
    assert "SUMMARY-TEXT" in text
    assert "S05-TEXT" in text
    assert "S02-TEXT" not in text
    assert "book-flight#summary" in report.loaded
    assert "book-flight:state-s05" in report.loaded
    # state S02 → summary + state-s02
    text2, _ = loader.load(scn, current_state="S02")
    assert "SUMMARY-TEXT" in text2
    assert "S02-TEXT" in text2
    assert "S05-TEXT" not in text2


def test_smoke_3_fragment_budget_enforced(tmp_path: Path) -> None:
    """3. FragmentLoader budget 强制 (error policy)."""
    reg = SkillRegistry()
    reg.register(
        _make_skill(
            tmp_path,
            "huge",
            {
                "summary": "X" * 600,  # ~400 tokens
                "full": "Y" * 600,  # ~400 tokens
            },
        )
    )
    loader = FragmentLoader(reg, budget=100, policy="error")
    scn = _scenario(
        strategy="on_demand",
        initial_skills=[{"name": "huge", "mode": "summary"}],
        load_on_state={"S02": ["huge:full"]},
    )
    with pytest.raises(SkillBudgetExceeded) as exc_info:
        loader.load(scn, current_state="S02")
    assert exc_info.value.limit == 100
    assert exc_info.value.used > 100
    # and the action hint is present
    assert exc_info.value.action
    # truncate policy → should NOT raise, but may drop
    trunc = FragmentLoader(reg, budget=100, policy="truncate")
    text, report = trunc.load(scn, current_state="S02")
    assert report.total_tokens <= 100
    assert report.dropped


def test_smoke_4_prompt_builder_six_sections(tmp_path: Path) -> None:
    """4. PromptBuilder 6 段拼装 (base / scenario / a2ui / fragments / state / messages)."""
    reg = SkillRegistry()
    reg.register(
        _make_skill(
            tmp_path, "book-flight", {"summary": "SUMMARY-FRAG"}
        )
    )
    loader = FragmentLoader(reg, budget=1000, policy="error")
    b = PromptBuilder(
        loader,
        framework_base="1-FRAMEWORK",
        aui_instructions="3-AUI",
    )
    scn = _scenario(
        name="flight_booking",
        strategy="on_demand",
        system_prompt="2-SCENARIO",
        a2ui_enabled=True,
        initial_skills=[{"name": "book-flight", "mode": "summary"}],
        load_on_state={"S05": ["book-flight:summary"]},
    )
    @dataclass
    class M:
        role: str
        content: str

    out = b.build(scn, current_state="S05", messages=[M("user", "6-USER")])
    # all 6 sections present
    assert "1-FRAMEWORK" in out
    assert "2-SCENARIO" in out
    assert "3-AUI" in out
    assert "SUMMARY-FRAG" in out
    assert "Current state: S05" in out
    assert "[user] 6-USER" in out
    # section order is correct
    order = [
        out.find("1-FRAMEWORK"),
        out.find("2-SCENARIO"),
        out.find("3-AUI"),
        out.find("SUMMARY-FRAG"),
        out.find("Current state: S05"),
        out.find("6-USER"),
    ]
    assert order == sorted(order)
    assert all(i >= 0 for i in order)


def test_smoke_5_empty_manifest_and_skill_not_found(tmp_path: Path) -> None:
    """5. empty() 兜底 + skill/fragment 缺失报错."""
    # empty manifest → guard should still work
    m = SkillManifest.empty()
    g = StateGuard(m)
    # ask_user is always allowed even with no states
    ok, _ = g.can_call_tool("ask_user")
    assert ok
    # current state defaults to initial_state (S01)
    assert g.get_state() == "S01"
    # any non-framework tool: blocked
    ok, reason = g.can_call_tool("query_flight")
    assert not ok
    assert "S01" in reason

    # fragment loader: skill not found
    reg = SkillRegistry()
    loader = FragmentLoader(reg, budget=1000, policy="error")
    scn = _scenario(
        strategy="on_demand",
        initial_skills=[{"name": "missing", "mode": "summary"}],
    )
    with pytest.raises(SkillNotFoundError):
        loader.load(scn, current_state="S01")

    # fragment loader: fragment not found
    reg.register(_make_skill(tmp_path, "book-flight", {"summary": "OK"}))
    scn2 = _scenario(
        strategy="on_demand",
        initial_skills=[],
        load_on_state={"S02": ["book-flight:no-such-fragment"]},
    )
    with pytest.raises(FragmentNotFoundError) as exc:
        loader.load(scn2, current_state="S02")
    assert exc.value.skill_name == "book-flight"
    assert exc.value.fragment_id == "no-such-fragment"
