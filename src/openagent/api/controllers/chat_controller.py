"""ChatController — POST /chat and POST /chat/stream."""

from __future__ import annotations

import traceback as _tb
from typing import Optional

import structlog
from sanic import Blueprint
from sanic.response import JSONResponse
from sanic.response.types import ResponseStream
from sanic.request import Request

from sanic_ext import openapi as sanic_openapi

from openagent.api.schemas import (
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    get_bridge,
)
from openagent.providers.base import ChatMessage
from openagent.streaming import StreamEvent

logger = structlog.get_logger(__name__)

doc_summary = sanic_openapi.summary
doc_description = sanic_openapi.description
doc_tag = sanic_openapi.tag
operation = sanic_openapi.operation
response = sanic_openapi.response
body = sanic_openapi.body

chat_bp = Blueprint("chat", url_prefix="/agent")


# ---------------------------------------------------------------------------
# Helpers (private)
# ---------------------------------------------------------------------------


def _tail_traceback(exc: BaseException) -> str:
    """提取异常的 traceback 末尾 3 行（用于错误消息）。"""
    tb = _tb.format_exc().splitlines()
    tail = tb[-3:] if len(tb) >= 3 else tb
    return " | ".join(line.strip() for line in tail)


def _format_500(exc: BaseException, log_event: str) -> JSONResponse:
    """统一的 500 错误格式化：记日志并返回 ErrorResponse。"""
    msg = f"{type(exc).__name__}: {exc}  [{_tail_traceback(exc)}]"
    logger.error(log_event, error=msg)
    return JSONResponse(ErrorResponse(error=msg).model_dump(), status=500)


async def _resolve_or_create_session(
    bridge,
    body: ChatRequest,
) -> tuple[Optional[str], Optional[str], Optional[JSONResponse]]:
    """根据请求体解析或创建本次 chat 使用的 session。

    Returns:
        ``(session_id, agent_name, error_response)`` 三元组 —— 三者中
        ``agent_name`` 与 ``error_response`` 恰好有一个非空。
    """
    if body.session_id:
        agent_name = bridge.get_agent_for_session(body.session_id)
        if agent_name is None:
            return None, None, JSONResponse(
                ErrorResponse(error=f"Session '{body.session_id}' not found").model_dump(),
                status=404,
            )
        return body.session_id, agent_name, None

    if body.agent_name:
        agent_name = body.agent_name
    else:
        agents = bridge.list_agents()
        if not agents:
            return None, None, JSONResponse(
                ErrorResponse(error="No agents registered").model_dump(), status=400
            )
        agent_name = next(iter(agents))

    try:
        session_info = await bridge.create_session(agent_name=agent_name)
    except Exception as e:
        return None, None, _format_500(e, "chat_create_session_failed")
    return session_info.session_id, agent_name, None


