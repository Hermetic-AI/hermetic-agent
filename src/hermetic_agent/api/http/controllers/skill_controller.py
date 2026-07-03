"""SkillController — /agent/skills/* CRUD 端点.

延迟加载 ServiceContainer: 不 import 到模块级,
避免 Sanic 路由注册时触发 DB 连接.
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

skill_bp = Blueprint("skills", url_prefix="/agent/skills-db")


def _get_container(request: Request):
    """从 request.app.ctx 获取 ServiceContainer (延迟 import)."""
    return request.app.ctx.service_container


def _err(code: str, message: str, status: int = 400) -> JSONResponse:
    return JSONResponse(
        {"success": False, "code": code, "error": message},
        status=status,
    )


@skill_bp.get("/")
@doc_summary("列出所有技能")
@doc_tag("Skills")
async def list_skills(request: Request) -> JSONResponse:
    from hermetic_agent.store.services.container import ServiceContainer

    container: ServiceContainer = _get_container(request)
    skills = await container.skill_service.list()
    return JSONResponse({
        "total": len(skills),
        "skills": [
            container.skill_service.to_response(s).model_dump(mode="json")
            for s in skills
        ],
    })


@skill_bp.get("/<code>")
@doc_summary("按 code 查询技能")
@doc_tag("Skills")
async def get_skill(request: Request, code: str) -> JSONResponse:
    from hermetic_agent.store.exceptions import NotFoundError
    from hermetic_agent.store.services.container import ServiceContainer

    container: ServiceContainer = _get_container(request)
    try:
        s = await container.skill_service.get_by_code(code)
    except NotFoundError:
        return _err("SKILL_NOT_FOUND", f"Skill {code!r} not found", status=404)
    return JSONResponse(
        container.skill_service.to_response(s).model_dump(mode="json")
    )


@skill_bp.post("/")
@doc_summary("创建技能")
@doc_tag("Skills")
async def create_skill(request: Request) -> JSONResponse:
    from hermetic_agent.store.dto.skill import CreateSkillRequest
    from hermetic_agent.store.exceptions import DuplicateError
    from hermetic_agent.store.services.container import ServiceContainer

    container: ServiceContainer = _get_container(request)
    body = request.json or {}
    try:
        req = CreateSkillRequest(**body)
    except Exception as e:
        return _err("VALIDATION_FAILED", f"Invalid request body: {e}")
    try:
        s = await container.skill_service.create(req)
    except DuplicateError as e:
        return _err("DUPLICATE_SKILL", str(e), status=409)
    return JSONResponse(
        container.skill_service.to_response(s).model_dump(mode="json"),
        status=201,
    )


@skill_bp.put("/<code>")
@doc_summary("更新技能")
@doc_tag("Skills")
async def update_skill(request: Request, code: str) -> JSONResponse:
    from hermetic_agent.store.dto.skill import UpdateSkillRequest
    from hermetic_agent.store.exceptions import NotFoundError
    from hermetic_agent.store.services.container import ServiceContainer

    container: ServiceContainer = _get_container(request)
    body = request.json or {}
    try:
        req = UpdateSkillRequest(**body)
    except Exception as e:
        return _err("VALIDATION_FAILED", f"Invalid request body: {e}")
    try:
        s = await container.skill_service.get_by_code(code)
    except NotFoundError:
        return _err("SKILL_NOT_FOUND", f"Skill {code!r} not found", status=404)
    try:
        updated = await container.skill_service.update(s.id, req)
    except NotFoundError:
        return _err("SKILL_NOT_FOUND", f"Skill {code!r} not found", status=404)
    return JSONResponse(
        container.skill_service.to_response(updated).model_dump(mode="json")
    )


@skill_bp.delete("/<code>")
@doc_summary("软删除技能")
@doc_tag("Skills")
async def delete_skill(request: Request, code: str) -> JSONResponse:
    from hermetic_agent.store.exceptions import NotFoundError
    from hermetic_agent.store.services.container import ServiceContainer

    container: ServiceContainer = _get_container(request)
    try:
        s = await container.skill_service.get_by_code(code)
    except NotFoundError:
        return _err("SKILL_NOT_FOUND", f"Skill {code!r} not found", status=404)
    await container.skill_service.soft_delete(s.id)
    return JSONResponse({"success": True, "code": code})


__all__ = ["skill_bp"]
