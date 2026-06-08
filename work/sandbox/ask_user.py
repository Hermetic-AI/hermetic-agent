#!/usr/bin/env python3
"""ask_user MCP local tool — opencode 的 stdio transport 是 NDJSON (无 Content-Length).

opencode 1.16.0 的 local MCP transport 走 **newline-delimited JSON** (NDJSON):
  - 每条消息: 1 行 JSON, 行尾 \\n
  - 不用 Content-Length header
  - 客户端先发, 服务端回

之前 v3 用 LSP 风格 Content-Length → opencode 看不到 initialize → 30s timeout
后 EOF. 改成 NDJSON 后 opencode 能正常 handshake.
"""
from __future__ import annotations

import json
import sys
from typing import Any


def _read_message() -> dict | None:
    """从 stdin 读一行 JSON. EOF 返 None."""
    line = sys.stdin.readline()
    if not line:
        return None
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"[ask_user] invalid JSON: {e}\n")
        sys.stderr.flush()
        return None


def _write_message(msg: dict) -> None:
    """写一行 JSON + \\n 到 stdout."""
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _result(req_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id: Any, code: int, message: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": code, "message": message},
    }


_SERVER_INFO = {"name": "ask_user", "version": "1.0.0"}
_SERVER_CAPABILITIES = {"tools": {}}

_ASK_USER_TOOL = {
    "name": "ask_user",
    "description": (
        "Send a structured AUIP card to the user. The Hub intercepts this tool "
        "call and converts it into an SSE 'card' event for the frontend to "
        "render (FlightResultCard / OdInputCard / etc.). LLM should not put "
        "structured data in chat text — use this tool instead."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "card_type": {
                "type": "string",
                "enum": [
                    "FLIGHT_RESULT",
                    "FLIGHT_LIST",
                    "OD_INPUT",
                    "CABIN_LIST",
                    "PASSENGER_FORM",
                    "OAT_BINDING",
                    "PRICE_VERIFY",
                    "POLICY_DECISION",
                    "ORDER_CONFIRM",
                    "ORDER_SUCCESS",
                    "CANNOT_ORDER",
                    "CHAT_FALLBACK",
                ],
                "description": "Card type (see CardType enum).",
            },
            "title": {"type": "string"},
            "body": {"type": "object"},
            "fields": {"type": "array"},
            "options": {"type": "array"},
            "actions": {"type": "array"},
            "metadata": {"type": "object"},
        },
        "required": ["card_type", "title", "body"],
    },
}


def _handle(req: dict) -> dict:
    req_id = req.get("id")
    method = req.get("method", "")
    params = req.get("params", {}) or {}

    if method == "initialize":
        return _result(req_id, {
            "protocolVersion": params.get("protocolVersion", "2024-11-05"),
            "serverInfo": _SERVER_INFO,
            "capabilities": _SERVER_CAPABILITIES,
        })
    if method == "notifications/initialized":
        return _result(req_id, {})
    if method == "ping":
        return _result(req_id, {})
    if method == "tools/list":
        return _result(req_id, {"tools": [_ASK_USER_TOOL]})
    if method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments", {}) or {}
        if name != "ask_user":
            return _error(req_id, -32602, f"unknown tool: {name!r}")
        text = json.dumps({
            "ok": True,
            "echo": {
                "card_type": args.get("card_type"),
                "title": (args.get("title") or "")[:80],
                "received_keys": sorted(args.keys()),
            },
            "ack": "framework_handles_card_emission",
        }, ensure_ascii=False)
        return _result(req_id, {
            "content": [{"type": "text", "text": text}],
            "isError": False,
        })
    return _error(req_id, -32601, f"method not implemented: {method!r}")


def main() -> int:
    sys.stderr.write("[ask_user] MCP NDJSON server starting\n")
    sys.stderr.flush()
    while True:
        req = _read_message()
        if req is None:
            break
        if "id" not in req or req.get("id") is None:
            continue
        try:
            resp = _handle(req)
        except Exception as e:
            sys.stderr.write(f"[ask_user] handler crashed: {e}\n")
            sys.stderr.flush()
            resp = _error(req.get("id"), -32603, f"internal: {e}")
        try:
            _write_message(resp)
        except (BrokenPipeError, OSError) as e:
            sys.stderr.write(f"[ask_user] write failed: {e}\n")
            sys.stderr.flush()
            break
    sys.stderr.write("[ask_user] stdin EOF, exiting\n")
    sys.stderr.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
