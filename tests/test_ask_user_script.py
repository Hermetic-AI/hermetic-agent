"""docker/ask_user.py MCP stdio server tests."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.resolve()
SCRIPT = REPO_ROOT / "docker" / "ask_user.py"


class AskUserServer:
    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, str(SCRIPT)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(REPO_ROOT),
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
        )

    def send(self, payload: dict) -> dict:
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            stderr = self.proc.stderr.read() if self.proc.stderr else ""
            raise AssertionError(f"server closed stdout; stderr: {stderr}")
        return json.loads(line)

    def close(self) -> None:
        if self.proc.stdin and not self.proc.stdin.closed:
            self.proc.stdin.close()
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()


def test_initialize_and_list_tools() -> None:
    srv = AskUserServer()
    try:
        init = srv.send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert init["result"]["capabilities"]["tools"] == {}

        listed = srv.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tool = listed["result"]["tools"][0]
        assert tool["name"] == "ask_user"
        assert tool["inputSchema"]["required"] == ["card_type"]
    finally:
        srv.close()


def test_tools_call_acknowledges_ask_user() -> None:
    srv = AskUserServer()
    try:
        out = srv.send({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "ask_user",
                "arguments": {"card_type": "OD_INPUT", "title": "请补充信息"},
            },
        })

        content = out["result"]["content"][0]
        assert content["type"] == "text"
        ack = json.loads(content["text"])
        assert ack["ok"] is True
        assert ack["tool"] == "ask_user"
        assert ack["received"]["card_type"] == "OD_INPUT"
    finally:
        srv.close()


def test_unknown_tool_returns_jsonrpc_error() -> None:
    srv = AskUserServer()
    try:
        out = srv.send({
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "missing", "arguments": {}},
        })
        assert out["error"]["code"] == -32602
    finally:
        srv.close()
