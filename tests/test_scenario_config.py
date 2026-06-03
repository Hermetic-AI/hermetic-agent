"""ScenarioConfig Pydantic schema 单测."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from openagent.scenarios.config import (
    A2UIConfig,
    ExecutionConfig,
    InitialSkillConfig,
    ProgressiveSkillConfig,
    ResourcesConfig,
    RoutingConfig,
    ScenarioConfig,
    SecurityConfig,
    WorkspaceConfig,
)


def _ps() -> ProgressiveSkillConfig:
    """默认 progressive_skill (strategy=none, 不要求 load_on_state)."""
    return ProgressiveSkillConfig(strategy="none")


def _ws(path: str = "/tmp/proj") -> WorkspaceConfig:
    return WorkspaceConfig(workspace_dirs=[path])


def _exec(orch: str = "single", skills: list[str] | None = None) -> ExecutionConfig:
    return ExecutionConfig(orchestration=orch, skills=skills or [])  # type: ignore[arg-type]


def _routing() -> RoutingConfig:
    return RoutingConfig()


def _cfg(**kw):
    base = {
        "name": "test",
        "version": "1.0.0",
        "routing": _routing(),
        "execution": _exec(),
        "workspace": _ws(),
        "progressive_skill": _ps(),
    }
    base.update(kw)
    return ScenarioConfig(**base)


# ----------------------------------------------------------------------
# 基础校验
# ----------------------------------------------------------------------


def test_init_minimal():
    cfg = _cfg()
    assert cfg.name == "test"
    assert cfg.version == "1.0.0"
    assert cfg.enabled is True
    assert cfg.tier == "silver"


def test_name_pattern_must_be_snake_case():
    with pytest.raises(ValidationError):
        ScenarioConfig(
            name="Invalid-Name",
            version="1.0.0",
            routing=_routing(),
            execution=_exec(),
            workspace=_ws(),
        )


def test_version_semver_required():
    with pytest.raises(ValidationError):
        ScenarioConfig(
            name="test",
            version="1.0",
            routing=_routing(),
            execution=_exec(),
            workspace=_ws(),
        )


# ----------------------------------------------------------------------
# security.denied_commands 必含 rm -rf / sudo / dd
# ----------------------------------------------------------------------


def test_security_denied_commands_required():
    with pytest.raises(ValidationError):
        SecurityConfig(denied_commands=["shutdown"])


def test_security_denied_commands_all_required():
    with pytest.raises(ValidationError):
        # 缺 dd
        SecurityConfig(denied_commands=["rm -rf", "sudo"])


def test_security_denied_commands_pass_with_all():
    cfg = SecurityConfig(denied_commands=["rm -rf", "sudo", "dd"])
    assert "rm -rf" in cfg.denied_commands


def test_security_denied_commands_pass_with_similar():
    cfg = SecurityConfig(denied_commands=["rm -rf root", "sudo bash", "dd if=/dev/zero"])
    assert len(cfg.denied_commands) == 3


# ----------------------------------------------------------------------
# workspace_dirs[0] 不能是根路径
# ----------------------------------------------------------------------


def test_workspace_not_root_path_slash():
    with pytest.raises(ValidationError):
        WorkspaceConfig(workspace_dirs=["/"])


def test_workspace_not_root_path_tilde():
    with pytest.raises(ValidationError):
        WorkspaceConfig(workspace_dirs=["~"])


def test_workspace_not_root_path_home_var():
    with pytest.raises(ValidationError):
        WorkspaceConfig(workspace_dirs=["$HOME"])


def test_workspace_not_root_path_home_brace():
    with pytest.raises(ValidationError):
        WorkspaceConfig(workspace_dirs=["${HOME}"])


def test_workspace_placeholder_accepted():
    cfg = WorkspaceConfig(workspace_dirs=["${PROJECT_DIR}"])
    assert cfg.workspace_dirs == ["${PROJECT_DIR}"]


def test_workspace_project_relative_accepted():
    cfg = WorkspaceConfig(workspace_dirs=["/work/tenants/foo/projects/bar"])
    assert cfg.workspace_dirs[0] == "/work/tenants/foo/projects/bar"


# ----------------------------------------------------------------------
# HITL 必 a2ui.enabled=true
# ----------------------------------------------------------------------


def test_hitl_requires_a2ui_enabled():
    with pytest.raises(ValidationError) as ei:
        ScenarioConfig(
            name="hl",
            version="1.0.0",
            routing=_routing(),
            execution=_exec("hitl"),
            workspace=_ws(),
            a2ui=A2UIConfig(enabled=False),
        )
    assert "a2ui.enabled" in str(ei.value)


def test_hitl_with_a2ui_enabled_passes():
    cfg = ScenarioConfig(
        name="hl",
        version="1.0.0",
        routing=_routing(),
        execution=_exec("hitl"),
        workspace=_ws(),
        a2ui=A2UIConfig(enabled=True),
        progressive_skill=_ps(),
    )
    assert cfg.a2ui.enabled is True


# ----------------------------------------------------------------------
# on_demand 必 load_on_state 非空
# ----------------------------------------------------------------------


def test_on_demand_requires_load_on_state():
    with pytest.raises(ValidationError) as ei:
        ScenarioConfig(
            name="od",
            version="1.0.0",
            routing=_routing(),
            execution=_exec(),
            workspace=_ws(),
            progressive_skill=ProgressiveSkillConfig(
                strategy="on_demand",
                load_on_state={},
            ),
        )
    assert "load_on_state" in str(ei.value)


def test_on_demand_with_load_on_state_passes():
    cfg = ScenarioConfig(
        name="od",
        version="1.0.0",
        routing=_routing(),
        execution=_exec(),
        workspace=_ws(),
        progressive_skill=ProgressiveSkillConfig(
            strategy="on_demand",
            load_on_state={"S05": ["book-flight:state-s05"]},
        ),
    )
    assert "S05" in cfg.progressive_skill.load_on_state


def test_strategy_all_does_not_require_load_on_state():
    cfg = ScenarioConfig(
        name="al",
        version="1.0.0",
        routing=_routing(),
        execution=_exec(),
        workspace=_ws(),
        progressive_skill=ProgressiveSkillConfig(strategy="all"),
    )
    assert cfg.progressive_skill.strategy == "all"


# ----------------------------------------------------------------------
# 枚举校验
# ----------------------------------------------------------------------


def test_tool_level_enum_validation():
    cfg = SecurityConfig(tool_level="safe")
    assert cfg.tool_level == "safe"
    with pytest.raises(ValidationError):
        SecurityConfig(tool_level="god_mode")  # type: ignore[arg-type]


def test_orchestration_enum_validation():
    cfg = ExecutionConfig(orchestration="chain")
    assert cfg.orchestration == "chain"
    with pytest.raises(ValidationError):
        ExecutionConfig(orchestration="anyhow")  # type: ignore[arg-type]


def test_tier_enum_validation():
    cfg = ScenarioConfig(
        name="t",
        version="1.0.0",
        routing=_routing(),
        execution=_exec(),
        workspace=_ws(),
        tier="platinum",
        progressive_skill=_ps(),
    )
    assert cfg.tier == "platinum"
    with pytest.raises(ValidationError):
        ScenarioConfig(
            name="t2",
            version="1.0.0",
            routing=_routing(),
            execution=_exec(),
            workspace=_ws(),
            tier="diamond",  # type: ignore[arg-type]
            progressive_skill=_ps(),
        )


# ----------------------------------------------------------------------
# 子模型: 单独校验
# ----------------------------------------------------------------------


def test_initial_skill_config():
    s = InitialSkillConfig(name="book-flight", mode="summary")
    assert s.name == "book-flight"


def test_resources_config_defaults():
    r = ResourcesConfig()
    assert r.timeout == 300
    assert r.agent is None
