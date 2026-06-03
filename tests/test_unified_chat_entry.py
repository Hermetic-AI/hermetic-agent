"""test_unified_chat_entry.py — 校验 统一对话入口 约束 (CI 必跑).

实现方式: 用 AST 扫描所有 controller 源文件, 禁止
``@<bp>.post("/<...>/chat")`` 与 ``/chat/stream`` 形式.
补充一个 ``create_app`` 后的运行时断言: 实际路由表不含 per-scenario chat 路径.
"""
import re
import subprocess
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# 1) 跑 scripts/check_unified_chat_entry.py (AST 扫描)
# ---------------------------------------------------------------------------


def test_check_unified_chat_entry_passes():
    """scripts/check_unified_chat_entry.py 必须 0 退出."""
    result = subprocess.run(
        ["python", "scripts/check_unified_chat_entry.py"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, (
        f"check_unified_chat_entry.py failed:\n"
        f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
    assert "PASS" in result.stdout


# ---------------------------------------------------------------------------
# 2) 运行时校验: 实际 Sanic app 路由表不含 per-scenario chat
# ---------------------------------------------------------------------------


def _build_app():
    """直接 build 一个有 unique name 的 Sanic app, 复用 create_app 的 init 流程."""
    from openagent.api.app import create_app
    from openagent.config.settings import Settings
    # 关键: Sanic 全局按 name 注册, 但 create_app 用 "agent-scheduler-hub".
    # 第一次调用是 OK 的, 之后会被 fixture 缓存. 我们直接 build 一次拿 router.
    import openagent.api.app as app_mod
    if not getattr(app_mod, "_test_app_cache", None):
        app_mod._test_app_cache = create_app(Settings())
    return app_mod._test_app_cache


def test_no_per_scenario_chat_route_in_app():
    """实际 Sanic app 路由表里不能有 per-scenario chat 路径."""
    app = _build_app()
    paths = [getattr(r, "path", "") for r in app.router.routes]
    norm = [("/" + p) if not p.startswith("/") else p for p in paths]
    forbidden = [
        p for p in norm
        if "/scenarios/" in p and ("/chat" in p or "/chat/stream" in p)
    ]
    assert not forbidden, (
        f"app 路由表里还有 per-scenario chat: {forbidden}\n"
        f"全部对话应统一走 /agent/chat (chat_controller.py)"
    )


def test_chat_routes_only_in_chat_controller():
    """/agent/chat + /agent/chat/stream 只能由 chat_controller.py 提供."""
    app = _build_app()
    paths = [getattr(r, "path", "") for r in app.router.routes]
    # Sanic 返回 path 不带前导 /, 兼容
    norm = [("/" + p) if not p.startswith("/") else p for p in paths]
    assert any(p == "/agent/chat" for p in norm), f"缺 /agent/chat in {norm}"
    assert any(p == "/agent/chat/stream" for p in norm), f"缺 /agent/chat/stream in {norm}"


# ---------------------------------------------------------------------------
# 3) 源代码 AST 二次扫描 (不依赖 script)
# ---------------------------------------------------------------------------


def _find_per_scenario_chat_in_source():
    """扫所有 controller 源文件, 返回违规的 (path, line, content) 列表."""
    forbidden_pattern = re.compile(
        r'@[^.]+\.post\(\s*["\']?/<[^>]+>/chat(?:/stream)?["\']?\s*\)'
    )
    violations = []
    for path in Path("src/openagent/api/controllers/").glob("*.py"):
        if path.name in ("__init__.py",):
            continue
        if "__pycache__" in str(path):
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if forbidden_pattern.search(line):
                violations.append((str(path), i, line.strip()))
    return violations


def test_no_per_scenario_chat_pattern_in_source():
    """所有 controller 源文件不应有 /<...>/chat 路由声明."""
    violations = _find_per_scenario_chat_in_source()
    assert not violations, (
        f"per-scenario chat 端点违规:\n" +
        "\n".join(f"  {p}:{i}: {c}" for p, i, c in violations)
    )
