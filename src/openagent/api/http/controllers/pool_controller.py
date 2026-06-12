"""PoolController — agent registration and pool stats."""

from __future__ import annotations

from dataclasses import asdict

import structlog
from sanic import Blueprint
from sanic.request import Request
from sanic.response import JSONResponse
from sanic_ext import openapi as sanic_openapi

from openagent.api.http.schemas import ErrorResponse, get_bridge
from openagent.providers.base import AgentConfig

logger = structlog.get_logger(__name__)

doc_summary = sanic_openapi.summary
doc_description = sanic_openapi.description
doc_tag = sanic_openapi.tag
operation = sanic_openapi.operation
response = sanic_openapi.response
body = sanic_openapi.body

pool_bp = Blueprint("pool", url_prefix="/agent")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_register_agent_body(body: dict | None) -> tuple[AgentConfig | None, ErrorResponse | None]:
    """校验 register_agent 请求体并构造 AgentConfig；失败时返回 ErrorResponse。"""
    if not body or "name" not in body or "base_url" not in body:
        return None, ErrorResponse(error="name and base_url are required")
    sdk_type = body.get("sdk_type", "opencode")
    if sdk_type not in ("opencode", "claude_code"):
        return None, ErrorResponse(
            error=f"invalid sdk_type '{sdk_type}', must be 'opencode' or 'claude_code'"
        )
    return (
        AgentConfig(
            name=body["name"],
            base_url=body["base_url"],
            sdk_type=sdk_type,
            default_model=body.get("default_model"),
        ),
        None,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@pool_bp.post("/pool/register")
@doc_summary("注册新 Agent 实例")
@doc_description("向 Agent Pool 注册一个 OpenCode 兼容后端实例。")
@doc_tag("Pool")
@operation("registerAgent")
@response(201, {"success": bool, "name": str, "base_url": str, "status": str})
@response(400, ErrorResponse, description="参数错误")
async def register_agent(request: Request) -> JSONResponse:
    """处理 POST /agent/pool/register：注册一个 Agent 实例。"""
    bridge = get_bridge(request)
    body = request.json
    config, err = _validate_register_agent_body(body)
    if err is not None:
        logger.warning("agent_register_invalid", error=err.error)
        return JSONResponse(err.model_dump(), status=400)
    logger.info(
        "agent_register_request",
        name=config.name,
        sdk_type=config.sdk_type,
        base_url=config.base_url,
    )
    try:
        bridge.register(config)
    except ValueError as e:
        logger.warning("agent_register_failed", name=config.name, error=str(e))
        return JSONResponse(ErrorResponse(error=str(e)).model_dump(), status=400)
    except Exception as e:
        logger.error(
            "register_agent_failed",
            name=config.name,
            sdk_type=config.sdk_type,
            error=str(e),
        )
        return JSONResponse(
            ErrorResponse(error=f"{type(e).__name__}: {e}").model_dump(), status=500
        )
    logger.info("agent_registered", name=config.name, sdk_type=config.sdk_type)
    return JSONResponse(
        {
            "success": True,
            "name": config.name,
            "base_url": config.base_url,
            "sdk_type": config.sdk_type,
            "status": "registered",
        },
        status=201,
    )


@pool_bp.delete("/pool/<name>")
@doc_summary("注销 Agent 实例")
@doc_description("从 Agent Pool 移除一个实例（未实现）。")
@doc_tag("Pool")
@operation("unregisterAgent")
@response(501, ErrorResponse, description="未实现")
async def unregister_agent(request: Request, name: str) -> JSONResponse:
    """处理 DELETE /agent/pool/<name>：注销 Agent 实例（未实现，返回 501）。"""
    logger.warning("agent_unregister_not_implemented", name=name)
    return JSONResponse(
        {"success": False, "name": name, "error": "Unregister not implemented via bridge"},
        status=501,
    )


@pool_bp.get("/pool/stats")
@doc_summary("获取实例池统计信息")
@doc_description("返回当前已注册的 Agent 实例数量和名称列表。")
@doc_tag("Pool")
@operation("poolStats")
@response(200, {"total_agents": int, "agents": dict})
async def pool_stats(request: Request) -> JSONResponse:
    """处理 GET /agent/pool/stats：返回 Agent Pool 当前的注册统计。"""
    bridge = get_bridge(request)
    agents = bridge.list_agents()
    logger.info("pool_stats_request", total_agents=len(agents))
    return JSONResponse(
        {
            "total_agents": len(agents),
            "agents": {name: asdict(cfg) for name, cfg in agents.items()},
        }
    )
