#!/usr/bin/env python3
"""ask_user MCP local tool — persistent JSON-line server.

历史实现 (v1):  ``sys.stdin.read()`` 阻塞到 EOF, 然后 print("ok") 退出.
结果: opencode 把脚本当 "persistent MCP server" 跑, 但脚本 30 秒内
没回响应, 报 "Operation timed out after 30000ms". 整个 server 状态
变 failed, LLM 看不到 ask_user 工具.

本版本 (v2): 走 **JSON-lines 持久循环** 模式, 跟 MCP local 协议对得
上. opencode 启动时 spawn 一次, 之后每条请求走 stdin 一行, 回 stdout
一行; opencode 关 stdin 时脚本退出.

  1. LLM 调 ask_user(card_type=..., body=...) 工具
  2. opencode 走 MCP local 协议, 把 input 序列化成 JSON 一行
     + 换行喂给本脚本的 stdin
  3. 脚本读一行, parse, 立刻回 stdout 一行 JSON
     {"ok": true, "tool": "ask_user", "received": {...}, "ack": "..."}
  4. opencode 把 stdout 那行当 tool result 回给 LLM
  5. 同时 opencode 推 message.part.updated (type=tool) 到 SSE;
     Hub 端 stream_chat 看到 tool_name=ask_user 转成 card 事件发前端

真正的 card 渲染 / 用户交互的回路**不在本脚本里**, 那是 Hub 端的活.
本脚本只负责 (a) 让 opencode 看到 ask_user tool, (b) ack 不阻塞.
"""
from __future__ import annotations

import json
import sys

# 强制 stdout/stderr 用 UTF-8, 避免 Windows GBK 编码报错
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except (AttributeError, OSError):
    pass


def handle(request: dict) -> dict:
    """处理一条 MCP request, 返回 response dict.

    真正的业务 (推 card / 收用户回复) 由 Hub 端通过 SSE 拦截 tool_use
    事件完成. 本脚本只做"echo" 让 LLM 拿到 tool result 不再被阻塞.
    """
    return {
        "ok": True,
        "tool": "ask_user",
        "received": {
            "card_type": request.get("card_type"),
            "title": (request.get("title") or "")[:80],
        },
        "ack": (
            "framework_will_handle_card_emission; "
            "Hub 端的 stream_chat 会拦截 tool_use(ask_user) 把它转成 "
            "card SSE 事件发前端, LLM 不需要做任何事"
        ),
    }


def main() -> int:
    sys.stderr.write("[ask_user] starting persistent MCP loop (json-lines)\n")
    sys.stderr.flush()
    while True:
        try:
            line = sys.stdin.readline()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            # opencode 关了 stdin; 正常退出路径
            break
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as e:
            sys.stderr.write(f"[ask_user] invalid JSON line: {e}\n")
            sys.stderr.flush()
            # 回一个错误响应, 不让 opencode 等死
            sys.stdout.write(json.dumps({
                "ok": False, "tool": "ask_user", "error": f"INVALID_JSON: {e}",
            }) + "\n")
            sys.stdout.flush()
            continue
        if not isinstance(request, dict):
            sys.stdout.write(json.dumps({
                "ok": False, "tool": "ask_user",
                "error": f"EXPECTED_OBJECT_GOT_{type(request).__name__}",
            }) + "\n")
            sys.stdout.flush()
            continue
        try:
            response = handle(request)
        except Exception as e:  # 防御: 单条请求崩了不杀整个 server
            sys.stderr.write(f"[ask_user] handler error: {e}\n")
            sys.stderr.flush()
            response = {"ok": False, "tool": "ask_user", "error": str(e)}
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    sys.stderr.write("[ask_user] stdin closed, exiting\n")
    sys.stderr.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
