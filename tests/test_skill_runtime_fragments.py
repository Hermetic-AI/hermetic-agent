"""tests/test_skill_runtime_fragments.py — FragmentLoader 单元测试."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest

from openagent.skills.runtime.errors import (
    FragmentNotFoundError,
    SkillBudgetExceeded,
    SkillNotFoundError,
)
from openagent.skills.runtime.fragments import FragmentLoader
from openagent.skills.registry import Skill, SkillRegistry


# ----- fixtures -----------------------------------------------------------


def _make_skill(tmp_path: Path, name: str, main_text: str = "MAIN", fragments: dict[str, str] | None = None) -> Skill:
    """建一个临时 skill: SKILL.md + fragments/*.md."""
    skill_dir = tmp_path / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(main_text, encoding="utf-8")
    if fragments:
        (skill_dir / "fragments").mkdir(exist_ok=True)
        for fid, body in fragments.items():
            (skill_dir / "fragments" / f"{fid}.md").write_text(body, encoding="utf-8")
    return Skill(
        name=name,
        description=f"skill {name}",
        source=str(skill_dir / "SKILL.md"),
    )


def _scenario(
    *,
    name: str = "flight_booking",
    strategy: str = "on_demand",
    initial_skills: list[dict] | None = None,
    load_on_state: dict[str, list[str]] | None = None,
    budget_tokens: int = 4000,
    budget_policy: str = "error",
    skills_in_execution: list[str] | None = None,
) -> SimpleNamespace:
    """Build a duck-typed scenario object."""
    prog = SimpleNamespace(
        strategy=strategy,
        initial_skills=initial_skills or [],
        load_on_state=load_on_state or {},
        budget_tokens=budget_tokens,
        budget_policy=budget_policy,
    )
    exec_ = SimpleNamespace(skills=skills_in_execution or [])
    return SimpleNamespace(name=name, execution=exec_, progressive_skill=prog)


# ----- registry & loader helpers ------------------------------------------


@pytest.fixture
def registry_with_skill(tmp_path: Path) -> tuple[SkillRegistry, Path]:
    reg = SkillRegistry()
    skill = _make_skill(
        tmp_path,
        "book-flight",
        main_text="BOOK FLIGHT MAIN",
        fragments={
            "summary": "SUMMARY BODY",
            "state-s02": "STATE-S02 BODY",
            "state-s05": "STATE-S05 BODY",
        },
    )
    reg.register(skill)
    return reg, tmp_path


# ----- tests --------------------------------------------------------------


def test_load_strategy_none_returns_empty(registry_with_skill: tuple[SkillRegistry, Path]) -> None:
    reg, _ = registry_with_skill
    loader = FragmentLoader(reg, budget=1000, policy="error")
    scn = _scenario(strategy="none")
    text, report = loader.load(scn, current_state="S05")
    assert text == ""
    assert report.loaded == []
    assert report.total_tokens == 0


def test_load_strategy_all_loads_full_skill(registry_with_skill: tuple[SkillRegistry, Path]) -> None:
    reg, _ = registry_with_skill
    loader = FragmentLoader(reg, budget=10000, policy="error")
    scn = _scenario(strategy="all", skills_in_execution=["book-flight"])
    text, report = loader.load(scn, current_state="S05")
    assert "BOOK FLIGHT MAIN" in text
    assert any(x.endswith("#all") for x in report.loaded)
    assert report.total_tokens > 0


def test_load_strategy_on_demand_loads_initial(registry_with_skill: tuple[SkillRegistry, Path]) -> None:
    reg, _ = registry_with_skill
    loader = FragmentLoader(reg, budget=1000, policy="error")
    scn = _scenario(
        strategy="on_demand",
        initial_skills=[{"name": "book-flight", "mode": "summary"}],
        load_on_state={},
    )
    text, report = loader.load(scn, current_state="S99")
    assert "SUMMARY BODY" in text
    assert "book-flight#summary" in report.loaded


def test_load_strategy_on_demand_loads_state(registry_with_skill: tuple[SkillRegistry, Path]) -> None:
    reg, _ = registry_with_skill
    loader = FragmentLoader(reg, budget=1000, policy="error")
    scn = _scenario(
        strategy="on_demand",
        initial_skills=[{"name": "book-flight", "mode": "summary"}],
        load_on_state={
            "S02": ["book-flight:state-s02"],
            "S05": ["book-flight:state-s05"],
        },
    )
    text, report = loader.load(scn, current_state="S05")
    assert "SUMMARY BODY" in text
    assert "STATE-S05 BODY" in text
    assert "book-flight:state-s05" in report.loaded
    # state-s02 should NOT be present
    assert "STATE-S02 BODY" not in text


def test_load_budget_error_raises(registry_with_skill: tuple[SkillRegistry, Path]) -> None:
    reg, _ = registry_with_skill
    loader = FragmentLoader(reg, budget=10, policy="error")
    scn = _scenario(
        strategy="on_demand",
        initial_skills=[{"name": "book-flight", "mode": "summary"}],
        load_on_state={"S02": ["book-flight:state-s02"]},
    )
    with pytest.raises(SkillBudgetExceeded) as exc_info:
        loader.load(scn, current_state="S02")
    assert exc_info.value.limit == 10
    assert exc_info.value.used > 10


def test_load_budget_warn_logs(registry_with_skill: tuple[SkillRegistry, Path], caplog: pytest.LogCaptureFixture) -> None:
    import logging
    reg, _ = registry_with_skill
    loader = FragmentLoader(reg, budget=10, policy="warn")
    scn = _scenario(
        strategy="on_demand",
        initial_skills=[{"name": "book-flight", "mode": "summary"}],
        load_on_state={"S02": ["book-flight:state-s02"]},
    )
    with caplog.at_level(logging.WARNING):
        text, report = loader.load(scn, current_state="S02")
    # text returned even when over budget, just a warning
    assert "SUMMARY BODY" in text
    assert report.total_tokens > 10


def test_load_budget_truncate_drops_last(registry_with_skill: tuple[SkillRegistry, Path]) -> None:
    reg, _ = registry_with_skill
    loader = FragmentLoader(reg, budget=15, policy="truncate")
    scn = _scenario(
        strategy="on_demand",
        initial_skills=[{"name": "book-flight", "mode": "summary"}],
        load_on_state={"S02": ["book-flight:state-s02"]},
    )
    text, report = loader.load(scn, current_state="S02")
    assert report.total_tokens <= 15
    assert report.dropped  # at least one dropped
    # the last (state-s02) should be dropped
    assert any("state-s02" in d for d in report.dropped)


def test_load_fragment_not_found(registry_with_skill: tuple[SkillRegistry, Path]) -> None:
    reg, _ = registry_with_skill
    loader = FragmentLoader(reg, budget=1000, policy="error")
    scn = _scenario(
        strategy="on_demand",
        initial_skills=[],
        load_on_state={"S02": ["book-flight:nonexistent"]},
    )
    with pytest.raises(FragmentNotFoundError) as exc_info:
        loader.load(scn, current_state="S02")
    assert exc_info.value.skill_name == "book-flight"
    assert exc_info.value.fragment_id == "nonexistent"
    assert exc_info.value.expected_path is not None


def test_load_skill_not_found(registry_with_skill: tuple[SkillRegistry, Path]) -> None:
    reg, _ = registry_with_skill
    loader = FragmentLoader(reg, budget=1000, policy="error")
    scn = _scenario(
        strategy="on_demand",
        initial_skills=[{"name": "unknown-skill", "mode": "summary"}],
        load_on_state={},
    )
    with pytest.raises(SkillNotFoundError) as exc_info:
        loader.load(scn, current_state="S01")
    assert exc_info.value.skill_name == "unknown-skill"


def test_load_explicit_strategy_with_no_loaded_fragments_returns_empty(
    registry_with_skill: tuple[SkillRegistry, Path],
) -> None:
    """P1-4: explicit 模式 + 没有任何 load_fragment() 调用 + 无 explicit_skills
    声明 → 返空 (跟旧版"等同于 on_demand"的行为完全不同)."""
    reg, _ = registry_with_skill
    loader = FragmentLoader(reg, budget=1000, policy="error")
    scn = _scenario(strategy="explicit")
    text, report = loader.load(scn, current_state="S05")
    assert text == ""
    assert report.loaded == []


def test_load_explicit_via_load_fragment(registry_with_skill: tuple[SkillRegistry, Path]) -> None:
    """P1-4: load_fragment() 调用过的片段会在下次 load() 时被读出."""
    reg, _ = registry_with_skill
    loader = FragmentLoader(reg, budget=1000, policy="error")

    # 显式 load 一个片段
    text1, tokens1 = loader.load_fragment("book-flight", "state-s05")
    assert "STATE-S05 BODY" in text1
    assert tokens1 > 0

    # 显式 load 另一个
    loader.load_fragment("book-flight", "state-s02")

    # load() 应该把两个都读出来
    scn = _scenario(strategy="explicit")
    text, report = loader.load(scn, current_state="anything")
    assert "STATE-S05 BODY" in text
    assert "STATE-S02 BODY" in text
    assert "book-flight:state-s05" in report.loaded
    assert "book-flight:state-s02" in report.loaded


def test_load_explicit_idempotent(registry_with_skill: tuple[SkillRegistry, Path]) -> None:
    """P1-4: 重复 load_fragment 同一片段是幂等的 (不重复加)."""
    reg, _ = registry_with_skill
    loader = FragmentLoader(reg, budget=1000, policy="error")

    loader.load_fragment("book-flight", "state-s05")
    loader.load_fragment("book-flight", "state-s05")
    loader.load_fragment("book-flight", "state-s05")

    scn = _scenario(strategy="explicit")
    text, report = loader.load(scn, current_state="X")
    # 只出现一次
    assert report.loaded.count("book-flight:state-s05") == 1
    assert text.count("STATE-S05 BODY") == 1


def test_load_explicit_clear_resets(registry_with_skill: tuple[SkillRegistry, Path]) -> None:
    """P1-4: clear_explicit() 清空运行时集合, 下次 load() 返空."""
    reg, _ = registry_with_skill
    loader = FragmentLoader(reg, budget=1000, policy="error")
    loader.load_fragment("book-flight", "state-s05")
    scn = _scenario(strategy="explicit")
    text1, _ = loader.load(scn, current_state="X")
    assert "STATE-S05 BODY" in text1

    loader.clear_explicit()
    text2, report2 = loader.load(scn, current_state="X")
    assert text2 == ""
    assert report2.loaded == []


def test_load_explicit_via_yaml_explicit_skills(
    registry_with_skill: tuple[SkillRegistry, Path],
) -> None:
    """P1-4: scenario.progressive_skill.explicit_skills YAML 字段生效."""
    reg, _ = registry_with_skill
    loader = FragmentLoader(reg, budget=1000, policy="error")
    scn = _scenario(
        strategy="explicit",
        # 这里借助 SimpleNamespace duck-typed 加 explicit_skills
        # (ProgressiveSkillConfig Pydantic 模型有这字段)
    )
    # 直接给 progressive_skill 塞字段 (避开 _scenario helper)
    from types import SimpleNamespace
    scn.progressive_skill = SimpleNamespace(
        strategy="explicit",
        initial_skills=[],
        load_on_state={},
        explicit_skills=["book-flight:state-s05"],
    )
    text, report = loader.load(scn, current_state="X")
    assert "STATE-S05 BODY" in text
    assert "book-flight:state-s05" in report.loaded


def test_load_explicit_load_fragment_not_found(registry_with_skill: tuple[SkillRegistry, Path]) -> None:
    """P1-4: load_fragment() 找不到时抛 FragmentNotFoundError."""
    reg, _ = registry_with_skill
    loader = FragmentLoader(reg, budget=1000, policy="error")
    with pytest.raises(FragmentNotFoundError):
        loader.load_fragment("book-flight", "nonexistent-frag")


def test_load_invalid_frag_id_format(registry_with_skill: tuple[SkillRegistry, Path]) -> None:
    reg, _ = registry_with_skill
    loader = FragmentLoader(reg, budget=1000, policy="error")
    scn = _scenario(
        strategy="on_demand",
        initial_skills=[],
        load_on_state={"S01": ["no-colon-here"]},
    )
    with pytest.raises(FragmentNotFoundError):
        loader.load(scn, current_state="S01")


def test_loader_ctor_validates_budget(tmp_path: Path) -> None:
    reg = SkillRegistry()
    with pytest.raises(ValueError, match="budget"):
        FragmentLoader(reg, budget=0)
    with pytest.raises(ValueError, match="policy"):
        FragmentLoader(reg, budget=100, policy="invalid")
