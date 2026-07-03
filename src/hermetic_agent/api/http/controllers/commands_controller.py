"""CommandsController — /agent/commands/* CRUD 端点.

镜像 PromptsController: list / community / get / create / update /
delete / publish(<code>, owner-only).
"""
from __future__ import annotations

import structlog
from sanic import Blueprint
from sanic.request import Request
from sanic.response import JSONResponse
from sanic_ext import openapi as sanic_openapi

from hermetic_agent.store.dto._common import ActorContext
from hermetic_agent.store.dto.command import (
    CreateCommandRequest,
    UpdateCommandRequest,
)
from hermetic_agent.store.exceptions import DuplicateError, NotFoundError, PolicyError

logger = structlog.get_logger(__name__)
doc_summary = sanic_openapi.summary
doc_tag = sanic_openapi.tag
command_bp = Blueprint("commands", url_prefix="/agent/commands")


def _container(request: Request):
    return request.app.ctx.service_container


def _err(code: str, message: str, status: int = 400) -> JSONResponse:
    return JSONResponse(
        {"success": False, "code": code, "error": message}, status=status,
    )


def _actor(request: Request) -> ActorContext:
    return getattr(request.ctx, "actor", ActorContext(user_id="anonymous"))


@command_bp.get("/")
@doc_summary("List commands (own + public)")
@doc_tag("Commands")
async def list_commands(request: Request) -> JSONResponse:
    c = _container(request)
    items = await c.command.list(
        actor=_actor(request),
        limit=int(request.args.get("limit", "50")),
        offset=int(request.args.get("offset", "0")),
        code=request.args.get("code"),
        status=request.args.get("status"),
    )
    return JSONResponse({
        "total": len(items),
        "items": [c.command.to_response(x).model_dump(mode="json") for x in items],
    })


@command_bp.get("/community")
@doc_summary("List public commands only")
@doc_tag("Commands")
async def list_public_commands(request: Request) -> JSONResponse:
    c = _container(request)
    items = await c.command.list_public(
        limit=int(request.args.get("limit", "50")),
        offset=int(request.args.get("offset", "0")),
        code=request.args.get("code"),
    )
    return JSONResponse({
        "total": len(items),
        "items": [c.command.to_response(x).model_dump(mode="json") for x in items],
    })


@command_bp.get("/<code>")
@doc_summary("Get a command by code")
@doc_tag("Commands")
async def get_command(request: Request, code: str) -> JSONResponse:
    c = _container(request)
    try:
        x = await c.command.get_by_code(code)
    except NotFoundError:
        return _err("COMMAND_NOT_FOUND", f"command {code!r} not found", status=404)
    return JSONResponse(c.command.to_response(x).model_dump(mode="json"))


@command_bp.post("/")
@doc_summary("Create a command")
@doc_tag("Commands")
async def create_command(request: Request) -> JSONResponse:
    c = _container(request)
    try:
        req = CreateCommandRequest(**(request.json or {}))
    except Exception as e:
        return _err("VALIDATION_FAILED", f"Invalid body: {e}")
    try:
        x = await c.command.create(req, actor=_actor(request))
    except DuplicateError as e:
        return _err("DUPLICATE_COMMAND", str(e), status=409)
    return JSONResponse(
        c.command.to_response(x).model_dump(mode="json"), status=201,
    )


@command_bp.put("/<code>")
@doc_summary("Update a command")
@doc_tag("Commands")
async def update_command(request: Request, code: str) -> JSONResponse:
    c = _container(request)
    try:
        req = UpdateCommandRequest(**(request.json or {}))
    except Exception as e:
        return _err("VALIDATION_FAILED", f"Invalid body: {e}")
    try:
        x = await c.command.get_by_code(code)
    except NotFoundError:
        return _err("COMMAND_NOT_FOUND", f"command {code!r} not found", status=404)
    try:
        u = await c.command.update(str(x.id), req, actor=_actor(request))
    except PolicyError as e:
        return _err("FORBIDDEN", e.detail, status=403)
    return JSONResponse(c.command.to_response(u).model_dump(mode="json"))


@command_bp.delete("/<code>")
@doc_summary("Soft-delete a command")
@doc_tag("Commands")
async def delete_command(request: Request, code: str) -> JSONResponse:
    c = _container(request)
    try:
        x = await c.command.get_by_code(code)
    except NotFoundError:
        return _err("COMMAND_NOT_FOUND", f"command {code!r} not found", status=404)
    await c.command.soft_delete(str(x.id), actor=_actor(request))
    return JSONResponse({"success": True, "code": code})


@command_bp.post("/<code>/publish")
@doc_summary("Toggle visibility (owner-only)")
@doc_tag("Commands")
async def publish_command(request: Request, code: str) -> JSONResponse:
    c = _container(request)
    body = request.json or {}
    visibility = body.get("visibility")
    if visibility not in ("private", "public"):
        return _err("VALIDATION_FAILED", "visibility must be 'private' or 'public'")
    try:
        x = await c.command.get_by_code(code)
    except NotFoundError:
        return _err("COMMAND_NOT_FOUND", f"command {code!r} not found", status=404)
    out = await c.command.set_visibility(
        str(x.id), visibility, actor=_actor(request),
    )
    if out is None:
        return _err("FORBIDDEN", "only owner can change visibility", status=403)
    return JSONResponse(c.command.to_response(out).model_dump(mode="json"))


__all__ = ["command_bp"]
