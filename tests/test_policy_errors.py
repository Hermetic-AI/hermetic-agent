"""errors 模块单测."""

from __future__ import annotations

import pytest

from openagent.policy.errors import (
    BudgetExceeded,
    CommandNotAllowed,
    NetworkNotAllowed,
    PathNotAllowed,
    PolicyError,
    PolicyViolation,
)


def test_policy_error_is_exception() -> None:
    err = PolicyError("boom")
    assert isinstance(err, Exception)
    assert err.message == "boom"
    assert err.action  # 默认 action 非空


def test_policy_violation_is_policy_error() -> None:
    err = PolicyViolation("v")
    assert isinstance(err, PolicyError)


def test_path_not_allowed_carries_path() -> None:
    err = PathNotAllowed("/etc/passwd", workspace_dirs=["/work/x"])
    assert err.path == "/etc/passwd"
    assert err.workspace_dirs == ["/work/x"]
    assert "workspace_dirs" in str(err) or "Action" in str(err)
    assert "Action" in str(err)


def test_command_not_allowed_has_action() -> None:
    err = CommandNotAllowed("rm -rf /", denied_reason="matches denied pattern")
    assert "rm -rf /" in str(err)
    assert err.action


def test_network_not_allowed_message() -> None:
    err = NetworkNotAllowed("https://example.com", network_level="off")
    assert "https://example.com" in str(err)
    assert "off" in str(err)
    assert err.action


def test_budget_exceeded_has_kind_and_limits() -> None:
    err = BudgetExceeded("turns", used=40, limit=20)
    assert err.kind == "turns"
    assert err.used == 40
    assert err.limit == 20
    assert "40" in str(err) and "20" in str(err)


def test_all_subclasses_inherit_policy_violation() -> None:
    assert issubclass(PathNotAllowed, PolicyViolation)
    assert issubclass(CommandNotAllowed, PolicyViolation)
    assert issubclass(NetworkNotAllowed, PolicyViolation)
    assert issubclass(BudgetExceeded, PolicyViolation)


def test_policy_violation_inherits_policy_error() -> None:
    assert issubclass(PolicyViolation, PolicyError)


def test_action_in_str() -> None:
    err = PathNotAllowed("/foo", workspace_dirs=["/bar"])
    s = str(err)
    assert "Action:" in s
