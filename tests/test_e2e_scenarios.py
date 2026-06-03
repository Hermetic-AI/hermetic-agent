"""E2E: 6 个 scenario 的 5 维度配置全对.

验证设计文档 §9 的 5 维度对比矩阵:
- security.tool_level
- workspace.cwd (project-relative)
- a2ui
- progressive_skill
- orchestration
"""
from pathlib import Path

import pytest

from openagent.scenarios import ScenarioRegistry, ScenarioRouter
from openagent.scenarios.injector import ScenarioInjector


WORK_ROOT = Path("work")


@pytest.fixture
def scenarios():
    ctx = {
        "WORK_ROOT": str(WORK_ROOT),
        "WORK_SHARED": str(WORK_ROOT / "shared"),
        "PROJECT_DIR": str(WORK_ROOT / "tenants" / "tenant-A" / "projects" / "project-1"),
    }
    reg = ScenarioRegistry(ctx=ctx)
    reg.load_from_paths(str(WORK_ROOT / "scenarios"))
    return reg


# ---------------------------------------------------------------------------
# flight_booking (5 维度最复杂)
# ---------------------------------------------------------------------------


def test_flight_booking_security_standard(scenarios):
    cfg = scenarios.get("flight_booking")
    assert cfg.security.tool_level == "standard"
    assert cfg.security.network in ("off", "local", "any")
    assert "rm -rf" in " ".join(cfg.security.denied_commands)
    assert "sudo" in " ".join(cfg.security.denied_commands)


def test_flight_booking_workspace_project_relative(scenarios):
    cfg = scenarios.get("flight_booking")
    assert cfg.workspace.strategy == "project_relative"
    first = cfg.workspace.workspace_dirs[0]
    assert "${PROJECT_DIR}" in first or first.startswith(str(WORK_ROOT))


def test_flight_booking_a2ui_enabled_with_cards(scenarios):
    cfg = scenarios.get("flight_booking")
    assert cfg.a2ui.enabled is True
    assert cfg.a2ui.protocol == "auip"
    assert cfg.a2ui.cards_dir  # 非空
    # state_machine: 可能在 a2ui.state_machine / execution.hitl.state_machine / resource_dirs 中
    has_state_machine = (
        cfg.a2ui.state_machine
        or (cfg.execution.hitl and cfg.execution.hitl.state_machine)
        or cfg.resource_dirs.get("state_machine")
    )
    assert has_state_machine, f"{cfg.name} is hitl but no state_machine declared"


def test_flight_booking_progressive_on_demand(scenarios):
    cfg = scenarios.get("flight_booking")
    assert cfg.progressive_skill.strategy == "on_demand"
    assert cfg.progressive_skill.budget_tokens >= 500
    assert cfg.progressive_skill.budget_tokens <= 32000
    assert cfg.progressive_skill.load_on_state  # on_demand 必填


def test_flight_booking_orchestration_hitl(scenarios):
    cfg = scenarios.get("flight_booking")
    assert cfg.execution.orchestration == "hitl"


# ---------------------------------------------------------------------------
# expense_audit (parallel)
# ---------------------------------------------------------------------------


def test_expense_audit_orchestration_parallel(scenarios):
    cfg = scenarios.get("expense_audit")
    assert cfg.execution.orchestration == "parallel"
    assert cfg.a2ui.enabled is False  # parallel 场景不需要 HITL 卡片


def test_expense_audit_progressive_all(scenarios):
    cfg = scenarios.get("expense_audit")
    assert cfg.progressive_skill.strategy in ("all", "on_demand")


# ---------------------------------------------------------------------------
# customer_service (HITL but light)
# ---------------------------------------------------------------------------


def test_customer_service_a2ui_enabled(scenarios):
    cfg = scenarios.get("customer_service")
    assert cfg.execution.orchestration == "hitl"
    assert cfg.a2ui.enabled is True


def test_customer_service_safe_tool_level(scenarios):
    cfg = scenarios.get("customer_service")
    assert cfg.security.tool_level == "safe"


# ---------------------------------------------------------------------------
# code_review (delegate)
# ---------------------------------------------------------------------------


def test_code_review_orchestration_delegate(scenarios):
    cfg = scenarios.get("code_review")
    assert cfg.execution.orchestration == "delegate"


# ---------------------------------------------------------------------------
# _generic (兜底)
# ---------------------------------------------------------------------------


def test_generic_is_minimal_no_skills(scenarios):
    cfg = scenarios.get("_generic")
    assert cfg.execution.skills == []
    assert cfg.execution.tools == []


def test_generic_security_strictest(scenarios):
    cfg = scenarios.get("_generic")
    assert cfg.security.tool_level == "safe"
    assert cfg.security.network == "off"
    assert cfg.security.max_turns <= 5
    assert cfg.security.max_budget_usd <= 0.5


def test_generic_progressive_none(scenarios):
    cfg = scenarios.get("_generic")
    assert cfg.progressive_skill.strategy == "none"


def test_generic_a2ui_disabled(scenarios):
    cfg = scenarios.get("_generic")
    assert cfg.a2ui.enabled is False


# ---------------------------------------------------------------------------
# _default (兜底)
# ---------------------------------------------------------------------------


def test_default_similar_to_generic(scenarios):
    g = scenarios.get("_generic")
    d = scenarios.get("_default")
    assert d.security.tool_level == g.security.tool_level == "safe"
    assert d.a2ui.enabled is False


def test_default_priority_between_generic_and_business(scenarios):
    g = scenarios.get("_generic").routing.priority
    d = scenarios.get("_default").routing.priority
    fb = scenarios.get("flight_booking").routing.priority
    # _default 比业务低, _generic 比 _default 低 (作为最终兜底)
    assert d >= fb  # default 优先级数字 ≥ 业务
    assert g > d   # generic 优先级数字 > default (数值大=优先级低)


# ---------------------------------------------------------------------------
# 跨场景一致性
# ---------------------------------------------------------------------------


def test_no_scenario_uses_root_workspace(scenarios):
    for cfg in scenarios.list_all():
        first = cfg.workspace.workspace_dirs[0]
        assert first not in ("/", "~", "${HOME}", ""), f"{cfg.name} uses root: {first!r}"


def test_all_scenarios_block_dangerous_commands(scenarios):
    for cfg in scenarios.list_all():
        joined = " ".join(cfg.security.denied_commands)
        assert "rm -rf" in joined, f"{cfg.name} missing rm -rf in denied_commands"
        assert "sudo" in joined, f"{cfg.name} missing sudo in denied_commands"
        assert "dd" in joined, f"{cfg.name} missing dd in denied_commands"


def test_all_scenarios_have_resource_dirs(scenarios):
    for cfg in scenarios.list_all():
        assert cfg.resource_dirs, f"{cfg.name} missing resource_dirs"


def test_hitl_scenarios_all_have_a2ui(scenarios):
    for cfg in scenarios.list_all():
        if cfg.execution.orchestration == "hitl":
            assert cfg.a2ui.enabled, f"{cfg.name} is hitl but a2ui disabled"
            # state_machine 至少有一处声明 (a2ui / execution.hitl / resource_dirs)
            has_state_machine = (
                cfg.a2ui.state_machine
                or (cfg.execution.hitl and cfg.execution.hitl.state_machine)
                or cfg.resource_dirs.get("state_machine")
            )
            assert has_state_machine, f"{cfg.name} is hitl but no state_machine declared"
