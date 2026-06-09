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


def test_load_missing_optional_resource(tmp_path: Path):
    """a2ui.cards_dir 不存在 → 仍是 soft warning, 场景照常加载.

    契约: cards_dir 跟 readonly_dirs 一样, 是可选能力, 缺失不应阻断
    场景注册. (之前是硬错, 导致 reload 返回 0.)
    """
    p_str = tmp_path.as_posix()
    yaml_text = f"""
name: t
version: "1.0.0"
routing: {{priority: 100}}
execution: {{orchestration: single, skills: []}}
workspace: {{workspace_dirs: ["{p_str}"]}}
a2ui: {{enabled: true, cards_dir: "{p_str}/missing_cards"}}
progressive_skill: {{strategy: none}}
"""
    p = tmp_path / "ok.scenario.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    cfg = load_scenario(p, {})  # 不抛错
    assert cfg.name == "t"
    assert cfg.a2ui.cards_dir == f"{p_str}/missing_cards"


def test_load_missing_readonly_dir_still_loads(tmp_path: Path):
    """readonly_dirs 缺失 → 场景照常加载 (warning 而非 error)."""
    p_str = tmp_path.as_posix()
    yaml_text = f"""
name: t_ro
version: "1.0.0"
routing: {{priority: 100}}
execution: {{orchestration: single, skills: []}}
workspace: {{workspace_dirs: ["{p_str}"], readonly_dirs: ["{p_str}/missing_ro"]}}
progressive_skill: {{strategy: none}}
"""
    p = tmp_path / "ok.scenario.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    cfg = load_scenario(p, {})  # 不抛错
    assert cfg.name == "t_ro"
    assert f"{p_str}/missing_ro" in cfg.workspace.readonly_dirs


def test_load_missing_workspace_dir_warns_not_raises(tmp_path: Path):
    """workspace_dirs 缺失 → 软警告而非硬错.

    docker compose 部署时 Hub 跟 sandbox 在不同容器, workspace 走
    sandbox 自己的 bind mount, Hub 端校验一定 miss. 强制硬错会让
    所有 scenario 在 Hub 启动时直接被 reject, 整个路由空了.

    实际"workspace 不存在就废了"由 sandbox 端 launcher 兜底 (创建
    workspace / 报 workspace 路径不对), Hub 端只负责路由.
    """
    p_str = tmp_path.as_posix()
    yaml_text = f"""
name: t_no_ws
version: "1.0.0"
routing: {{priority: 100}}
execution: {{orchestration: single, skills: []}}
workspace: {{workspace_dirs: ["{p_str}/missing_ws"]}}
progressive_skill: {{strategy: none}}
"""
    p = tmp_path / "ok.scenario.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    cfg = load_scenario(p, {})  # 不抛错
    assert cfg.name == "t_no_ws"
    assert f"{p_str}/missing_ws" in cfg.workspace.workspace_dirs


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


def test_load_skill_md_missing_warns_not_raises(tmp_path: Path):
    """SKILL.md 缺失 → 软警告而非硬错.

    跟 workspace_dirs 同理: Hub 端 ``resource_dirs.skills`` 指向
    ``${WORK_SHARED}/skills`` (= ``work/shared/skills``), 在 docker compose
    下 Hub 容器不挂这个目录. 实际 skill 加载由 Hub 的 SkillRegistry 从
    自带 ``src/openagent/.skills/`` (Dockerfile build COPY) 读取, 跟
    scenario 里的 ``${WORK_SHARED}/skills`` 不是同一份.

    Hub 端只负责"场景声明了 skill X"这个**意图**, 真实 skill 文件由
    Hub 端的 SkillRegistry 兜底.
    """
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
    p = tmp_path / "ok.scenario.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    cfg = load_scenario(p, {})  # 不抛错
    assert "nonexistent_skill" in cfg.execution.skills


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


# ----------------------------------------------------------------------
# 回归: POST /agent/scenarios/reload 必须能加载 work/scenarios/*.yaml
# ----------------------------------------------------------------------


def test_reload_work_scenarios_loads_all() -> None:
    """盯住用户工单: reload 必须返回全部 scenario, 即使 ``work/shared/docs`` 不存在.

    work/scenarios/ 里 8 个 yaml 都引用 ${WORK_SHARED}/docs (软资源),
    之前 _check_workspace 把 readonly_dir 缺失当硬错 → reload 返回 0.
    修完后 8 个都该加载 (v3 新增 flight_query_v3).
    """
    from openagent.api.scenario_lifecycle import _build_placeholder_ctx, find_project_root
    from openagent.config.settings import Settings
    from openagent.scenarios.registry import ScenarioRegistry

    repo_root = find_project_root()
    scenarios_dir = repo_root / "work" / "scenarios"
    if not scenarios_dir.is_dir():
        pytest.skip(f"{scenarios_dir} not present")

    settings = Settings(
        work_root="work",
        scenario_paths=["work/scenarios"],
    )
    ctx = _build_placeholder_ctx(settings)
    reg = ScenarioRegistry(ctx=ctx)
    loaded = reg.reload(scenarios_dir)

    names = sorted(cfg.name for cfg in loaded)
    assert len(loaded) == 10, f"expected 10 scenarios, got {len(loaded)}: {names}"
    # 关键: 软警告 (readonly_dir / cards_dir 缺失) 不该阻断任何场景
    for expected in (
        "_default",
        "_generic",
        "code_review",
        "customer_service",
        "expense_audit",
        "flight_booking",
        "flight_query",
        "flight_query_v3",
        "flight_query_v4",
    ):
        assert expected in names, f"missing scenario: {expected}"
