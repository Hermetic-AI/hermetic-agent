"""RegistryController — skills and tools CRUD (read & write)."""

from __future__ import annotations

from typing import Any

import structlog
from sanic import Blueprint
from sanic.response import JSONResponse
from sanic.request import Request

from sanic_ext import openapi as sanic_openapi

from openagent.api.schemas import (
    ErrorResponse,
    SkillResponse,
    ToolResponse,
    get_mcp_registry,
    get_skill_registry,
)
from openagent.mcp.registry import MCPRegistry
from openagent.skills.registry import Skill, SkillRegistry

logger = structlog.get_logger(__name__)

doc_summary = sanic_openapi.summary
doc_description = sanic_openapi.description
doc_tag = sanic_openapi.tag
operation = sanic_openapi.operation
response = sanic_openapi.response
body = sanic_openapi.body

registry_bp = Blueprint("registry", url_prefix="/agent")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_name_present(body: dict | None) -> ErrorResponse | None:
    """校验 body 是否存在 `name` 字段，缺失则返回 ErrorResponse，否则 None。"""
    if not body or "name" not in body:
        return ErrorResponse(error="name is required")
    return None


def _skill_to_dict(s: Skill) -> dict[str, Any]:
    """把 Skill 对象序列化为对外的 dict 视图。"""
    return {
        "name": s.name,
        "description": s.description,
        "version": s.version,
        "triggers": s.triggers,
        "input_schema": s.input_schema,
        "output_schema": s.output_schema,
        "mcp_tools": s.mcp_tools,
        "source": s.source,
    }


def _build_skill(body: dict) -> Skill:
    """从请求 body 构造 Skill 实例。"""
    return Skill(
        name=str(body["name"]),
        description=str(body.get("description", "")),
        version=str(body.get("version", "1.0.0")),
        triggers=list(body.get("triggers", [])),
        input_schema=body.get("input_schema", {}),
        output_schema=body.get("output_schema", {}),
        prompt_template=str(body.get("prompt_template", "")),
        mcp_tools=list(body.get("mcp_tools", [])),
        source=str(body.get("source", "api")),
    )


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


@registry_bp.get("/skills")
@doc_summary("获取所有技能")
@doc_description("列出当前已注册的全部 Skill。")
@doc_tag("Skills")
@operation("listSkills")
@response(200, SkillResponse, description="技能列表")
async def get_skills(request: Request) -> JSONResponse:
    """处理 GET /agent/skills：列出全部已注册 Skill。"""
    skill_registry = get_skill_registry(request)
    skills = list(skill_registry.list_all())
    logger.info("skills_list_request", count=len(skills))
    return JSONResponse(
        SkillResponse(
            success=True,
            skills=[_skill_to_dict(s) for s in skills],
        ).model_dump()
    )


@registry_bp.post("/skills")
@doc_summary("注册新技能")
@doc_description("动态注册一个 Skill。")
@doc_tag("Skills")
@operation("registerSkill")
@response(201, SkillResponse, description="注册成功")
@response(400, ErrorResponse, description="参数错误")
async def register_skill(request: Request) -> JSONResponse:
    """处理 POST /agent/skills：动态注册一个 Skill。"""
    skill_registry = get_skill_registry(request)
    body = request.json
    err = _validate_name_present(body)
    if err is not None:
        logger.warning("skill_register_invalid", error=err.error)
        return JSONResponse(err.model_dump(), status=400)
    logger.info("skill_register_request", skill_name=str(body["name"]))
    try:
        skill = _build_skill(body)
        skill_registry.register(skill)
    except ValueError as e:
        logger.warning("skill_register_failed", skill_name=str(body["name"]), error=str(e))
        return JSONResponse(ErrorResponse(error=str(e)).model_dump(), status=400)
    except Exception as e:
        logger.error("skill_register_error", skill_name=str(body["name"]), error=str(e))
        return JSONResponse(
            ErrorResponse(error=f"{type(e).__name__}: {e}").model_dump(), status=500
        )
    logger.info("skill_registered", skill_name=skill.name)
    return JSONResponse(
        SkillResponse(success=True, skill=_skill_to_dict(skill)).model_dump(), status=201
    )


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@registry_bp.get("/tools")
@doc_summary("获取所有工具")
@doc_description("列出当前 MCP 注册表中的全部工具。")
@doc_tag("Tools")
@operation("listTools")
@response(200, ToolResponse, description="工具列表")
async def get_tools(request: Request) -> JSONResponse:
    """处理 GET /agent/tools：列出 MCP 注册表中的全部工具。"""
    mcp_registry = get_mcp_registry(request)
    tools = list(mcp_registry.list_all())
    logger.info("tools_list_request", count=len(tools))
    return JSONResponse(
        ToolResponse(success=True, tools=[t.to_dict() for t in tools]).model_dump()
    )


