"""PromptsController — /agent/prompts/* CRUD 端点.

延迟加载 DTO / Exception: 避免在 import 时触发 ServiceContainer,
保证 Sanic 路由注册阶段不会触发 DB 连接.
"""
from __future__ import annotations

import structlog
from sanic import Blueprint
from sanic.request import Request
from sanic.response import JSONResponse
from sanic_ext import openapi as sanic_openapi

from hermetic_agent.store.dto._common import ActorContext
from hermetic_agent.store.dto.prompt import (
    CreatePromptRequest,
    UpdatePromptRequest,
)
from hermetic_agent.store.exceptions import DuplicateError, NotFoundError, PolicyError

logger = structlog.get_logger(__name__)
doc_summary = sanic_openapi.summary
doc_tag = sanic_openapi.tag
prompt_bp = Blueprint("prompts", url_prefix="/agent/prompts")


def _container(request: Request):
    return request.app.ctx.service_container


def _err(code: str, message: str, status: int = 400) -> JSONResponse:
    return JSONResponse(
        {"success": False, "code": code, "error": message}, status=status,
    )


def _actor(request: Request) -> ActorContext:
    return getattr(request.ctx, "actor", ActorContext(user_id="anonymous"))


@prompt_bp.get("/")
@doc_summary("List prompts (own + public)")
@doc_tag("Prompts")
async def list_prompts(request: Request) -> JSONResponse:
    c = _container(request)
    items = await c.prompt.list(
        actor=_actor(request),
        limit=int(request.args.get("limit", "50")),
        offset=int(request.args.get("offset", "0")),
        code=request.args.get("code"),
        status=request.args.get("status"),
    )
    return JSONResponse({
        "total": len(items),
        "items": [c.prompt.to_response(p).model_dump(mode="json") for p in items],
    })


@prompt_bp.get("/community")
@doc_summary("List public prompts only")
@doc_tag("Prompts")
async def list_public_prompts(request: Request) -> JSONResponse:
    c = _container(request)
    items = await c.prompt.list_public(
        limit=int(request.args.get("limit", "50")),
        offset=int(request.args.get("offset", "0")),
        code=request.args.get("code"),
    )
    return JSONResponse({
        "total": len(items),
        "items": [c.prompt.to_response(p).model_dump(mode="json") for p in items],
    })


@prompt_bp.get("/<code>")
@doc_summary("Get a prompt by code")
@doc_tag("Prompts")
async def get_prompt(request: Request, code: str) -> JSONResponse:
    c = _container(request)
    try:
        p = await c.prompt.get_by_code(code)
    except NotFoundError:
        return _err("PROMPT_NOT_FOUND", f"prompt {code!r} not found", status=404)
    return JSONResponse(c.prompt.to_response(p).model_dump(mode="json"))


@prompt_bp.post("/")
@doc_summary("Create a prompt")
@doc_tag("Prompts")
async def create_prompt(request: Request) -> JSONResponse:
    c = _container(request)
    try:
        req = CreatePromptRequest(**(request.json or {}))
    except Exception as e:
        return _err("VALIDATION_FAILED", f"Invalid body: {e}")
    try:
        p = await c.prompt.create(req, actor=_actor(request))
    except DuplicateError as e:
        return _err("DUPLICATE_PROMPT", str(e), status=409)
    return JSONResponse(
        c.prompt.to_response(p).model_dump(mode="json"), status=201,
    )


@prompt_bp.put("/<code>")
@doc_summary("Update a prompt")
@doc_tag("Prompts")
async def update_prompt(request: Request, code: str) -> JSONResponse:
    c = _container(request)
    try:
        req = UpdatePromptRequest(**(request.json or {}))
    except Exception as e:
        return _err("VALIDATION_FAILED", f"Invalid body: {e}")
    try:
        p = await c.prompt.get_by_code(code)
    except NotFoundError:
        return _err("PROMPT_NOT_FOUND", f"prompt {code!r} not found", status=404)
    try:
        u = await c.prompt.update(str(p.id), req, actor=_actor(request))
    except PolicyError as e:
        return _err("FORBIDDEN", e.detail, status=403)
    return JSONResponse(c.prompt.to_response(u).model_dump(mode="json"))


@prompt_bp.delete("/<code>")
@doc_summary("Soft-delete a prompt")
@doc_tag("Prompts")
async def delete_prompt(request: Request, code: str) -> JSONResponse:
    c = _container(request)
    try:
        p = await c.prompt.get_by_code(code)
    except NotFoundError:
        return _err("PROMPT_NOT_FOUND", f"prompt {code!r} not found", status=404)
    await c.prompt.soft_delete(str(p.id), actor=_actor(request))
    return JSONResponse({"success": True, "code": code})


@prompt_bp.post("/<code>/publish")
@doc_summary("Toggle visibility (owner-only)")
@doc_tag("Prompts")
async def publish_prompt(request: Request, code: str) -> JSONResponse:
    c = _container(request)
    body = request.json or {}
    visibility = body.get("visibility")
    if visibility not in ("private", "public"):
        return _err("VALIDATION_FAILED", "visibility must be 'private' or 'public'")
    try:
        p = await c.prompt.get_by_code(code)
    except NotFoundError:
        return _err("PROMPT_NOT_FOUND", f"prompt {code!r} not found", status=404)
    out = await c.prompt.set_visibility(
        str(p.id), visibility, actor=_actor(request),
    )
    if out is None:
        return _err("FORBIDDEN", "only owner can change visibility", status=403)
    return JSONResponse(c.prompt.to_response(out).model_dump(mode="json"))


__all__ = ["prompt_bp"]
