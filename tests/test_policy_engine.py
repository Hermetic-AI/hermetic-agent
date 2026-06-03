"""engine 模块单测: EffectivePolicy / merge / PolicyEngine."""

from __future__ import annotations

import pytest

from openagent.policy.audit import InMemoryAuditLogger
from openagent.policy.engine import EffectivePolicy, PolicyEngine, merge
from openagent.policy.errors import (
    BudgetExceeded,
    CommandNotAllowed,
    NetworkNotAllowed,
    PathNotAllowed,
)


def test_effective_policy_defaults() -> None:
    p = EffectivePolicy()
    assert p.tool_level == "standard"
    assert p.workspace_dirs == []
    assert p.deny_dirs == []
    assert p.network == "local"
    assert p.max_turns == 30
    assert p.max_budget_usd == 5.0
    assert p.require_approval_for_writes is True


def test_effective_policy_custom_values() -> None:
    p = EffectivePolicy(
        tool_level="safe",
        workspace_dirs=["/work/x"],
        allowed_commands=["ls"],
        network="off",
        max_turns=5,
    )
    assert p.tool_level == "safe"
    assert p.workspace_dirs == ["/work/x"]
    assert p.allowed_commands == ["ls"]
    assert p.network == "off"
    assert p.max_turns == 5


def test_merge_request_override() -> None:
    base = EffectivePolicy(
        tool_level="standard",
        max_turns=30,
        max_budget_usd=5.0,
        allowed_commands=["ls", "cat"],
    )
    merged = merge(base, {"max_turns": 10, "max_budget_usd": 1.0})
    assert merged.max_turns == 10
    assert merged.max_budget_usd == 1.0
    # 其他保留
    assert merged.tool_level == "standard"
    assert merged.allowed_commands == ["ls", "cat"]


def test_merge_none_returns_copy() -> None:
    base = EffectivePolicy(tool_level="safe", max_turns=10)
    merged = merge(base, None)
    assert merged.tool_level == "safe"
    assert merged.max_turns == 10
    # 应该是新对象
    assert merged is not base


def test_merge_override_cannot_relax_tool_level() -> None:
    """config=safe, override=full → 保留 safe (不能更宽松)."""
    base = EffectivePolicy(tool_level="safe")
    merged = merge(base, {"tool_level": "full"})
    assert merged.tool_level == "safe"


def test_merge_override_can_tighten_tool_level() -> None:
    """config=standard, override=safe → 收紧到 safe."""
    base = EffectivePolicy(tool_level="standard")
    merged = merge(base, {"tool_level": "safe"})
    assert merged.tool_level == "safe"


def test_merge_override_cannot_relax_network() -> None:
    """config=off, override=any → 保留 off."""
    base = EffectivePolicy(network="off")
    merged = merge(base, {"network": "any"})
    assert merged.network == "off"


def test_merge_override_can_tighten_network() -> None:
    """config=local, override=off → 收紧到 off."""
    base = EffectivePolicy(network="local")
    merged = merge(base, {"network": "off"})
    assert merged.network == "off"


def test_merge_workspace_dirs_intersection() -> None:
    """workspace_dirs override 取交集 (子集)."""
    base = EffectivePolicy(workspace_dirs=["/a", "/b", "/c"])
    merged = merge(base, {"workspace_dirs": ["/a", "/b"]})
    assert sorted(merged.workspace_dirs) == ["/a", "/b"]


def test_merge_workspace_dirs_no_intersection_keeps_base() -> None:
    base = EffectivePolicy(workspace_dirs=["/a"])
    merged = merge(base, {"workspace_dirs": ["/x"]})
    assert merged.workspace_dirs == ["/a"]


def test_policy_engine_init() -> None:
    p = EffectivePolicy(workspace_dirs=["/work"])
    engine = PolicyEngine(policy=p)
    assert engine.policy is p


