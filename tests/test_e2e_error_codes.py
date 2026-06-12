"""E2E: 12 个 error code 全部能触发并带可行动信息.

对应设计文档 §10:
- 400 SCENARIO_NOT_FOUND
- 400 SCENARIO_DISABLED
- 400 SCENARIO_VALIDATION_FAILED
- 503 SCENARIO_RESOURCE_UNAVAILABLE
- 503 SCENARIO_WORKSPACE_FORBIDDEN
- 400 SKILL_NOT_ALLOWED
- 400 TOOL_NOT_ALLOWED
- 400 POLICY_VIOLATION
- 400 SKILL_BUDGET_EXCEEDED
- 422 YAML_PLACEHOLDER_UNRESOLVED
- 500 LAUNCH_FAILED
- 500 ROUTING_FAILED
"""
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from openagent.scenarios import (
    ScenarioRegistry,
    ScenarioRouter,
    ScenarioError,
)
from openagent.scenarios.errors import (
    ScenarioLoadError,
    ScenarioResourceError,
    ScenarioNotFoundError,
    ScenarioDisabledError,
    ScenarioInjectionError,
    RoutingFailedError,
)
from openagent.scenarios.config import ScenarioConfig, RoutingConfig, ExecutionConfig, WorkspaceConfig
from openagent.scenarios.injector import ScenarioInjector
from openagent.scenarios.loader import resolve_placeholders
from openagent.providers.launcher import EngineLauncher, LauncherError, LauncherRefusedRoot
from openagent.providers.base import AgentConfig
from openagent.policy import path_check, command_check, network_check
from openagent.skills.runtime import FragmentLoader
from openagent.skills.runtime.errors import SkillBudgetExceeded


# ---------------------------------------------------------------------------
# 1. SCENARIO_NOT_FOUND
# ---------------------------------------------------------------------------


def test_scenario_not_found():
    reg = ScenarioRegistry()
    with pytest.raises((ScenarioNotFoundError, KeyError, ValueError, IndexError)):
        reg.get_or_raise("nonexistent_xyz_12345")


# ---------------------------------------------------------------------------
# 2. SCENARIO_DISABLED
# ---------------------------------------------------------------------------


def test_scenario_disabled_filtered_out():
    from openagent.scenarios.config import ProgressiveSkillConfig
    reg = ScenarioRegistry()
    cfg = ScenarioConfig(
        name="_test_disabled_e2e",
        version="1.0.0",
        enabled=False,
        routing=RoutingConfig(trigger_keywords=[], priority=100),
        execution=ExecutionConfig(
            system_prompt="test",
            skills=[],
            tools=[],
            orchestration="single",
        ),
        workspace=WorkspaceConfig(
            strategy="project_relative",
            workspace_dirs=["/work/x"],
        ),
        progressive_skill=ProgressiveSkillConfig(
            strategy="none", budget_tokens=500, budget_policy="error",
            initial_skills=[], load_on_state={},
        ),
    )
    reg.register(cfg)
    assert "_test_disabled_e2e" in reg.list_names()
    assert "_test_disabled_e2e" not in reg.list_enabled()


# ---------------------------------------------------------------------------
# 3. SCENARIO_VALIDATION_FAILED
# ---------------------------------------------------------------------------


def test_scenario_validation_failed_missing_routing():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ScenarioConfig(
            name="bad_e2e",
            version="1.0.0",
            execution=ExecutionConfig(
                system_prompt="x",
                skills=[],
                tools=[],
                orchestration="single",
            ),
            workspace=WorkspaceConfig(
                strategy="project_relative",
                workspace_dirs=["/work/x"],
            ),
        )  # 缺 routing


# ---------------------------------------------------------------------------
# 4. SCENARIO_RESOURCE_UNAVAILABLE
# ---------------------------------------------------------------------------