def _build_chat_response(
    result,
    agent_name: str,
    fallback_session_id: str,
) -> ChatResponse:
    """把 bridge.chat 返回的 ChatResult 适配为 ChatResponse。"""
    return ChatResponse(
        success=result.success,
        session_id=result.session_id or fallback_session_id,
        agent_name=agent_name,
        result=(
            {
                "message": {
                    "role": result.message.role,
                    "content": result.message.content,
                },
                "tool_calls": [
                    {"id": tc.id, "name": tc.name, "input": tc.input}
                    for tc in (result.tool_calls or [])
                ],
                "stop_reason": result.stop_reason,
            }
            if result.message
            else None
        ),
        error=result.error,
        duration=result.duration,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@chat_bp.post("/chat")
@doc_summary("发送消息并获取回复")
@doc_description(
    "向 Agent 发送一条用户消息并同步等待完整回复。\n\n"
    "如果不提供 `session_id`，会自动创建新会话；提供则继续已有会话的上下文。"
)
@doc_tag("Chat")
@operation("agentChat")
@body(ChatRequest)
@response(200, ChatResponse, description="成功返回 Agent 回复")
@response(400, ErrorResponse, description="参数错误或无可用 Agent")
@response(500, ErrorResponse, description="服务器内部错误")
async def chat(request: Request) -> JSONResponse:
    """处理 POST /agent/chat：发送消息并同步返回 Agent 回复。"""
    bridge = get_bridge(request)
    try:
        json_body = ChatRequest(**(request.json or {}))
    except Exception as e:
        logger.warning("chat_request_invalid", error=str(e))
        return JSONResponse(
            ErrorResponse(error=f"Invalid request body: {e}").model_dump(),
            status=400,
        )

    logger.info(
        "chat_request",
        session_id=json_body.session_id,
        agent_name=json_body.agent_name,
        model=json_body.model,
        message_length=len(json_body.message),
    )

    try:
        session_id, agent_name, err = await _resolve_or_create_session(bridge, json_body)
        if err is not None:
            return err

        result = await bridge.chat(
            session_id=session_id,
            messages=[ChatMessage(role="user", content=json_body.message)],
            model=json_body.model,
            system_prompt=json_body.system_prompt,
            skills=json_body.skills,
            tools=json_body.tools,
            timeout=json_body.timeout,
        )
        logger.info(
            "chat_completed",
            session_id=session_id,
            agent_name=agent_name,
            success=result.success,
        )
        return JSONResponse(
            _build_chat_response(result, agent_name, json_body.session_id or "").model_dump()
        )
    except Exception as e:
        return _format_500(e, "chat_failed")


@chat_bp.post("/chat/stream")
@doc_summary("发送消息并获取流式回复 (SSE)")
@doc_description("向 Agent 发送一条用户消息并以 Server-Sent Events 形式流式返回响应。")
@doc_tag("Chat")
@operation("agentChatStream")
@body(ChatRequest)
async def chat_stream(request: Request) -> ResponseStream:
    """处理 POST /agent/chat/stream：发送消息并以 SSE 形式流式返回。"""
    bridge = get_bridge(request)
    try:
        json_body = ChatRequest(**(request.json or {}))
    except Exception as e:
        # Python deletes the `as e` binding when the except block exits, so
        # capture it into a local that the inner closure can safely close over.
        err_msg = f"Invalid request body: {e}"
        logger.warning("chat_stream_request_invalid", error=str(e))

        async def _invalid(resp: ResponseStream):
            await resp.write(StreamEvent.error(message=err_msg).to_sse())
            await resp.eof()

        return ResponseStream(
            _invalid,
            status=400,
            content_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    logger.info(
        "chat_stream_request",
        session_id=json_body.session_id,
        agent_name=json_body.agent_name,
        model=json_body.model,
        message_length=len(json_body.message),
    )

    async def streaming_fn(resp: ResponseStream) -> None:
        try:
            session_id, agent_name, err = await _resolve_or_create_session(bridge, json_body)
            if err is not None:
                await resp.write(
                    StreamEvent.error(message=err.body.decode() if err.body else "error").to_sse()
                )
                return

            await resp.write(StreamEvent.session(session_id=session_id).to_sse())
            iterator = await bridge.chat(
                session_id=session_id,
                messages=[ChatMessage(role="user", content=json_body.message)],
                model=json_body.model,
                system_prompt=json_body.system_prompt,
                skills=json_body.skills,
                tools=json_body.tools,
                timeout=json_body.timeout,
                stream=True,
            )
            async for event in iterator:
                await resp.write(event.to_sse())
            await resp.write(StreamEvent.done().to_sse())
            logger.info(
                "chat_stream_completed",
                session_id=session_id,
                agent_name=agent_name,
            )
        except Exception as e:
            logger.error("chat_stream_failed", error=str(e))
            await resp.write(StreamEvent.error(message=str(e)).to_sse())
        finally:
            await resp.eof()

    return ResponseStream(
        streaming_fn,
        status=200,
        content_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
