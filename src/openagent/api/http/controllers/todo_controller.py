"""TodoController — opencode 原生 task todo 端点的代理 (L1).

L1 通过 L3 ``auip.opencode_resolver`` 调 opencode SDK 包装的 todo_list,
不直接 import L4 providers (5 层依赖方向)。
"""
from __future__ import annotations

import structlog
from sanic import Blueprint
from sanic.request import Request
from sanic.response import JSONResponse
from sanic_ext import openapi as sanic_openapi

from openagent.api.http.schemas import ErrorResponse, get_bridge
from openagent.auip.opencode_resolver import list_todos_for_session

logger = structlog.get_logger(__name__)

doc_summary = sanic_openapi.summary
doc_description = sanic_openapi.description
doc_tag = sanic_openapi.tag
operation = sanic_openapi.operation
response = sanic_openapi.response

todo_bp = Blueprint("todos", url_prefix="/agent")


@todo_bp.get("/sessions/<session_id>/todo")
@doc_summary("列出 opencode 会话任务清单 (Todo)")
@doc_description(
    "代理 opencode `GET /session/:id/todo?directory=...` 端点。"
)
@doc_tag("Todo")
@operation("listTodos")
@response(200, {"success": bool, "session_id": str, "todos": list}, description="任务清单")
@response(404, ErrorResponse, description="session 不存在")
@response(502, ErrorResponse, description="opencode 服务错误")
async def list_todos_route(request: Request, session_id: str) -> JSONResponse:
    """GET /agent/sessions/:id/todo — 列出任务清单。"""
    bridge = get_bridge(request)
    todos, err = await list_todos_for_session(bridge, session_id)
    if err:
        status = 404 if "not found" in err else 502
        return JSONResponse(ErrorResponse(error=err).model_dump(), status=status)
    return JSONResponse({"success": True, "session_id": session_id, "todos": todos or []})


__all__ = ["todo_bp"]
