"""E2E: 现有基座 scenario 的配置矩阵全对.

Phase 1 重构后, 基座 work/scenarios/ 仅含 2 个 scenario:
  - _default: 兜底场景, tool_level=safe, a2ui disabled
  - example_echo: 示例场景, 演示 SKILL 引用, a2ui enabled

历史测试覆盖的 flight_booking / expense_audit / customer_service /
code_review 业务场景全部下沉到 work/shared/skills/<skill-name>/
的 SKILL 包内, 不再在基座 work/scenarios/ 里.
"""

from pathlib import Path

import pytest

from hermetic_agent.scenarios import ScenarioRegistry


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
# _default (基座兜底)
# ---------------------------------------------------------------------------


def test_default_minimal_no_skills(scenarios):
    cfg = scenarios.get("_default")
    assert cfg.execution.skills == []
    assert cfg.execution.tools == []


def test_default_security_strictest(scenarios):
    cfg = scenarios.get("_default")
    assert cfg.security.tool_level == "safe"
    assert cfg.security.network == "off"
    assert cfg.security.max_turns <= 5
    assert cfg.security.max_budget_usd <= 0.5


def test_default_progressive_none(scenarios):
    cfg = scenarios.get("_default")
    assert cfg.progressive_skill.strategy == "none"


def test_default_a2ui_disabled(scenarios):
    cfg = scenarios.get("_default")
    assert cfg.a2ui.enabled is False


# ---------------------------------------------------------------------------
# example_echo (基座示例)
# ---------------------------------------------------------------------------


def test_example_echo_a2ui_enabled(scenarios):
    cfg = scenarios.get("example_echo")
    assert cfg.a2ui.enabled is True
    assert cfg.a2ui.protocol == "auip"


def test_example_echo_references_skill(scenarios):
    cfg = scenarios.get("example_echo")
    assert "example-echo-skill" in cfg.execution.skills


def test_example_echo_security_safe(scenarios):
    cfg = scenarios.get("example_echo")
    assert cfg.security.tool_level == "safe"


# ---------------------------------------------------------------------------
# 跨场景一致性 (基座强制约束)
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