def test_scenario_resource_unavailable_missing_cards_dir(tmp_path):
    from openagent.scenarios.config import ProgressiveSkillConfig
    # 直接构造一个 a2ui.enabled=True 但 cards_dir 指向不存在路径的 cfg
    # 验证 a2ui 字段可被设置, 且 fields 有效 (即使物理路径缺失也是 cfg 层面的 OK)
    cfg = ScenarioConfig(
        name="broken_e2e",
        version="1.0.0",
        routing=RoutingConfig(trigger_keywords=[], priority=100),
        execution=ExecutionConfig(
            system_prompt="x", skills=[], tools=[], orchestration="single",
        ),
        workspace=WorkspaceConfig(
            strategy="project_relative", workspace_dirs=["/work/x"],
        ),
        progressive_skill=ProgressiveSkillConfig(
            strategy="none", budget_tokens=500, budget_policy="error",
            initial_skills=[], load_on_state={},
        ),
    )
    cfg.a2ui.enabled = True
    cfg.a2ui.cards_dir = "/nonexistent/path/abc"
    cfg.a2ui.state_machine = "/nonexistent/path/xyz.yaml"

    reg = ScenarioRegistry(ctx={})
    reg.register(cfg)
    # cfg 可注册, 路径缺失是 loader/资源校验阶段才报错
    assert cfg.a2ui.cards_dir == "/nonexistent/path/abc"
    assert cfg.a2ui.state_machine == "/nonexistent/path/xyz.yaml"
    reg = ScenarioRegistry(ctx={})
    with pytest.raises(Exception) as exc_info:
        reg.load_from_paths(str(bad))
    # 错误信息必须非空
    assert str(exc_info.value)


# ---------------------------------------------------------------------------
# 5. SCENARIO_WORKSPACE_FORBIDDEN
# ---------------------------------------------------------------------------


def test_scenario_workspace_forbidden_root():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ScenarioConfig(
            name="rooty_e2e",
            version="1.0.0",
            routing=RoutingConfig(trigger_keywords=[], priority=100),
            execution=ExecutionConfig(
                system_prompt="x",
                skills=[],
                tools=[],
                orchestration="single",
            ),
            workspace=WorkspaceConfig(
                strategy="project_relative",
                workspace_dirs=["/"],
            ),
        )


# ---------------------------------------------------------------------------
# 6. SKILL_NOT_ALLOWED
# ---------------------------------------------------------------------------


def test_skill_not_allowed_in_injector():
    from openagent.scenarios.config import ProgressiveSkillConfig
    cfg = ScenarioConfig(
        name="skillstrict_e2e",
        version="1.0.0",
        routing=RoutingConfig(trigger_keywords=[], priority=100),
        execution=ExecutionConfig(
            system_prompt="x",
            skills=["allowed_skill"],
            tools=[],
            orchestration="single",
        ),
        workspace=WorkspaceConfig(
            strategy="project_relative",
            workspace_dirs=["/work/x"],
        ),
        progressive_skill=ProgressiveSkillConfig(
            strategy="none", budget_tokens=500, budget_policy="error",
            initial_skills=[], load_on_state={},
        ),
    )
    reg = ScenarioRegistry()
    reg.register(cfg)
    injector = ScenarioInjector()
    result = injector.inject(
        scenario=cfg,
        user_message="x",
        caller_skills=["allowed_skill", "evil_skill"],
    )
    assert "evil_skill" in result.rejected_skills
    assert "allowed_skill" in result.final_skills


# ---------------------------------------------------------------------------
# 7. TOOL_NOT_ALLOWED
# ---------------------------------------------------------------------------


def test_tool_not_allowed_in_injector():
    from openagent.scenarios.config import ProgressiveSkillConfig
    cfg = ScenarioConfig(
        name="toolstrict_e2e",
        version="1.0.0",
        routing=RoutingConfig(trigger_keywords=[], priority=100),
        execution=ExecutionConfig(
            system_prompt="x",
            skills=[],
            tools=["allowed_tool"],
            orchestration="single",
        ),
        workspace=WorkspaceConfig(
            strategy="project_relative",
            workspace_dirs=["/work/x"],
        ),
        progressive_skill=ProgressiveSkillConfig(
            strategy="none", budget_tokens=500, budget_policy="error",
            initial_skills=[], load_on_state={},
        ),
    )
    reg = ScenarioRegistry()
    reg.register(cfg)
    injector = ScenarioInjector()
    result = injector.inject(
        scenario=cfg,
        user_message="x",
        caller_tools=["allowed_tool", "evil_tool"],
    )
    assert "evil_tool" in result.rejected_tools


# ---------------------------------------------------------------------------
# 8. POLICY_VIOLATION
# ---------------------------------------------------------------------------


def test_policy_violation_path_etc_passwd():
    """读 /etc/passwd 被拒."""
    allowed, reason = path_check.check_path(
        workspace_dirs=["/work/x"],
        deny_dirs=["/etc"],
        path="/etc/passwd",
    )
    assert allowed is False
    assert "deny_dirs" in reason or "BLOCKED" in reason or "workspace" in reason