def test_policy_engine_with_override() -> None:
    base = EffectivePolicy(tool_level="standard", max_turns=30)
    engine = PolicyEngine(policy=base)
    new = engine.with_override({"max_turns": 5})
    assert new.policy.max_turns == 5
    assert engine.policy.max_turns == 30  # 原 engine 不变


def test_policy_engine_check_path_allowed() -> None:
    p = EffectivePolicy(workspace_dirs=["/work"], deny_dirs=[])
    engine = PolicyEngine(policy=p)
    assert engine.check_path("/work/x.py") is True


def test_policy_engine_check_path_blocked_raises() -> None:
    p = EffectivePolicy(workspace_dirs=["/work"], deny_dirs=[])
    engine = PolicyEngine(policy=p)
    with pytest.raises(PathNotAllowed):
        engine.check_path("/work/.env")


def test_policy_engine_check_path_outside_workspace_raises(tmp_path) -> None:
    import os
    # 用实际存在的路径做 workspace, 让 normalize() 不抛
    ws = str(tmp_path / "ws")
    os.makedirs(ws, exist_ok=True)
    p = EffectivePolicy(workspace_dirs=[ws])
    engine = PolicyEngine(policy=p)
    with pytest.raises(PathNotAllowed):
        engine.check_path("/etc/passwd")


def test_policy_engine_check_command_allowed() -> None:
    p = EffectivePolicy(
        tool_level="standard",
        allowed_commands=["ls", "cat"],
        denied_commands=["rm -rf"],
    )
    engine = PolicyEngine(policy=p)
    assert engine.check_command("ls -la") is True


def test_policy_engine_check_command_denied_raises() -> None:
    p = EffectivePolicy(
        tool_level="standard",
        allowed_commands=["ls"],
        denied_commands=["rm -rf"],
    )
    engine = PolicyEngine(policy=p)
    with pytest.raises(CommandNotAllowed):
        engine.check_command("rm -rf /")


def test_policy_engine_check_url_off() -> None:
    p = EffectivePolicy(network="off")
    engine = PolicyEngine(policy=p)
    with pytest.raises(NetworkNotAllowed):
        engine.check_url("https://example.com")


def test_policy_engine_check_url_local() -> None:
    p = EffectivePolicy(network="local")
    engine = PolicyEngine(policy=p)
    assert engine.check_url("http://10.0.0.1:8080") is True
    with pytest.raises(NetworkNotAllowed):
        engine.check_url("https://example.com")


def test_policy_engine_check_turn() -> None:
    p = EffectivePolicy(max_turns=10)
    engine = PolicyEngine(policy=p)
    assert engine.check_turn(5) is True
    assert engine.check_turn(10) is True  # 等于不算超出
    with pytest.raises(BudgetExceeded):
        engine.check_turn(11)


def test_policy_engine_check_budget() -> None:
    p = EffectivePolicy(max_budget_usd=1.0)
    engine = PolicyEngine(policy=p)
    assert engine.check_budget(0.5) is True
    with pytest.raises(BudgetExceeded):
        engine.check_budget(1.5)


def test_policy_engine_records_audit() -> None:
    audit = InMemoryAuditLogger()
    p = EffectivePolicy(workspace_dirs=["/work"], network="off")
    engine = PolicyEngine(policy=p, audit=audit)
    with pytest.raises(PathNotAllowed):
        engine.check_path("/etc/passwd")
    with pytest.raises(NetworkNotAllowed):
        engine.check_url("https://example.com")
    # 至少 2 条审计
    events = audit.all()
    assert len(events) >= 2
    actions = [e.action for e in events]
    assert "path_check" in actions
    assert "network_check" in actions


def test_policy_engine_no_audit_does_not_crash() -> None:
    p = EffectivePolicy(workspace_dirs=["/work"])
    engine = PolicyEngine(policy=p)  # audit=None
    engine.check_path("/work/x")  # 不应抛


def test_merge_empty_override() -> None:
    base = EffectivePolicy(tool_level="standard")
    merged = merge(base, {})
    assert merged == base or (merged.tool_level == base.tool_level)
