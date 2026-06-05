"""ChatController - POST /chat and POST /chat/stream.

P6/F2 改造: 真正接入 scenario + injection.
- ``request.ctx.scenario`` 由 ScenarioMiddleware 注入
- ``request.ctx.injection`` 由 ScenarioMiddleware 注入 (白名单过滤后)
- ``request.ctx.scenario_error`` 在路由失败时设置, controller 优先检查
- HITL 场景: 转交 SuspendableScheduler, 把 TurnEvent 翻译为 SSE 事件
- 普通场景: 用 injection.final_* 调 bridge.chat, 流开头 emit scenario 事件
- AUIP 卡片: single 场景下, 把 LLM 调 ask_user 合成工具的 tool_use
  拦截为 card SSE 事件 (HITL 由 SuspendableScheduler 负责)
"""
from __future__ import annotations

import time
import traceback as _tb
from typing import Any, Optional
from uuid import uuid4

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
from openagent.api.routes import _extract_mcp_token
from openagent.auip.cards import CARD_TYPES_SET

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
    tb = _tb.format_exc().splitlines()
    tail = tb[-3:] if len(tb) >= 3 else tb
    return " | ".join(line.strip() for line in tail)


def _format_500(exc: BaseException, log_event: str) -> JSONResponse:
    msg = f"{type(exc).__name__}: {exc}  [{_tail_traceback(exc)}]"
    logger.error(log_event, error=msg)
    return JSONResponse(ErrorResponse(error=msg).model_dump(), status=500)


def _scenario_error_response(scen_err: Any) -> JSONResponse:
    """统一的 scenario 错误响应."""
    return JSONResponse(
        {
            "success": False,
            "code": getattr(scen_err, "code", "ROUTING_FAILED"),
            "error": str(scen_err),
            "action": getattr(scen_err, "action", None),
        },
        status=400,
    )


def _build_scenario_dict(ctx_scenario: Any, routing_ctx: Any) -> dict:
    """构造返回体里的 scenario 字段."""
    if ctx_scenario is None:
        return None
    out = {
        "name": ctx_scenario.name,
        "version": ctx_scenario.version,
        "orchestration": ctx_scenario.execution.orchestration,
    }
    if routing_ctx is not None:
        out["matched_by"] = routing_ctx.matched_by
    return out


def _resolve_injection(request: Request, body: ChatRequest) -> tuple:
    """从 request.ctx 拿到 scenario + injection (middleware 已设置).

    任何 scenario 错误都已挂在 ctx.scenario_error, 直接返回.
    """
    scen_err = getattr(request.ctx, "scenario_error", None)
    if scen_err is not None:
        return None, None, _scenario_error_response(scen_err)
    scenario = getattr(request.ctx, "scenario", None)
    injection = getattr(request.ctx, "injection", None)
    routing_ctx = getattr(request.ctx, "routing_context", None)
    if scenario is None or injection is None:
        # middleware 没跑 (例如直接 unit test), 兜底用 raw body
        logger.warning(
            "scenario_ctx_missing_falling_back",
            has_scenario=scenario is not None,
            has_injection=injection is not None,
        )
    return scenario, injection, None


def _effective_params(body: ChatRequest, injection: Any) -> dict:
    """从 injection (或兜底用 body) 抽取实际传给 bridge.chat 的参数."""
    if injection is not None:
        return {
            "system_prompt": injection.final_system_prompt,
            "skills": injection.final_skills,
            "tools": injection.final_tools,
        }
    return {
        "system_prompt": body.system_prompt,
        "skills": body.skills,
        "tools": body.tools,
    }


