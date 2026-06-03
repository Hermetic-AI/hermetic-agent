"""command_check 模块单测."""

from __future__ import annotations

import pytest

from openagent.policy.command_check import (
    has_metacharacter,
    is_command_allowed,
)


def test_command_blocks_rm_rf() -> None:
    allowed, reason = is_command_allowed(
        "rm -rf /", allowed=["rm"], denied=["rm -rf"]
    )
    assert allowed is False
    assert "rm -rf" in reason or "denied" in reason


def test_command_blocks_sudo() -> None:
    allowed, _ = is_command_allowed(
        "sudo apt install foo", allowed=["apt"], denied=["sudo"]
    )
    assert allowed is False


def test_command_splits_chained_and() -> None:
    """`ls && rm -rf /` 中 rm -rf 必须被拒."""
    allowed, reason = is_command_allowed(
        "ls && rm -rf /", allowed=["ls", "rm"], denied=["rm -rf"]
    )
    assert allowed is False
    assert "rm -rf" in reason


def test_command_splits_chained_pipe() -> None:
    allowed, _ = is_command_allowed(
        "ls | grep x", allowed=["ls", "grep"], denied=[]
    )
    assert allowed is True


def test_command_splits_chained_semicolon() -> None:
    allowed, _ = is_command_allowed(
        "ls; rm x", allowed=["ls"], denied=[]
    )
    assert allowed is False  # rm 不在 allowed


def test_command_splits_chained_or() -> None:
    allowed, _ = is_command_allowed(
        "ls || true", allowed=["ls", "true"], denied=[]
    )
    assert allowed is True


def test_command_safe_blocks_redirect() -> None:
    """safe 档 + 重定向 → 拒绝."""
    allowed, reason = is_command_allowed(
        "ls > /tmp/x", allowed=["ls"], denied=[], tool_level="safe"
    )
    assert allowed is False
    assert "metacharacter" in reason


def test_command_safe_blocks_backtick() -> None:
    allowed, _ = is_command_allowed(
        "ls `whoami`", allowed=["ls"], denied=[], tool_level="safe"
    )
    assert allowed is False


def test_command_safe_blocks_dollar_paren() -> None:
    allowed, _ = is_command_allowed(
        "ls $(whoami)", allowed=["ls"], denied=[], tool_level="safe"
    )
    assert allowed is False


def test_command_standard_allows_redirect() -> None:
    """standard 档 + 重定向不禁止 (依赖 denied 列表)."""
    allowed, _ = is_command_allowed(
        "ls > /tmp/x", allowed=["ls"], denied=[], tool_level="standard"
    )
    assert allowed is True


def test_command_whitelist_must_match() -> None:
    """非空白名单: 第一个 token 必须在白名单里."""
    allowed, _ = is_command_allowed(
        "curl https://example.com", allowed=["ls", "cat"], denied=[]
    )
    assert allowed is False


def test_command_whitelist_matches() -> None:
    allowed, _ = is_command_allowed(
        "git status", allowed=["git", "ls"], denied=[]
    )
    assert allowed is True


def test_command_empty_denied_list_still_works() -> None:
    allowed, _ = is_command_allowed(
        "ls", allowed=["ls"], denied=[]
    )
    assert allowed is True


def test_command_empty_string() -> None:
    allowed, reason = is_command_allowed("", allowed=["ls"], denied=[])
    assert allowed is False


def test_command_deny_pattern_matches_substring() -> None:
    """`dd` 在 denied 里应拒绝 `dd if=/dev/zero of=/tmp/x`."""
    allowed, _ = is_command_allowed(
        "dd if=/dev/zero of=/tmp/x", allowed=[], denied=["dd"]
    )
    assert allowed is False


def test_command_env_var_prefix_stripped() -> None:
    """`FOO=bar ls` 应当识别首 token 为 ls."""
    allowed, _ = is_command_allowed(
        "FOO=bar ls", allowed=["ls"], denied=[]
    )
    assert allowed is True


def test_command_has_metacharacter_helper() -> None:
    # Metacharacters: > < & ` $ ( ) — 分号不是 metacharacter,
    # 它在 _split_command 里作为 separator 处理.
    assert has_metacharacter("ls > /tmp/x") is True
    assert has_metacharacter("ls < /tmp/x") is True
    assert has_metacharacter("ls `id`") is True
    assert has_metacharacter("ls $(id)") is True
    assert has_metacharacter("ls &") is True
    assert has_metacharacter("ls") is False
    assert has_metacharacter("ls; rm") is False  # 分号不是 metacharacter
