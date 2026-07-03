"""path_check 模块单测."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from hermetic_agent.policy.path_check import (
    BLOCKED_PATTERNS,
    check_path,
    is_blocked,
    is_denied,
    is_within,
    normalize,
)


def test_path_blocks_etc_passwd(tmp_path: Path) -> None:
    # /etc/passwd 在 Linux 上确实存在; 把它放到一个 workspace 之外
    if sys.platform == "win32":
        # Windows 上 /etc/passwd 不一定存在, 仍要走 BLOCKED_PATTERNS (它不在)
        # 改用 BLOCKED_PATTERNS 必拦截的 .env
        target = tmp_path / "passwd"
        target.write_text("x")
        # 它不在 BLOCKED_PATTERNS, 但不在 workspace 里, 应当被 not_within 拒绝
        allowed, _ = check_path([str(tmp_path)], [], str(target))
        assert allowed is True  # 在 tmp_path 内 OK
    else:
        allowed, reason = check_path([str(tmp_path)], [], "/etc/passwd")
        assert allowed is False


def test_path_blocks_env_file() -> None:
    assert is_blocked("/work/proj/.env") is True
    assert is_blocked("/work/proj/.env.production") is True
    assert is_blocked("/home/u/.ssh/id_rsa") is True
    # secrets/credentials 是目录: secrets 下的任意文件都被拦
    assert is_blocked("/work/proj/secrets/db.yaml") is True
    # credentials 目录同理
    assert is_blocked("/work/proj/credentials/db.json") is True
    # .pem / .key / .p12 文件
    assert is_blocked("/work/proj/cert.pem") is True
    assert is_blocked("/work/proj/srv.key") is True


def test_path_does_not_block_normal_files() -> None:
    assert is_blocked("/work/proj/src/main.py") is False
    assert is_blocked("/work/proj/README.md") is False


def test_path_resolves_symlinks(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    real_file = real / "a.txt"
    real_file.write_text("x")
    link = tmp_path / "link"
    try:
        link.symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("symlink not supported on this platform")

    target = link / "a.txt"
    resolved = normalize(str(target))
    # 解析后应指向 real/a.txt
    assert os.path.realpath(resolved) == os.path.realpath(str(real_file))


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
def test_path_windows_case_insensitive(tmp_path: Path) -> None:
    """Windows 上大小写不敏感: WORK/PROJ 应该匹配 work/proj."""
    d = tmp_path / "Work" / "Proj"
    d.mkdir(parents=True)
    target = d / "file.txt"
    target.write_text("x")
    ws = [str(tmp_path / "work" / "proj")]
    # 用另一种大小写查询
    assert is_within(ws, str(target)) is True


def test_is_within_basic(tmp_path: Path) -> None:
    ws = str(tmp_path / "ws")
    Path(ws).mkdir()
    sub = Path(ws) / "src" / "main.py"
    sub.parent.mkdir(parents=True)
    sub.write_text("x")
    assert is_within([ws], str(sub)) is True


def test_is_within_rejects_sibling(tmp_path: Path) -> None:
    a = tmp_path / "dir_a"
    b = tmp_path / "dir_b"
    a.mkdir()
    b.mkdir()
    target = b / "file.txt"
    target.write_text("x")
    assert is_within([str(a)], str(target)) is False


def test_is_within_no_workspace_returns_false() -> None:
    assert is_within([], "/work/x") is False


def test_is_denied() -> None:
    assert is_denied("/etc/passwd", ["/etc"]) is True
    assert is_denied("/work/x", ["/etc"]) is False


def test_blocked_patterns_have_minimum_set() -> None:
    """BLOCKED_PATTERNS 必须覆盖 credentials 类文件."""
    p = " ".join(BLOCKED_PATTERNS)
    assert ".env" in p
    assert "id_rsa" in p
    assert ".pem" in p


def test_check_path_priority_blocked_first() -> None:
    """即使 path 在 workspace 里, 命中 BLOCKED_PATTERNS 也应拒绝."""
    allowed, reason = check_path(["/work/x/.env"], [], "/work/x/.env")
    assert allowed is False
    assert "BLOCKED" in reason