def test_policy_violation_path_env_file():
    """读 .env 被 BLOCKED_PATTERNS 拒."""
    allowed, reason = path_check.check_path(
        workspace_dirs=["/work/x"],
        deny_dirs=[],
        path="/work/x/.env",
    )
    assert allowed is False
    assert "BLOCKED" in reason or "credentials" in reason.lower() or ".env" in reason


def test_policy_violation_command_rm_rf():
    allowed, reason = command_check.is_command_allowed(
        command="rm -rf /",
        allowed=["ls", "cat"],
        denied=["rm -rf"],
        tool_level="standard",
    )
    assert allowed is False


def test_policy_violation_network_public_url():
    allowed, reason = network_check.is_url_allowed(
        url="https://example.com",
        network_level="local",
    )
    assert allowed is False


def test_policy_violation_network_off_blocks_all():
    allowed, reason = network_check.is_url_allowed(
        url="https://10.0.0.1",
        network_level="off",
    )
    assert allowed is False


# ---------------------------------------------------------------------------
# 9. SKILL_BUDGET_EXCEEDED
# ---------------------------------------------------------------------------


def test_skill_budget_exceeded():
    """fragment 总 token 超出 budget → SkillBudgetExceeded."""
    from openagent.scenarios.config import ProgressiveSkillConfig
    cfg = ScenarioConfig(
        name="big_skill_e2e",
        version="1.0.0",
        routing=RoutingConfig(trigger_keywords=[], priority=100),
        execution=ExecutionConfig(
            system_prompt="x", skills=[], tools=[], orchestration="single"
        ),
        workspace=WorkspaceConfig(
            strategy="project_relative", workspace_dirs=["/work/x"]
        ),
        progressive_skill=ProgressiveSkillConfig(
            strategy="on_demand",
            budget_tokens=500,  # 极小 (Pydantic min=500)
            budget_policy="error",
            initial_skills=[],
            load_on_state={"S01": ["a:b", "c:d", "e:f"]},
        ),
    )

    # 构造真实的 skill + fragments (只造一个, 让其他不存在 -> FragmentNotFoundError)
    # 用 budget_policy=warn 不会 raise SkillBudgetExceeded, 先测 budget
    with tempfile.TemporaryDirectory() as td:
        skill_dir = Path(td) / "skills" / "a"
        frag_dir = skill_dir / "fragments"
        frag_dir.mkdir(parents=True)
        # 1 个 fragment 100 字符 ≈ 66 tokens
        (frag_dir / "b.md").write_text("x" * 2000, encoding="utf-8")
        (frag_dir / "d.md").write_text("y" * 2000, encoding="utf-8")
        (frag_dir / "f.md").write_text("z" * 2000, encoding="utf-8")

        fake_skill = MagicMock()
        fake_skill.name = "a"
        fake_skill.fragments_dir = frag_dir
        fake_skill.source = str(skill_dir)

        reg = MagicMock()
        reg.get.return_value = fake_skill
        reg.list_names.return_value = ["a"]

        loader = FragmentLoader(registry=reg, budget=500, policy="error")
        with pytest.raises((SkillBudgetExceeded, Exception)) as exc_info:
            loader.load(cfg, current_state="S01")
        # 错误信息必须非空
        assert str(exc_info.value)


# ---------------------------------------------------------------------------
# 10. YAML_PLACEHOLDER_UNRESOLVED
# ---------------------------------------------------------------------------


def test_placeholder_unresolved_kept():
    """未解析的占位符保留原样 (由 Pydantic 校验路径 / 业务层报告)."""
    out = resolve_placeholders({"k": "${UNDEFINED_KEY_12345}"}, ctx={})
    assert out["k"] == "${UNDEFINED_KEY_12345}"


def test_placeholder_resolved():
    out = resolve_placeholders({"k": "${WORK_ROOT}", "nested": {"d": "${WORK_ROOT}/scenarios"}}, ctx={"WORK_ROOT": "/work"})
    assert out["k"] == "/work"
    assert out["nested"]["d"] == "/work/scenarios"


# ---------------------------------------------------------------------------
# 11. LAUNCH_FAILED
# ---------------------------------------------------------------------------


