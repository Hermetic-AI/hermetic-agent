"""AgentsController — /agent/agents/* CRUD 端点.

镜像 PromptsController, 但 DTO 多 4 个 *_codes + system_prompt + model +
tool_level + network 字段 (Agent 是复合体, 引用 4 类资产).
"""
from __future__ import annotations

import structlog
from sanic import Blueprint
from sanic.request import Request
from sanic.response import JSONResponse
from sanic_ext import openapi as sanic_openapi

from hermetic_agent.store.dto._common import ActorContext
from hermetic_agent.store.dto.agent import (
    CreateAgentRequest,
    UpdateAgentRequest,
)
from hermetic_agent.store.exceptions import DuplicateError, NotFoundError, PolicyError

logger = structlog.get_logger(__name__)
doc_summary = sanic_openapi.summary
doc_tag = sanic_openapi.tag
agent_bp = Blueprint("agents", url_prefix="/agent/agents")


def _container(request: Request):
    return request.app.ctx.service_container


def _err(code: str, message: str, status: int = 400) -> JSONResponse:
    return JSONResponse(
        {"success": False, "code": code, "error": message}, status=status,
    )


def _actor(request: Request) -> ActorContext:
    return getattr(request.ctx, "actor", ActorContext(user_id="anonymous"))


@agent_bp.get("/")
@doc_summary("List agents (own + public)")
@doc_tag("Agents")
async def list_agents(request: Request) -> JSONResponse:
    c = _container(request)
    items = await c.agent.list(
        actor=_actor(request),
        limit=int(request.args.get("limit", "50")),
        offset=int(request.args.get("offset", "0")),
        code=request.args.get("code"),
        status=request.args.get("status"),
    )
    return JSONResponse({
        "total": len(items),
        "items": [c.agent.to_response(a).model_dump(mode="json") for a in items],
    })


@agent_bp.get("/community")
@doc_summary("List public agents only")
@doc_tag("Agents")
async def list_public_agents(request: Request) -> JSONResponse:
    c = _container(request)
    items = await c.agent.list_public(
        limit=int(request.args.get("limit", "50")),
        offset=int(request.args.get("offset", "0")),
        code=request.args.get("code"),
    )
    return JSONResponse({
        "total": len(items),
        "items": [c.agent.to_response(a).model_dump(mode="json") for a in items],
    })


@agent_bp.get("/<code>")
@doc_summary("Get an agent by code")
@doc_tag("Agents")
async def get_agent(request: Request, code: str) -> JSONResponse:
    c = _container(request)
    try:
        a = await c.agent.get_by_code(code)
    except NotFoundError:
        return _err("AGENT_NOT_FOUND", f"agent {code!r} not found", status=404)
    return JSONResponse(c.agent.to_response(a).model_dump(mode="json"))


@agent_bp.post("/")
@doc_summary("Create an agent")
@doc_tag("Agents")
async def create_agent(request: Request) -> JSONResponse:
    c = _container(request)
    try:
        req = CreateAgentRequest(**(request.json or {}))
    except Exception as e:
        return _err("VALIDATION_FAILED", f"Invalid body: {e}")
    try:
        a = await c.agent.create(req, actor=_actor(request))
    except DuplicateError as e:
        return _err("DUPLICATE_AGENT", str(e), status=409)
    return JSONResponse(
        c.agent.to_response(a).model_dump(mode="json"), status=201,
    )


@agent_bp.put("/<code>")
@doc_summary("Update an agent")
@doc_tag("Agents")
async def update_agent(request: Request, code: str) -> JSONResponse:
    c = _container(request)
    try:
        req = UpdateAgentRequest(**(request.json or {}))
    except Exception as e:
        return _err("VALIDATION_FAILED", f"Invalid body: {e}")
    try:
        a = await c.agent.get_by_code(code)
    except NotFoundError:
        return _err("AGENT_NOT_FOUND", f"agent {code!r} not found", status=404)
    try:
        u = await c.agent.update(str(a.id), req, actor=_actor(request))
    except PolicyError as e:
        return _err("FORBIDDEN", e.detail, status=403)
    return JSONResponse(c.agent.to_response(u).model_dump(mode="json"))


@agent_bp.delete("/<code>")
@doc_summary("Soft-delete an agent")
@doc_tag("Agents")
async def delete_agent(request: Request, code: str) -> JSONResponse:
    c = _container(request)
    try:
        a = await c.agent.get_by_code(code)
    except NotFoundError:
        return _err("AGENT_NOT_FOUND", f"agent {code!r} not found", status=404)
    await c.agent.soft_delete(str(a.id), actor=_actor(request))
    return JSONResponse({"success": True, "code": code})


@agent_bp.post("/<code>/publish")
@doc_summary("Toggle visibility (owner-only)")
@doc_tag("Agents")
async def publish_agent(request: Request, code: str) -> JSONResponse:
    c = _container(request)
    body = request.json or {}
    visibility = body.get("visibility")
    if visibility not in ("private", "public"):
        return _err("VALIDATION_FAILED", "visibility must be 'private' or 'public'")
    try:
        a = await c.agent.get_by_code(code)
    except NotFoundError:
        return _err("AGENT_NOT_FOUND", f"agent {code!r} not found", status=404)
    out = await c.agent.set_visibility(
        str(a.id), visibility, actor=_actor(request),
    )
    if out is None:
        return _err("FORBIDDEN", "only owner can change visibility", status=403)
    return JSONResponse(c.agent.to_response(out).model_dump(mode="json"))


__all__ = ["agent_bp"]
