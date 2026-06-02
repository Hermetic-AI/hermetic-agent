"""Readiness probe — extracted from app.py to keep that file under the 300-line cap."""

from __future__ import annotations

from typing import Any, Optional

import structlog
from sanic.request import Request
from sanic.response import JSONResponse

logger = structlog.get_logger(__name__)


def _storage_ok(s: Any) -> bool:
    """判断 storage 后端是否处于已连接状态。

    检查常见的 `_initialized` / `initialized` / `connected` 布尔属性；都没有则
    视作 True（适用于始终可用的 ``MemorySessionRepository``）。
    """
    for attr in ("_initialized", "initialized", "connected"):
        val = getattr(s, attr, None)
        if isinstance(val, bool):
            return val
    return True


def _check_component(name: str, ok: bool, detail: str) -> tuple[str, bool, str]:
    """对单个子组件输出 ready_check 日志并返回三元组。"""
    if ok:
        logger.info("ready_check", component=name, ok=True, detail=detail)
    else:
        logger.warning("ready_check", component=name, ok=False, detail=detail)
    return (name, ok, detail)


def collect_readiness(request: Request) -> dict:
    """聚合 storage / bridge / skill_registry / mcp_registry 四个组件的就绪状态。

    Returns:
        包含 `status`、`checks`、`missing` 字段的字典；如果就绪还会附上
        `agents`、`skills_count`、`tools_count`；未就绪会附 `reason` 字段。
        同时每个子组件会写一条 `ready_check` 日志。
    """
    storage = request.app.ctx.storage
    bridge = request.app.ctx.bridge
    skill_registry = request.app.ctx.skill_registry
    mcp_registry = request.app.ctx.mcp_registry

    checks: list[tuple[str, bool, str]] = []

    # 1. storage
    if storage is None:
        checks.append(_check_component("storage", False, "storage backend not initialized"))
    else:
        backend_name = type(storage).__name__
        ok = _storage_ok(storage)
        detail = f"{backend_name} connected" if ok else f"{backend_name} not connected"
        checks.append(_check_component("storage", ok, detail))

    # 2. bridge
    if bridge is None:
        checks.append(_check_component("bridge", False, "agent bridge not initialized"))
    else:
        agents = bridge.list_agents()
        if agents:
            checks.append(_check_component(
                "bridge", True,
                f"{len(agents)} agent(s) registered: {sorted(agents.keys())}",
            ))
        else:
            checks.append(_check_component(
                "bridge", False,
                "no agents registered (set AGENT_SCHEDULER_AUTO_REGISTER_DEFAULTS=true or POST /agent/pool/register)",
            ))

    # 3. skill_registry
    if skill_registry is None:
        checks.append(_check_component("skill_registry", False, "skill registry not initialized"))
    else:
        n_skills = len(skill_registry.list_all())
        if n_skills:
            checks.append(_check_component("skill_registry", True, f"{n_skills} skill(s) loaded"))
        else:
            checks.append(_check_component(
                "skill_registry", False,
                "0 skills loaded (check AGENT_SCHEDULER_SKILL_PATHS)",
            ))

    # 4. mcp_registry
    if mcp_registry is None:
        checks.append(_check_component("mcp_registry", False, "MCP registry not initialized"))
    else:
        n_tools = len(mcp_registry.list_all())
        if n_tools:
            checks.append(_check_component("mcp_registry", True, f"{n_tools} tool(s) registered"))
        else:
            checks.append(_check_component(
                "mcp_registry", False,
                "0 tools registered (check AGENT_SCHEDULER_MCP_TOOLS_CONFIG)",
            ))

    missing = [n for n, ok, _ in checks if not ok]
    ready = not missing
    checks_dict = {n: {"ok": ok, "detail": d} for n, ok, d in checks}

    out: dict[str, Any] = {
        "status": "ready" if ready else "not_ready",
        "checks": checks_dict,
        "missing": missing,
    }
    if ready:
        logger.info("ready_summary", ok=True, components=[n for n, _, _ in checks])
        out["agents"] = list(bridge.list_agents().keys()) if bridge else []
        out["skills_count"] = len(skill_registry.list_all()) if skill_registry else 0
        out["tools_count"] = len(mcp_registry.list_all()) if mcp_registry else 0
    else:
        missing_details = [f"{n} ({d})" for n, ok, d in checks if not ok]
        out["reason"] = "missing components: " + "; ".join(missing_details)
        logger.warning("ready_summary", ok=False, missing=missing, reason=out["reason"])
    return out


def build_ready_response(request: Request) -> JSONResponse:
    """为 `/ready` 端点构造 JSONResponse（200 或 503）。

    Args:
        request: Sanic 请求对象。

    Returns:
        status 字段为 "ready" 时返回 200，否则返回 503。
    """
    payload = collect_readiness(request)
    status = 200 if payload["status"] == "ready" else 503
    return JSONResponse(payload, status=status)
