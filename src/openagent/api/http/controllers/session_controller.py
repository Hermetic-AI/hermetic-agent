"""SessionController — session CRUD and history."""

from __future__ import annotations

from sanic import Blueprint
from sanic.request import Request
from sanic.response import JSONResponse
from sanic_ext import openapi as sanic_openapi

from openagent.api.http.schemas import (
    CreateSessionRequest,
    CreateSessionResponse,
    ErrorResponse,
    get_bridge,
)

logger = __import__("structlog").get_logger(__name__)

doc_summary = sanic_openapi.summary
doc_description = sanic_openapi.description
doc_tag = sanic_openapi.tag
operation = sanic_openapi.operation
response = sanic_openapi.response
body = sanic_openapi.body

session_bp = Blueprint("session", url_prefix="/agent")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@session_bp.post("/session")
@doc_summary("创建新会话")
@doc_description("在指定 Agent 实例上创建新的会话上下文，可用于后续 chat 调用。")
@doc_tag("Session")
@operation("createSession")
@body(CreateSessionRequest)
@response(201, CreateSessionResponse, description="会话创建成功")
@response(404, ErrorResponse, description="Agent 实例不存在")
@response(500, ErrorResponse, description="服务器内部错误")
async def create_session(request: Request) -> JSONResponse:
    """处理 POST /agent/session：在指定 Agent 上创建新会话。"""
    bridge = get_bridge(request)
    try:
        json_body = CreateSessionRequest(**(request.json or {}))
    except Exception as e:
        logger.warning("session_create_request_invalid", error=str(e))
        return JSONResponse(
            ErrorResponse(error=f"Invalid request body: {e}").model_dump(),
            status=400,
        )
    logger.info(
        "session_create_request",
        agent_name=json_body.agent_name,
        model=json_body.model,
        session_id=json_body.session_id,
    )
    try:
        session_info = await bridge.create_session(
            agent_name=json_body.agent_name,
            model=json_body.model,
            system_prompt=json_body.system_prompt,
            session_id=json_body.session_id,
        )
        logger.info(
            "session_created",
            session_id=session_info.session_id,
            agent_name=session_info.agent_name,
        )
        return JSONResponse(
            CreateSessionResponse(
                success=True,
                session_id=session_info.session_id,
                agent_name=session_info.agent_name,
                agent_base_url=session_info.agent_base_url,
                model=session_info.model,
            ).model_dump(),
            status=201,
        )
    except ValueError as e:
        logger.warning("session_create_not_found", agent_name=json_body.agent_name, error=str(e))
        return JSONResponse(ErrorResponse(error=str(e)).model_dump(), status=404)
    except RuntimeError as e:
        logger.error("session_create_failed", agent_name=json_body.agent_name, error=str(e))
        return JSONResponse(ErrorResponse(error=str(e)).model_dump(), status=500)


@session_bp.get("/session/<session_id>")
@doc_summary("获取会话信息")
@doc_description("根据 session_id 查询会话的元信息（所属 Agent、模型、URL 等）。")
@doc_tag("Session")
@operation("getSession")
@response(200, CreateSessionResponse, description="返回会话信息")
@response(404, ErrorResponse, description="会话不存在")
async def get_session(request: Request, session_id: str) -> JSONResponse:
    """处理 GET /agent/session/<session_id>：查询单个会话元信息。"""
    bridge = get_bridge(request)
    logger.info("session_get_request", session_id=session_id)
    try:
        session_info = await bridge.get_session(session_id)
    except KeyError as e:
        logger.warning("session_get_not_found", session_id=session_id, error=str(e))
        return JSONResponse(
            ErrorResponse(error=f"Session '{session_id}' not found").model_dump(),
            status=404,
        )
    except Exception as e:
        logger.error("session_get_failed", session_id=session_id, error=str(e))
        return JSONResponse(
            ErrorResponse(error=f"{type(e).__name__}: {e}").model_dump(),
            status=500,
        )
    if session_info is None:
        logger.warning("session_get_not_found", session_id=session_id)
        return JSONResponse(
            ErrorResponse(error=f"Session '{session_id}' not found").model_dump(),
            status=404,
        )
    logger.info("session_get_completed", session_id=session_id, agent_name=session_info.agent_name)
    return JSONResponse(
        {
            "success": True,
            "session_id": session_info.session_id,
            "agent_name": session_info.agent_name,
            "agent_base_url": session_info.agent_base_url,
            "model": session_info.model,
        }
    )


