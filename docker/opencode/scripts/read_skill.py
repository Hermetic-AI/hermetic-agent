#!/usr/bin/env python3
"""read_skill MCP local tool — persistent JSON-line server.

历史实现 (v1): 单次 read+print 模式, opencode 当 persistent server 跑
的话 30 秒超时被杀. 改成跟 ask_user.py 同模式的 json-lines 循环.

调用流程 (跟 ask_user.py 同模式):
  1. LLM 调 read_skill(name="flight-query-v3.iata_icao_codes", fragment=None)
  2. opencode 通过 MCP local 协议把 input 序列化成 JSON 一行 + 换行
     喂给本脚本的 stdin
  3. 脚本读一行, 解析, 立刻回 stdout 一行 JSON
     {"ok": true, "name": ..., "content": ...}
  4. opencode 把 stdout 那行当 tool result 回给 LLM
  5. LLM 拿到 SKILL.md 全文 / fragments/<id>.md 子片段

skill 路径解析规则 (跟 v1 一样):
  - "flight-query-v3"  → <root>/flight-query-v3/SKILL.md
  - "flight-query-v3.iata_icao_codes" → <root>/flight-query-v3/flight-query-v3.iata_icao_codes/SKILL.md
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 强制 stdout/stderr 用 UTF-8, 避免 Windows GBK 编码报错 (中文 SKILL 内容)
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except (AttributeError, OSError):
    pass

SKILL_ROOT = Path(os.environ.get("READ_SKILL_ROOT", "/work/shared/skills"))


def resolve_skill_path(name: str) -> Path | None:
    """根据 skill name 解析到 SKILL.md 的绝对路径."""
    if not SKILL_ROOT.is_dir():
        return None
    direct = SKILL_ROOT / name / "SKILL.md"
    if direct.is_file():
        return direct
    if "." in name:
        parent, sub = name.split(".", 1)
        nested = SKILL_ROOT / parent / f"{parent}.{sub}" / "SKILL.md"
        if nested.is_file():
            return nested
    for candidate in SKILL_ROOT.rglob(f"{name}/SKILL.md"):
        return candidate
    return None


def handle(request: dict) -> dict:
    """处理一条 read_skill MCP request, 返回 response dict."""
    name = request.get("name", "").strip() if isinstance(request.get("name"), str) else ""
    fragment = request.get("fragment")
    if not name:
        return {
            "ok": False, "error_code": "MISSING_NAME",
            "hint": 'pass {"name": "<skill>"} e.g. {"name": "flight-query-v3"}',
        }

    skill_path = resolve_skill_path(name)
    if skill_path is None:
        return {
            "ok": False, "error_code": "SKILL_NOT_FOUND",
            "name": name,
            "hint": f"looked under {SKILL_ROOT}; check work/shared/skills/ tree",
        }

    if fragment:
        frag_path = skill_path.parent / "fragments" / f"{fragment}.md"
        if not frag_path.is_file():
            return {
                "ok": False, "error_code": "FRAGMENT_NOT_FOUND",
                "name": name, "fragment": fragment,
                "expected_path": str(frag_path),
            }
        content = frag_path.read_text(encoding="utf-8")
        return {
            "ok": True, "name": name, "fragment": fragment, "content": content,
        }

    content = skill_path.read_text(encoding="utf-8")
    return {"ok": True, "name": name, "content": content}


def main() -> int:
    sys.stderr.write("[read_skill] starting persistent MCP loop (json-lines)\n")
    sys.stderr.flush()
    while True:
        try:
            line = sys.stdin.readline()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as e:
            sys.stderr.write(f"[read_skill] invalid JSON line: {e}\n")
            sys.stderr.flush()
            sys.stdout.write(json.dumps({
                "ok": False, "error_code": "INVALID_JSON", "error": str(e),
            }) + "\n")
            sys.stdout.flush()
            continue
        if not isinstance(request, dict):
            sys.stdout.write(json.dumps({
                "ok": False, "error_code": "EXPECTED_OBJECT",
                "got": type(request).__name__,
            }) + "\n")
            sys.stdout.flush()
            continue
        try:
            response = handle(request)
        except Exception as e:
            sys.stderr.write(f"[read_skill] handler error: {e}\n")
            sys.stderr.flush()
            response = {"ok": False, "error_code": "HANDLER_ERROR", "error": str(e)}
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    sys.stderr.write("[read_skill] stdin closed, exiting\n")
    sys.stderr.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