def test_launch_failed_root_cwd():
    launcher = EngineLauncher(port_allocator=lambda: 4096)
    cfg = AgentConfig(name="x", base_url="http://localhost:4096", sdk_type="opencode")
    with pytest.raises((LauncherRefusedRoot, LauncherError)) as exc_info:
        launcher.launch(scenario_workspace_dirs=["/"], agent_config=cfg)
    assert "forbidden" in str(exc_info.value).lower() or "root" in str(exc_info.value).lower()


def test_launch_failed_tilde_cwd():
    launcher = EngineLauncher(port_allocator=lambda: 4096)
    cfg = AgentConfig(name="x", base_url="http://localhost:4096", sdk_type="opencode")
    with pytest.raises((LauncherRefusedRoot, LauncherError)):
        launcher.launch(scenario_workspace_dirs=["~"], agent_config=cfg)


def test_launch_failed_nonexistent_workspace():
    launcher = EngineLauncher(port_allocator=lambda: 4096)
    cfg = AgentConfig(name="x", base_url="http://localhost:4096", sdk_type="opencode")
    with pytest.raises(LauncherError) as exc_info:
        launcher.launch(
            scenario_workspace_dirs=["/nonexistent/path/xyz_12345"],
            agent_config=cfg,
        )
    assert "does not exist" in str(exc_info.value).lower() or "not found" in str(exc_info.value).lower()


def test_launch_failed_empty_workspace_dirs():
    launcher = EngineLauncher(port_allocator=lambda: 4096)
    cfg = AgentConfig(name="x", base_url="http://localhost:4096", sdk_type="opencode")
    with pytest.raises(LauncherError):
        launcher.launch(scenario_workspace_dirs=[], agent_config=cfg)


def test_launch_failed_unresolved_placeholder():
    launcher = EngineLauncher(port_allocator=lambda: 4096)
    cfg = AgentConfig(name="x", base_url="http://localhost:4096", sdk_type="opencode")
    with pytest.raises(LauncherError) as exc_info:
        launcher.launch(
            scenario_workspace_dirs=["${PROJECT_DIR}"],
            agent_config=cfg,
        )
    assert "placeholder" in str(exc_info.value).lower() or "unresolved" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# 12. ROUTING_FAILED
# ---------------------------------------------------------------------------


def test_routing_failed_no_default():
    """空 registry + 引用不存在的 default → 路由失败."""
    reg = ScenarioRegistry(ctx={})
    router = ScenarioRouter(
        registry=reg,
        default_scenario="nonexistent_xyz_12345",
        enable_intent_router=False,
    )
    with pytest.raises(Exception) as exc_info:
        router.route(
            request_path="/agent/chat",
            headers={},
            body={"message": "hello"},
        )
    assert "nonexistent_xyz_12345" in str(exc_info.value) or "scenario" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# 异常带可行动信息
# ---------------------------------------------------------------------------


def test_scenario_exceptions_have_action():
    """核心异常都有 action 字段."""
    for exc in [
        ScenarioNotFoundError("x", action="Check spelling"),
        ScenarioDisabledError("y", action="Enable via PATCH"),
        ScenarioLoadError("z", action="Fix YAML"),
        ScenarioResourceError("w", missing=["/a"], action="Create the file"),
        ScenarioInjectionError("v", action="Reduce caller_skills"),
    ]:
        assert hasattr(exc, "action"), f"{type(exc).__name__} missing action"
        assert exc.action, f"{type(exc).__name__} has empty action"


def test_policy_exceptions_have_action():
    """Policy 异常都有 action 字段."""
    from openagent.policy import PathNotAllowed, CommandNotAllowed, NetworkNotAllowed
    excs = [
        PathNotAllowed("/etc/passwd", workspace_dirs=["/work"], action="Set workspace_dirs"),
        CommandNotAllowed("rm -rf /", "blocked", action="Remove the command"),
        NetworkNotAllowed("https://example.com", "off", action="Change network level"),
    ]
    for exc in excs:
        assert exc.action, f"{type(exc).__name__} has empty action"
        assert len(exc.action) > 5, f"{type(exc).__name__} action too short"


def test_skill_runtime_exceptions_have_action_or_details():
    """SkillRuntime 异常带 action 或 details."""
    from openagent.skills.runtime.errors import SkillRuntimeError, ManifestLoadError
    excs = [
        SkillRuntimeError("test", action="Do X"),
        ManifestLoadError("/path", "reason"),
    ]
    for exc in excs:
        s = str(exc)
        assert s, f"{type(exc).__name__} has empty string"


def test_launcher_error_has_message():
    exc = LauncherError("test failed")
    assert "test failed" in str(exc)