@registry_bp.post("/tools")
@doc_summary("注册新工具")
@doc_description("动态注册 MCP 工具。")
@doc_tag("Tools")
@operation("registerTool")
@response(201, ToolResponse, description="注册成功")
@response(400, ErrorResponse, description="参数错误")
async def register_tool(request: Request) -> JSONResponse:
    """处理 POST /agent/tools：动态注册一个 MCP 工具。"""
    mcp_registry = get_mcp_registry(request)
    body = request.json
    err = _validate_name_present(body)
    if err is not None:
        logger.warning("tool_register_invalid", error=err.error)
        return JSONResponse(err.model_dump(), status=400)
    logger.info("tool_register_request", tool_name=str(body["name"]))
    try:
        tool = mcp_registry.register(
            name=str(body["name"]),
            description=str(body.get("description", "")),
            input_schema=body.get("input_schema"),
            handler=body.get("handler"),
            remote_url=body.get("remote_url"),
            remote_tool_name=body.get("remote_tool_name"),
            enabled=body.get("enabled", True),
        )
    except ValueError as e:
        logger.warning("tool_register_failed", tool_name=str(body["name"]), error=str(e))
        return JSONResponse(ErrorResponse(error=str(e)).model_dump(), status=400)
    except Exception as e:
        logger.error("tool_register_error", tool_name=str(body["name"]), error=str(e))
        return JSONResponse(
            ErrorResponse(error=f"{type(e).__name__}: {e}").model_dump(), status=500
        )
    logger.info("tool_registered", tool_name=tool.name)
    return JSONResponse(ToolResponse(success=True, tool=tool.to_dict()).model_dump(), status=201)


@registry_bp.patch("/tools/<name>/enabled")
@doc_summary("启用或禁用工具")
@doc_description("Body: `{\"enabled\": true/false}`")
@doc_tag("Tools")
@operation("updateToolEnabled")
@response(200, ToolResponse, description="更新后的工具信息")
@response(404, ErrorResponse, description="工具不存在")
async def update_tool_enabled(request: Request, name: str) -> JSONResponse:
    """处理 PATCH /agent/tools/<name>/enabled：启用或禁用指定工具。"""
    mcp_registry = get_mcp_registry(request)
    body = request.json
    if body is None or "enabled" not in body:
        logger.warning("tool_enabled_invalid", tool_name=name)
        return JSONResponse(
            ErrorResponse(error="enabled field is required").model_dump(), status=400
        )
    logger.info("tool_enabled_request", tool_name=name, enabled=bool(body["enabled"]))
    try:
        mcp_registry.set_enabled(name, bool(body["enabled"]))
    except KeyError as e:
        logger.warning("tool_enabled_not_found", tool_name=name, error=str(e))
        return JSONResponse(ErrorResponse(error=str(e)).model_dump(), status=404)
    except Exception as e:
        logger.error("tool_enabled_failed", tool_name=name, error=str(e))
        return JSONResponse(
            ErrorResponse(error=f"{type(e).__name__}: {e}").model_dump(), status=500
        )
    tool = mcp_registry.get_tool(name)
    logger.info("tool_enabled_updated", tool_name=name)
    return JSONResponse(ToolResponse(success=True, tool=tool.to_dict() if tool else None).model_dump())
