#!/usr/bin/env python3
"""Minimal MCP stdio server exposing the synthetic ``ask_user`` tool.

opencode loads local MCP servers through the MCP JSON-RPC stdio protocol. This
server only needs to make the tool available and acknowledge calls; Hub converts
the resulting opencode tool event into an AUIP card.
"""
from __future__ import annotations

import json
import sys
from typing import Any

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except (AttributeError, OSError):
    pass


ASK_USER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["card_type"],
    "additionalProperties": True,
    "properties": {
        "card_type": {
            "type": "string",
            "description": (
                "AUIP card type. 基座预定义见 hermetic-agent, "
                "业务 SKILL 可扩展新 card_type, 由前端 CardShell 渲染."
            ),
        },
        "title": {"type": "string"},
        "message": {"type": "string"},
        "body": {"type": "object"},
        "fields": {"type": "array"},
        "options": {"type": "array"},
        "actions": {"type": "array"},
        "decision_buttons": {"type": "array"},
        "metadata": {"type": "object"},
    },
}


def _response(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _tools_list() -> dict[str, Any]:
    return {
        "tools": [
            {
                "name": "ask_user",
                "description": (
                    "Emit a structured AUIP card to the user. The Hub intercepts "
                    "the tool event and renders the card in the frontend."
                ),
                "inputSchema": ASK_USER_SCHEMA,
            }
        ]
    }


def _call_tool(params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    if name != "ask_user":
        raise ValueError(f"unknown tool: {name}")
    args = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "ok": True,
                        "tool": "ask_user",
                        "received": {
                            "card_type": args.get("card_type"),
                            "title": str(args.get("title") or "")[:80],
                        },
                        "ack": "framework_will_handle_card_emission",
                    },
                    ensure_ascii=False,
                ),
            }
        ]
    }


def handle(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") if isinstance(message.get("params"), dict) else {}

    if method == "initialize":
        return _response(
            request_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "hermetic_agent-ask-user", "version": "1.0.0"},
            },
        )
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return _response(request_id, _tools_list())
    if method == "tools/call":
        try:
            return _response(request_id, _call_tool(params))
        except ValueError as exc:
            return _error(request_id, -32602, str(exc))
    return _error(request_id, -32601, f"method not found: {method}")


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            sys.stdout.write(json.dumps(_error(None, -32700, f"parse error: {exc}")) + "\n")
            sys.stdout.flush()
            continue
        if not isinstance(message, dict):
            sys.stdout.write(json.dumps(_error(None, -32600, "request must be an object")) + "\n")
            sys.stdout.flush()
            continue
        response = handle(message)
        if response is None:
            continue
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
