"""tests/test_ask_user_script.py — docker/ask_user.py 单元测试 (v2 持久循环).

跟 read_skill.py 同模式: ask_user.py 是 persistent JSON-line MCP server.
opencode spawn 一次, 每条请求走 stdin 一行, 回 stdout 一行.

v1 单次 read+print 模式导致 30s 超时 (opencode mcp list 显示 failed);
v2 改成 json-lines 持久循环, 修复 timeout.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.resolve()
SCRIPT = REPO_ROOT / "docker" / "ask_user.py"


class AskUserServer:
    """启动 ask_user.py 子进程, 模拟 opencode MCP 协议 send/recv."""

    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, str(SCRIPT)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(REPO_ROOT),
            text=True,
            bufsize=1,
            encoding="utf-8",  # 避免 Windows GBK 编码问题 (中文 SKILL 内容)
            errors="replace",
        )

    def send(self, payload: dict) -> dict:
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            stderr = self.proc.stderr.read() if self.proc.stderr else ""
            raise AssertionError(
                f"server closed stdout; stderr: {stderr}"
            )
        return json.loads(line)

    def close(self) -> None:
        if self.proc.stdin and not self.proc.stdin.closed:
            self.proc.stdin.close()
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()


# ----- tests --------------------------------------------------------------


def test_persistent_loop_handles_multiple_calls() -> None:
    """关键不变量: 同一连接, 多次 send 都不让 server 退出."""
    srv = AskUserServer()
    try:
        r1 = srv.send({"card_type": "FLIGHT_RESULT", "title": "first"})
        assert r1["ok"] is True
        assert r1["tool"] == "ask_user"
        assert r1["received"]["card_type"] == "FLIGHT_RESULT"

        r2 = srv.send({"card_type": "CANNOT_ORDER", "title": "second"})
        assert r2["ok"] is True
        assert r2["received"]["card_type"] == "CANNOT_ORDER"

        # server 仍存活
        assert srv.proc.poll() is None
    finally:
        srv.close()


def test_long_title_truncated_to_80() -> None:
    srv = AskUserServer()
    try:
        long_title = "x" * 200
        out = srv.send({"card_type": "CHAT_FALLBACK", "title": long_title})
        assert out["ok"] is True
        # received.title 应当被截到 80 字符
        assert len(out["received"]["title"]) == 80
    finally:
        srv.close()


def test_invalid_json_does_not_crash_server() -> None:
    """非 JSON 输入不应该让 server 退出."""
    srv = AskUserServer()
    try:
        assert srv.proc.stdin
        srv.proc.stdin.write("garbage not json\n")
        srv.proc.stdin.flush()
        line = srv.proc.stdout.readline()
        out = json.loads(line)
        assert out["ok"] is False
        assert "INVALID_JSON" in out.get("error", "")

        # 仍能继续 serve
        r2 = srv.send({"card_type": "FLIGHT_RESULT"})
        assert r2["ok"] is True
        assert srv.proc.poll() is None
    finally:
        srv.close()


def test_non_object_payload_returns_error() -> None:
    """MCP request 必须是 JSON object, list/数字等返 error."""
    srv = AskUserServer()
    try:
        assert srv.proc.stdin
        srv.proc.stdin.write(json.dumps([1, 2, 3]) + "\n")
        srv.proc.stdin.flush()
        line = srv.proc.stdout.readline()
        out = json.loads(line)
        assert out["ok"] is False
        assert "EXPECTED_OBJECT" in out.get("error", "")
    finally:
        srv.close()


def test_server_responds_quickly() -> None:
    """P0-2 follow-up: 30 秒超时回归测试 — server 应在毫秒级响应.

    opencode 配的 default timeout 是 5s, 但 30s 是它给"连接+认证"的
    总预算. 我们的 server 必须在毫秒内 ack 否则不算 healthy.
    """
    import time
    srv = AskUserServer()
    try:
        t0 = time.monotonic()
        srv.send({"card_type": "FLIGHT_RESULT"})
        elapsed = time.monotonic() - t0
        assert elapsed < 1.0, f"server too slow: {elapsed:.3f}s"
    finally:
        srv.close()
