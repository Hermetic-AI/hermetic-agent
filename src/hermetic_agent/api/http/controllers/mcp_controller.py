"""McpController — /agent/mcp-configs/* CRUD 端点.

延迟加载 ServiceContainer: 不 import 到模块级.
"""

from __future__ import annotations

import structlog
from sanic import Blueprint
from sanic.request import Request
from sanic.response import JSONResponse
from sanic_ext import openapi as sanic_openapi

logger = structlog.get_logger(__name__)

doc_summary = sanic_openapi.summary
doc_tag = sanic_openapi.tag

mcp_config_bp = Blueprint("mcp_configs", url_prefix="/agent/mcp-configs")


def _get_container(request: Request):
    return request.app.ctx.service_container


def _err(code: str, message: str, status: int = 400) -> JSONResponse:
    return JSONResponse(
        {"success": False, "code": code, "error": message},
        status=status,
    )


@mcp_config_bp.get("/")
@doc_summary("列出所有 MCP 配置")
@doc_tag("MCP Configs")
async def list_mcp_configs(request: Request) -> JSONResponse:
    from hermetic_agent.store.services.container import ServiceContainer

    container: ServiceContainer = _get_container(request)
    configs = await container.mcp_config_service.list()
    return JSONResponse({
        "total": len(configs),
        "items": [
            container.mcp_config_service.to_response(c).model_dump(mode="json")
            for c in configs
        ],
    })


@mcp_config_bp.get("/<code>")
@doc_summary("按 code 查询 MCP 配置")
@doc_tag("MCP Configs")
async def get_mcp_config(request: Request, code: str) -> JSONResponse:
    from hermetic_agent.store.exceptions import NotFoundError
    from hermetic_agent.store.services.container import ServiceContainer

    container: ServiceContainer = _get_container(request)
    try:
        c = await container.mcp_config_service.get_by_code(code)
    except NotFoundError:
        return _err("MCP_NOT_FOUND", f"MCP config {code!r} not found", status=404)
    return JSONResponse(
        container.mcp_config_service.to_response(c).model_dump(mode="json")
    )


@mcp_config_bp.post("/")
@doc_summary("创建 MCP 配置")
@doc_tag("MCP Configs")
async def create_mcp_config(request: Request) -> JSONResponse:
    from hermetic_agent.store.dto.mcp_config import CreateMcpConfigRequest
    from hermetic_agent.store.exceptions import DuplicateError
    from hermetic_agent.store.services.container import ServiceContainer

    container: ServiceContainer = _get_container(request)
    body = request.json or {}
    try:
        req = CreateMcpConfigRequest(**body)
    except Exception as e:
        return _err("VALIDATION_FAILED", f"Invalid request body: {e}")
    try:
        c = await container.mcp_config_service.create(req)
    except DuplicateError as e:
        return _err("DUPLICATE_MCP", str(e), status=409)
    return JSONResponse(
        container.mcp_config_service.to_response(c).model_dump(mode="json"),
        status=201,
    )


@mcp_config_bp.put("/<code>")
@doc_summary("更新 MCP 配置")
@doc_tag("MCP Configs")
async def update_mcp_config(request: Request, code: str) -> JSONResponse:
    from hermetic_agent.store.dto.mcp_config import UpdateMcpConfigRequest
    from hermetic_agent.store.exceptions import NotFoundError
    from hermetic_agent.store.services.container import ServiceContainer

    container: ServiceContainer = _get_container(request)
    body = request.json or {}
    try:
        req = UpdateMcpConfigRequest(**body)
    except Exception as e:
        return _err("VALIDATION_FAILED", f"Invalid request body: {e}")
    try:
        c = await container.mcp_config_service.get_by_code(code)
    except NotFoundError:
        return _err("MCP_NOT_FOUND", f"MCP config {code!r} not found", status=404)
    try:
        updated = await container.mcp_config_service.update(c.id, req)
    except NotFoundError:
        return _err("MCP_NOT_FOUND", f"MCP config {code!r} not found", status=404)
    return JSONResponse(
        container.mcp_config_service.to_response(updated).model_dump(mode="json")
    )


@mcp_config_bp.delete("/<code>")
@doc_summary("软删除 MCP 配置")
@doc_tag("MCP Configs")
async def delete_mcp_config(request: Request, code: str) -> JSONResponse:
    from hermetic_agent.store.exceptions import NotFoundError
    from hermetic_agent.store.services.container import ServiceContainer

    container: ServiceContainer = _get_container(request)
    try:
        c = await container.mcp_config_service.get_by_code(code)
    except NotFoundError:
        return _err("MCP_NOT_FOUND", f"MCP config {code!r} not found", status=404)
    await container.mcp_config_service.soft_delete(c.id)
    return JSONResponse({"success": True, "code": code})


__all__ = ["mcp_config_bp"]
