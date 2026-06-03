"""ScenarioLoader 单测 — 占位符 + YAML + 资源校验."""

from __future__ import annotations

from pathlib import Path

import pytest

from openagent.scenarios.errors import (
    ScenarioLoadError,
    ScenarioResourceError,
)
from openagent.scenarios.loader import load_scenario, resolve_placeholders

WORK_DIR = Path(__file__).resolve().parents[1] / "work"


# ----------------------------------------------------------------------
# resolve_placeholders
# ----------------------------------------------------------------------


def test_resolve_placeholders_simple():
    out = resolve_placeholders("hello ${NAME}", {"NAME": "world"})
    assert out == "hello world"


def test_resolve_placeholders_nested_dict():
    out = resolve_placeholders(
        {"a": "${X}", "b": {"c": "${Y}"}}, {"X": "1", "Y": "2"}
    )
    assert out == {"a": "1", "b": {"c": "2"}}


def test_resolve_placeholders_in_list():
    out = resolve_placeholders(["${A}", "raw", {"k": "${B}"}], {"A": "1", "B": "2"})
    assert out == ["1", "raw", {"k": "2"}]


def test_resolve_placeholders_unresolved_kept():
    """找不到的占位符保留原样, 不抛错."""
    out = resolve_placeholders("${MISSING}/foo", {})
    assert out == "${MISSING}/foo"


def test_resolve_placeholders_partial_match():
    out = resolve_placeholders(
        {"a": "${A}", "b": "${B}"}, {"A": "1"}
    )
    assert out == {"a": "1", "b": "${B}"}


def test_resolve_placeholders_no_ctx():
    assert resolve_placeholders("${X}", None) == "${X}"
    assert resolve_placeholders("plain", None) == "plain"


def test_resolve_placeholders_non_string_types():
    assert resolve_placeholders(42, {}) == 42
    assert resolve_placeholders(3.14, {}) == 3.14
    assert resolve_placeholders(None, {}) is None
    assert resolve_placeholders(True, {}) is True


# ----------------------------------------------------------------------
# load_scenario — 现有 YAML
# ----------------------------------------------------------------------


def test_load_generic_scenario():
    ctx = {
        "PROJECT_DIR": str(WORK_DIR),
        "WORK_SHARED": str(WORK_DIR / "shared"),
        "WORK_ROOT": str(WORK_DIR),
        "SCENARIO_DIR": str(WORK_DIR / "scenarios" / "_generic"),
    }
    cfg = load_scenario(WORK_DIR / "scenarios" / "_generic.scenario.yaml", ctx)
    assert cfg.name == "_generic"
    assert cfg.security.tool_level == "safe"
    assert cfg.a2ui.enabled is False
    assert cfg.execution.skills == []
    assert cfg.enabled is True


def test_load_default_scenario():
    ctx = {
        "PROJECT_DIR": str(WORK_DIR),
        "WORK_SHARED": str(WORK_DIR / "shared"),
        "WORK_ROOT": str(WORK_DIR),
        "SCENARIO_DIR": str(WORK_DIR / "scenarios" / "_default"),
    }
    cfg = load_scenario(WORK_DIR / "scenarios" / "_default.scenario.yaml", ctx)
    assert cfg.name == "_default"
    assert cfg.security.tool_level == "safe"
    assert cfg.routing.priority == 90000


# ----------------------------------------------------------------------
# load_scenario — 失败场景
# ----------------------------------------------------------------------


def test_load_missing_resource(tmp_path: Path):
    """a2ui.cards_dir 不存在 → ScenarioResourceError."""
    p_str = tmp_path.as_posix()
    yaml_text = f"""
name: t
version: "1.0.0"
routing: {{priority: 100}}
execution: {{orchestration: hitl, skills: []}}
workspace: {{workspace_dirs: ["{p_str}"]}}
a2ui: {{enabled: true, cards_dir: "{p_str}/missing_cards"}}
progressive_skill: {{strategy: none}}
"""
    p = tmp_path / "bad.scenario.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    with pytest.raises(ScenarioResourceError) as ei:
        load_scenario(p, {})
    assert "missing_cards" in str(ei.value)
    assert ei.value.missing  # 有 missing 列表


def test_load_invalid_yaml(tmp_path: Path):
    p = tmp_path / "bad.scenario.yaml"
    p.write_text("name: t\nversion: '1.0.0'\n  bad indent: x", encoding="utf-8")
    with pytest.raises(ScenarioLoadError):
        load_scenario(p, {})


def test_load_validation_error(tmp_path: Path):
    """YAML 合法但 schema 不通过 → ScenarioLoadError."""
    yaml_text = """
name: "Invalid-Name"
version: "1.0.0"
routing: {priority: 100}
execution: {orchestration: single}
workspace: {workspace_dirs: ["/tmp/proj"]}
"""
    p = tmp_path / "bad.scenario.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    with pytest.raises(ScenarioLoadError):
        load_scenario(p, {})


def test_load_file_not_found():
    with pytest.raises(ScenarioLoadError):
        load_scenario("/nope/never.scenario.yaml", {})


def test_load_top_level_not_mapping(tmp_path: Path):
    p = tmp_path / "list.yaml"
    p.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ScenarioLoadError):
        load_scenario(p, {})


def test_load_hitl_missing_state_machine(tmp_path: Path):
    p_str = tmp_path.as_posix()
    yaml_text = f"""
name: hitl_no_sm
version: "1.0.0"
routing: {{priority: 100}}
execution: {{orchestration: hitl, skills: []}}
workspace: {{workspace_dirs: ["{p_str}"]}}
a2ui: {{enabled: true, state_machine: "{p_str}/no_such_sm.yaml"}}
progressive_skill: {{strategy: none}}
"""
    p = tmp_path / "bad.scenario.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    with pytest.raises(ScenarioResourceError) as ei:
        load_scenario(p, {})
    assert "state_machine" in str(ei.value)


def test_load_skill_md_missing(tmp_path: Path):
    p_str = tmp_path.as_posix()
    yaml_text = f"""
name: needs_skill
version: "1.0.0"
routing: {{priority: 100}}
execution: {{orchestration: single, skills: ["nonexistent_skill"]}}
workspace: {{workspace_dirs: ["{p_str}"]}}
resource_dirs: {{skills: "{p_str}"}}
progressive_skill: {{strategy: none}}
"""
    p = tmp_path / "bad.scenario.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    with pytest.raises(ScenarioResourceError) as ei:
        load_scenario(p, {})
    assert "SKILL.md" in str(ei.value)
    assert any("SKILL.md" in m for m in ei.value.missing)


def test_load_with_real_skill(tmp_path: Path):
    """完整的 happy path: skills/resource_dirs 配齐."""
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "my_skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# my_skill\n", encoding="utf-8")

    p_str = tmp_path.as_posix()
    skills_str = skills_dir.as_posix()
    yaml_text = f"""
name: with_skill
version: "1.0.0"
routing: {{priority: 100}}
execution: {{orchestration: single, skills: ["my_skill"]}}
workspace: {{workspace_dirs: ["{p_str}"]}}
resource_dirs: {{skills: "{skills_str}"}}
progressive_skill: {{strategy: none}}
"""
    p = tmp_path / "ok.scenario.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    cfg = load_scenario(p, {})
    assert "my_skill" in cfg.execution.skills