@session_bp.get("/session/<session_id>/messages")
@doc_summary("获取会话历史消息")
@doc_description("返回该会话下所有历史消息（按时间顺序）。")
@doc_tag("Session")
@operation("getSessionMessages")
@response(200, {"success": bool, "session_id": str, "messages": list})
@response(404, ErrorResponse, description="会话不存在")
async def get_messages(request: Request, session_id: str) -> JSONResponse:
    """处理 GET /agent/session/<session_id>/messages：拉取会话历史消息。"""
    bridge = get_bridge(request)
    logger.info("session_messages_request", session_id=session_id)
    try:
        messages = await bridge.get_messages(session_id)
    except ValueError as e:
        logger.warning("session_messages_not_found", session_id=session_id, error=str(e))
        return JSONResponse(ErrorResponse(error=str(e)).model_dump(), status=404)
    except RuntimeError as e:
        logger.error("session_messages_failed", session_id=session_id, error=str(e))
        return JSONResponse(ErrorResponse(error=str(e)).model_dump(), status=500)
    logger.info("session_messages_completed", session_id=session_id, count=len(messages))
    return JSONResponse(
        {
            "success": True,
            "session_id": session_id,
            "messages": [
                {
                    "role": getattr(m, "role", "user"),
                    "content": getattr(m, "content", str(m)),
                }
                for m in messages
            ],
        }
    )


@session_bp.delete("/session/<session_id>")
@doc_summary("删除会话")
@doc_description("删除指定会话及其历史消息。")
@doc_tag("Session")
@operation("deleteSession")
@response(200, {"success": bool, "session_id": str})
@response(404, ErrorResponse, description="会话不存在")
async def delete_session(request: Request, session_id: str) -> JSONResponse:
    """处理 DELETE /agent/session/<session_id>：删除会话及其历史。"""
    bridge = get_bridge(request)
    logger.info("session_delete_request", session_id=session_id)
    try:
        success = await bridge.delete(session_id)
    except ValueError as e:
        logger.warning("session_delete_not_found", session_id=session_id, error=str(e))
        return JSONResponse(ErrorResponse(error=str(e)).model_dump(), status=404)
    except Exception as e:
        logger.error("session_delete_failed", session_id=session_id, error=str(e))
        return JSONResponse(
            ErrorResponse(error=f"{type(e).__name__}: {e}").model_dump(),
            status=500,
        )
    logger.info("session_deleted", session_id=session_id, success=success)
    return JSONResponse({"success": success, "session_id": session_id})


@session_bp.post("/session/<session_id>/abort")
@doc_summary("中止运行中的会话")
@doc_description("打断当前正在执行的 Agent 调用。")
@doc_tag("Session")
@operation("abortSession")
@response(200, {"success": bool, "session_id": str})
@response(404, ErrorResponse, description="会话不存在")
async def abort_session(request: Request, session_id: str) -> JSONResponse:
    """处理 POST /agent/session/<session_id>/abort：打断正在执行的 Agent 调用。"""
    bridge = get_bridge(request)
    logger.info("session_abort_request", session_id=session_id)
    try:
        success = await bridge.abort(session_id)
    except ValueError as e:
        logger.warning("session_abort_not_found", session_id=session_id, error=str(e))
        return JSONResponse(ErrorResponse(error=str(e)).model_dump(), status=404)
    except Exception as e:
        logger.error("session_abort_failed", session_id=session_id, error=str(e))
        return JSONResponse(
            ErrorResponse(error=f"{type(e).__name__}: {e}").model_dump(),
            status=500,
        )
    logger.info("session_abort_completed", session_id=session_id, success=success)
    return JSONResponse({"success": success, "session_id": session_id})