async def _resolve_or_create_session(bridge, body: ChatRequest) -> tuple:
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
    scenario_dict: Optional[dict] = None,
    injection: Any = None,
) -> ChatResponse:
    resp = ChatResponse(
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
    if scenario_dict is not None:
        resp.scenario = scenario_dict
    if injection is not None:
        resp.routing = {
            "matched_by": getattr(getattr(injection, "injection_log", None), "matched_by", "default"),
            "rejected_skills": getattr(injection, "rejected_skills", []),
            "rejected_tools": getattr(injection, "rejected_tools", []),
        }
    return resp


# ---------------------------------------------------------------------------
# HITL bridge: SuspendableScheduler TurnEvent -> SSE StreamEvent
# ---------------------------------------------------------------------------


def _turn_event_to_sse(turn_event) -> StreamEvent:
    """把 auip.TurnEvent 翻译为 streaming.StreamEvent (复用现有 SSE 协议)."""
    from openagent.auip import TurnEventType

    t = turn_event.type
    d = turn_event.data or {}
    if t == TurnEventType.SESSION:
        return StreamEvent.session(session_id=d.get("session_id", ""))
    if t == TurnEventType.TEXT:
        return StreamEvent.text(content=d.get("text") or d.get("content", ""))
    if t == TurnEventType.REASONING:
        return StreamEvent.reasoning(content=d.get("content", ""))
    if t == TurnEventType.TOOL_USE:
        return StreamEvent.tool_use(
            tool_name=d.get("name", "unknown"),
            input_data=d.get("input", {}),
            id=d.get("id", ""),
        )
    if t == TurnEventType.TOOL_RESULT:
        return StreamEvent.tool_result(
            tool_name=d.get("name", "unknown"),
            output=d.get("output", ""),
            id=d.get("id", ""),
            is_error=d.get("is_error", False),
        )
    if t == TurnEventType.CARD:
        card = d.get("card", {})
        return StreamEvent.card(
            card_id=d.get("card_id", ""),
            card_type=card.get("card_type", "UNKNOWN"),
            card=card,
            correlation_id=d.get("correlation_id", ""),
        )
    if t == TurnEventType.STATE:
        return StreamEvent.state(state=d.get("state", ""), note=d.get("note", ""))
    if t == TurnEventType.SUSPEND:
        return StreamEvent.suspend(
            checkpoint_id=d.get("checkpoint_id", ""),
            card=d.get("card", {}),
            correlation_id=d.get("correlation_id", ""),
            input_schema=d.get("input_schema", {}),
        )
    if t == TurnEventType.RESUME:
        return StreamEvent.resume(checkpoint_id=d.get("checkpoint_id", ""))
    if t == TurnEventType.DONE:
        return StreamEvent.done(stop_reason=d.get("stop_reason", "end_turn"))
    if t == TurnEventType.ERROR:
        return StreamEvent.error(message=d.get("message", "unknown"), code=d.get("code", ""))
    # fallback
    return StreamEvent(text=str(d))


# ---------------------------------------------------------------------------
# AUIP ask_user interception (single-mode streaming)
# ---------------------------------------------------------------------------


def _ask_user_to_card(
    event: StreamEvent,
    *,
    allowed_card_types: Optional[set],
) -> StreamEvent:
    """把 tool_use(ask_user) 转成 card 事件. 其它事件原样返回.

    Args:
        event: 来自 bridge 的 StreamEvent.
        allowed_card_types: scenario.a2ui.card_schemas 白名单; None 表示
            不校验 (CARD_TYPES_SET 全部允许).

    Returns:
        转换后的 card 事件; 非 ask_user 事件原样返回, 非法 card_type 返回 error.
    """
    if event.type != "tool_use":
        return event
    data = event.data or {}
    tool_name = data.get("name") or data.get("tool_name")
    if tool_name != "ask_user":
        return event

    inp = data.get("input") or {}
    card_type = str(inp.get("card_type") or "CHAT_FALLBACK")
    if card_type not in CARD_TYPES_SET:
        return StreamEvent.error(
            message=(
                f"LLM called ask_user with unknown card_type: {card_type!r}. "
                f"Valid: {sorted(CARD_TYPES_SET)}"
            ),
            code="CARD_TYPE_INVALID",
        )
    if allowed_card_types is not None and card_type not in allowed_card_types:
        return StreamEvent.error(
            message=(
                f"Current scenario does not allow card_type={card_type!r}; "
                f"whitelist: {sorted(allowed_card_types)}"
            ),
            code="CARD_TYPE_NOT_ALLOWED",
        )

    correlation_id = str(data.get("id") or inp.get("correlation_id") or "")
    card_id = str(inp.get("card_id") or f"card-{uuid4().hex[:8]}")
    body = inp.get("body")
    if body is None:
        # compatibility: LLM flat-fields everything into ask_user input
        body = {k: v for k, v in inp.items() if k not in {"card_type", "title"}}
    card_payload: dict = {
        "card_id": card_id,
        "card_type": card_type,
        "schema_version": str(inp.get("schema_version") or "1.0"),
        "title": str(inp.get("title") or ""),
        "body": body if isinstance(body, dict) else {},
        "fields": inp.get("fields") or [],
        "options": inp.get("options") or [],
        "actions": inp.get("actions") or inp.get("decision_buttons") or [],
        "decision_buttons": inp.get("decision_buttons") or [],
        "metadata": inp.get("metadata") or {},
        "dismissible": bool(inp.get("dismissible", False)),
    }
    return StreamEvent.card(
        card_id=card_id,
        card_type=card_type,
        card=card_payload,
        correlation_id=correlation_id,
    )


async def _stream_with_ask_user_intercept(iterator, *, allowed_card_types: Optional[set]):
    """Wrap bridge event iterator: convert ask_user tool_use to card, suppress tool_result.

    Yields:
        Transformed events. Suppresses tool_result(name=ask_user) - the LLM does
        not need to see its own tool result because the card itself is the ack.
    """
    last_ask_user_id: Optional[str] = None
    async for event in iterator:
        if event.type == "tool_use":
            data = event.data or {}
            tool_name = data.get("name") or data.get("tool_name")
            if tool_name == "ask_user":
                last_ask_user_id = str(data.get("id") or "")
                yield _ask_user_to_card(event, allowed_card_types=allowed_card_types)
                continue
        if event.type == "tool_result" and last_ask_user_id is not None:
            data = event.data or {}
            tool_name = data.get("name") or data.get("tool_name")
            tool_id = str(data.get("id") or "")
            if tool_name == "ask_user" and (not last_ask_user_id or tool_id == last_ask_user_id):
                last_ask_user_id = None
                continue
        yield event


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@chat_bp.post("/chat")
@doc_summary("Send a message and get a synchronous reply")
@doc_description(
    "Send a user message to the agent and wait for the full reply.\n\n"
    "If `X-Scenario` header or body.scenario is provided, route to that scenario;\n"
    "otherwise let ScenarioRouter match by keyword.\n"
    "Scenario skills/tools whitelist filters the caller's request."
)
@doc_tag("Chat")
@operation("agentChat")
@body(ChatRequest)
@response(200, ChatResponse, description="Successful agent reply")
@response(400, ErrorResponse, description="Bad request or no available agent")
@response(500, ErrorResponse, description="Server error")
async def chat(request: Request) -> JSONResponse:
    """Handle POST /agent/chat: send a message and return the synchronous agent reply."""
    scen_err = getattr(request.ctx, "scenario_error", None)
    if scen_err is not None:
        return _scenario_error_response(scen_err)
    bridge = get_bridge(request)
    try:
        json_body = ChatRequest(**(request.json or {}))
    except Exception as e:
        logger.warning("chat_request_invalid", error=str(e))
        return JSONResponse(
            ErrorResponse(error=f"Invalid request body: {e}").model_dump(),
            status=400,
        )

    scenario, injection, err = _resolve_injection(request, json_body)
    if err is not None:
        return err
    scenario_dict = _build_scenario_dict(scenario, getattr(request.ctx, "routing_context", None))
    params = _effective_params(json_body, injection)

    logger.info(
        "chat_request",
        scenario=scenario.name if scenario else None,
        matched_by=(
            getattr(request.ctx, "routing_context", None).matched_by
            if getattr(request.ctx, "routing_context", None)
            else None
        ),
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
            system_prompt=params["system_prompt"],
            skills=params["skills"],
            tools=params["tools"],
            timeout=json_body.timeout,
            mcp_token=_extract_mcp_token(request),
        )
        logger.info(
            "chat_completed",
            scenario=scenario.name if scenario else None,
            session_id=session_id,
            agent_name=agent_name,
            success=result.success,
        )
        return JSONResponse(
            _build_chat_response(
                result,
                agent_name,
                json_body.session_id or "",
                scenario_dict=scenario_dict,
                injection=injection,
            ).model_dump()
        )
    except Exception as e:
        return _format_500(e, "chat_failed")


@chat_bp.post("/chat/stream")
@doc_summary("Send a message and get a streaming reply (SSE)")
@doc_description(
    "Send a user message to the agent and stream the response via Server-Sent Events.\n\n"
    "**Event sequence**:\n"
    "1. `scenario` event (matched_by / scenario_name / version)\n"
    "2. `session` event (session_id)\n"
    "3. Business events (text / reasoning / tool_use / tool_result / state)\n"
    "4. If orchestration=hitl: `card` + `suspend` then stop the stream\n"
    "5. If LLM calls `ask_user`: `card` event (single mode only, no suspend)\n"
    "6. `done` event to end the stream\n\n"
    "If the scenario is unavailable or routing fails, the first event is `error`."
)
@doc_tag("Chat")
@operation("agentChatStream")
@body(ChatRequest)
async def chat_stream(request: Request) -> ResponseStream:
    """Handle POST /agent/chat/stream: send a message and stream the response.

    F2 changes:
    - Read request.ctx.scenario + injection
    - Emit `scenario` event at the start
    - HITL scenarios: hand off to SuspendableScheduler, translate TurnEvent to SSE
    - Normal scenarios: use injection.final_* and call bridge.chat(stream=True)
    - AUIP: intercept LLM's ask_user synthetic-tool tool_use as a card event
    """
    bridge = get_bridge(request)
    scen_err = getattr(request.ctx, "scenario_error", None)
    if scen_err is not None:
        code = getattr(scen_err, "code", "ROUTING_FAILED")
        err_msg = f"[{code}] {scen_err}"

        async def _scenario_err(resp: ResponseStream) -> None:
            await resp.write(StreamEvent.error(message=err_msg, code=code).to_sse())
            await resp.eof()

        return ResponseStream(
            _scenario_err,
            status=400,
            content_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    try:
        json_body = ChatRequest(**(request.json or {}))
    except Exception as e:
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

    scenario, injection, err = _resolve_injection(request, json_body)
    if err is not None:
        async def _err(resp: ResponseStream):
            await resp.write(StreamEvent.error(message="scenario setup failed").to_sse())
            await resp.eof()
        return ResponseStream(_err, status=400, content_type="text/event-stream")
    params = _effective_params(json_body, injection)
    routing_ctx = getattr(request.ctx, "routing_context", None)
    matched_by = routing_ctx.matched_by if routing_ctx else "default"

    is_hitl = scenario is not None and scenario.execution.orchestration == "hitl"
    turn_store = getattr(request.app.ctx, "turn_store", None)
    hitl_factory = getattr(request.app.ctx, "hitl_factory", None)

    logger.info(
        "chat_stream_request",
        scenario=scenario.name if scenario else None,
        matched_by=matched_by,
        is_hitl=is_hitl,
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
                    StreamEvent.error(
                        message=err.body.decode() if err.body else "session error",
                        code="SESSION_ERROR",
                    ).to_sse()
                )
                return

            # 1. Emit scenario event at the start
            await resp.write(
                StreamEvent.scenario(
                    name=scenario.name if scenario else "_unknown",
                    version=scenario.version if scenario else "",
                    matched_by=matched_by,
                    orchestration=scenario.execution.orchestration if scenario else "single",
                ).to_sse()
            )
            # 2. Session event
            await resp.write(StreamEvent.session(session_id=session_id).to_sse())

            # 3. Branch: HITL goes through SuspendableScheduler
            if is_hitl and turn_store is not None and hitl_factory is not None:
                turn_id = f"turn-{uuid4().hex[:12]}"
                await turn_store.create_turn(
                    session_id=session_id,
                    skill_name=scenario.name,
                    skill_version=scenario.version,
                )
                scheduler = hitl_factory(scenario)

                augmented_prompt = (
                    f"[Scenario: {scenario.name} v{scenario.version}]\n"
                    f"[Allowed skills: {params['skills']}]\n"
                    f"[Allowed tools: {params['tools']}]\n"
                    f"---\n{params['system_prompt'] or ''}\n---\n"
                    f"User: {json_body.message}"
                )

                async for turn_evt in scheduler.run_turn(
                    turn_id=turn_id,
                    session_id=session_id,
                    prompt=augmented_prompt,
                ):
                    await resp.write(_turn_event_to_sse(turn_evt).to_sse())
                    if turn_evt.type.value == "suspend":
                        # HITL: stop the stream after the suspend event
                        break
                logger.info(
                    "chat_stream_hitl_suspended",
                    scenario=scenario.name,
                    turn_id=turn_id,
                )
                return

            # 4. Normal scenario: bridge.chat(stream=True)
            # Auto-append ask_user synthetic tool so LLM can emit AUIP cards.
            scenario_tools = list(params["tools"] or [])
            if "ask_user" not in scenario_tools:
                scenario_tools.append("ask_user")
            # Card-type whitelist: prefer scenario.a2ui.card_schemas; default open.
            card_schemas = (
                set(scenario.a2ui.card_schemas)
                if scenario and scenario.a2ui.card_schemas
                else None
            )
            iterator = await bridge.chat(
                session_id=session_id,
                messages=[ChatMessage(role="user", content=json_body.message)],
                model=json_body.model,
                system_prompt=params["system_prompt"],
                skills=params["skills"],
                tools=scenario_tools,
                timeout=json_body.timeout,
                mcp_token=_extract_mcp_token(request),
                stream=True,
            )
            async for event in _stream_with_ask_user_intercept(
                iterator, allowed_card_types=card_schemas,
            ):
                await resp.write(event.to_sse())
            await resp.write(StreamEvent.done().to_sse())
            logger.info(
                "chat_stream_completed",
                scenario=scenario.name if scenario else None,
                session_id=session_id,
                agent_name=agent_name,
            )
        except Exception as e:
            logger.error("chat_stream_failed", error=str(e), exc_info=_tb.format_exc())
            try:
                await resp.write(
                    StreamEvent.error(message=f"{type(e).__name__}: {e}").to_sse()
                )
            except Exception:
                pass
        finally:
            try:
                await resp.eof()
            except Exception:
                pass

    return ResponseStream(
        streaming_fn,
        status=200,
        content_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
