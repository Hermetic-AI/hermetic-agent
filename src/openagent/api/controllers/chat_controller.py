"""ChatController - POST /chat and POST /chat/stream.

P6/F2 改造: 真正接入 scenario + injection.
- ``request.ctx.scenario`` 由 ScenarioMiddleware 注入
- ``request.ctx.injection`` 由 ScenarioMiddleware 注入 (白名单过滤后)
- ``request.ctx.scenario_error`` 在路由失败时设置, controller 优先检查
- HITL 场景: 转交 SuspendableScheduler, 把 TurnEvent 翻译为 SSE 事件
- 普通场景: 用 injection.final_* 调 bridge.chat, 流开头 emit scenario 事件
- AUIP 卡片: single 场景下, 把 LLM 调 ask_user 合成工具的 tool_use
  拦截为 card SSE 事件 (HITL 由 SuspendableScheduler 负责)

P8 长连接加固 (P0 流式断流修复):
- chat_stream 外层套 ``_stream_with_keepalive``: 业务事件空闲 15s 时
  yield ``: keepalive\\n\\n`` SSE 注释行, 防止 Vite/Nginx 代理关连接
- timeout/httpx 超时配置在 ``opencode_chat._build_http_client``:
  connect=10/read=300/write=10/pool=5, 替代 SDK 默认 5s 兜底
- 流式 SSE 端到端超时不依赖 opencode serve 的 idle, 由 hub 复用长连接
"""
from __future__ import annotations

import asyncio
import contextlib
import os
import re
import traceback as _tb
from typing import Any
from uuid import uuid4

import structlog
from sanic import Blueprint
from sanic.request import Request
from sanic.response import JSONResponse
from sanic.response.types import ResponseStream
from sanic_ext import openapi as sanic_openapi

from openagent.api.routes import _extract_mcp_token, _resolve_session_directory
from openagent.api.schemas import (
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    get_bridge,
)
from openagent.auip.cards import CARD_TYPES_SET
from openagent.providers.base import ChatMessage
from openagent.streaming import StreamEvent

logger = structlog.get_logger(__name__)


ASK_USER_TOOL_NAMES = {"ask_user", "ask_user_ask_user"}


def _is_ask_user_tool(tool_name: Any) -> bool:
    return str(tool_name or "") in ASK_USER_TOOL_NAMES

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


def _scenario_model(scenario: Any) -> str | None:
    resources = getattr(scenario, "resources", None)
    model = getattr(resources, "model", None) if resources is not None else None
    return str(model).strip() or None if model else None


def _extract_effective_mcp_token(request: Request) -> str | None:
    """Read request token, falling back to the container-level flight token.

    fallback env var 名从 settings.flight_mcp_token_env 读 (默认
    "FLIGHT_API_KEY"), 跟 docker/render_config.py 保持一致.
    """
    token = _extract_mcp_token(request)
    if token:
        return token
    try:
        from openagent.config.settings import get_settings
        env_name = get_settings().flight_mcp_token_env
    except Exception:  # pragma: no cover
        env_name = "FLIGHT_API_KEY"
    env_token = os.environ.get(env_name, "").strip() or None
    if env_token:
        logger.debug(
            "mcp_token_extracted",
            source=env_name,
            token_present=True,
            token_len=len(env_token),
        )
    return env_token


_FH_ROUTE_RE = re.compile(
    r"(?:从\s*)?[\u4e00-\u9fffA-Za-z]{2,12}\s*(?:到|至|飞)\s*[\u4e00-\u9fffA-Za-z]{2,12}"
)
_FH_DATE_RE = re.compile(
    r"(今天|明天|后天|大后天|周[一二三四五六日天]|星期[一二三四五六日天]|"
    r"\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?|\d{1,2}[-/.月]\d{1,2}日?)"
)


def _should_bypass_hitl_placeholder(scenario: Any, message: str) -> bool:
    """Avoid the P5 HITL placeholder when FH search inputs are already clear."""
    if getattr(scenario, "name", "") != "fh_domestic_flight_booking":
        return False
    return bool(_FH_ROUTE_RE.search(message) and _FH_DATE_RE.search(message))


async def _resolve_or_create_session(
    bridge,
    body: ChatRequest,
    *,
    model_hint: str | None = None,
    request: Request | None = None,
) -> tuple:
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
        session_info = await bridge.create_session(
            agent_name=agent_name,
            model=body.model or model_hint,
            directory=_resolve_session_directory(request) if request is not None else None,
        )
    except Exception as e:
        return None, None, _format_500(e, "chat_create_session_failed")
    return session_info.session_id, agent_name, None


def _build_chat_response(
    result,
    agent_name: str,
    fallback_session_id: str,
    scenario_dict: dict | None = None,
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
            turn_id=turn_event.turn_id,
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
    allowed_card_types: set | None,
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
    if not _is_ask_user_tool(tool_name):
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


async def _stream_with_ask_user_intercept(iterator, *, allowed_card_types: set | None):
    """Wrap bridge event iterator: convert ask_user tool_use to card, suppress tool_result.

    Yields:
        Transformed events. Suppresses tool_result(name=ask_user) - the LLM does
        not need to see its own tool result because the card itself is the ack.
    """
    last_ask_user_id: str | None = None
    async for event in iterator:
        if event.type == "tool_use":
            data = event.data or {}
            tool_name = data.get("name") or data.get("tool_name")
            if _is_ask_user_tool(tool_name):
                last_ask_user_id = str(data.get("id") or "")
                yield _ask_user_to_card(event, allowed_card_types=allowed_card_types)
                continue
        if event.type == "tool_result" and last_ask_user_id is not None:
            data = event.data or {}
            tool_name = data.get("name") or data.get("tool_name")
            tool_id = str(data.get("id") or "")
            if _is_ask_user_tool(tool_name) and (not last_ask_user_id or tool_id == last_ask_user_id):
                last_ask_user_id = None
                continue
        yield event


# 心跳间隔 (秒): 15s 是 Vite / Nginx / Cloud LB / 浏览器侧 SSE 实现都接受的
# "足够安静 + 不被杀" 的平衡点. 短了浪费带宽, 长了对端可能误判 idle.
def _should_skip_bridge_event(event: StreamEvent, session_id: str) -> bool:
    """Return True for adapter-private events already emitted by controller."""
    return event.type == "session" and event.data.get("session_id") == session_id


DEFAULT_SSE_KEEPALIVE_INTERVAL = 15.0


def _sse_keepalive_interval() -> float:
    """SSE 心跳间隔 (秒). 优先 settings.sse_keepalive_interval, 兜底模块常量."""
    try:
        from openagent.config.settings import get_settings
        return float(get_settings().sse_keepalive_interval)
    except Exception:  # pragma: no cover
        return DEFAULT_SSE_KEEPALIVE_INTERVAL


async def _stream_with_keepalive(
    iterator,
    *,
    keepalive_interval: float | None = None,
):
    """SSE 心跳包装 — 在业务事件空闲时插入 SSE 注释行, 防止中间代理断连.

    SSE 协议规定 ``: xxx\\n`` 注释行会被浏览器 EventSource / 标准 SSE 解析器
    忽略内容, 但能重置对端 keep-alive 计时器. 没有这层, 长 LLM 思考会让
    Vite proxy / Nginx / 浏览器在 30-60s 后关闭连接.

    行为:
    - 业务事件 (text/reasoning/tool/card/...) → 原样 yield
    - ``keepalive_interval`` 秒内没业务事件 → yield 一次 ``: keepalive\\n\\n``
    - ``done`` / ``error`` 事件 → 原样 yield 然后退出
    """
    loop = asyncio.get_event_loop()
    last_yield = loop.time()
    keepalive_text = ": keepalive\n\n"
    if keepalive_interval is None:
        keepalive_interval = _sse_keepalive_interval()
    async for event in iterator:
        yield event
        if event.type in ("done", "error"):
            return
        now = loop.time()
        if now - last_yield >= keepalive_interval:
            # 直接 yield 字符串, Sanic ResponseStream.write 接受 str/bytes
            yield keepalive_text
            last_yield = now
        else:
            last_yield = now


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
    model_hint = _scenario_model(scenario)

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
        session_id, agent_name, err = await _resolve_or_create_session(
            bridge,
            json_body,
            model_hint=model_hint,
            request=request,
        )
        if err is not None:
            return err

        result = await bridge.chat(
            session_id=session_id,
            messages=[ChatMessage(role="user", content=json_body.message)],
            model=json_body.model or model_hint,
            system_prompt=params["system_prompt"],
            skills=params["skills"],
            tools=params["tools"],
            timeout=json_body.timeout,
            mcp_token=_extract_effective_mcp_token(request),
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
    "5. If LLM calls `ask_user`: `card` event (single mode; frontend may continue via chat)\n"
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
            await resp.write(StreamEvent.error(message=err_msg, code=code, retry=2000).to_sse())
            await resp.write(StreamEvent.done().to_sse())
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
    model_hint = _scenario_model(scenario)
    routing_ctx = getattr(request.ctx, "routing_context", None)
    matched_by = routing_ctx.matched_by if routing_ctx else "default"

    bypass_hitl = (
        scenario is not None
        and _should_bypass_hitl_placeholder(scenario, json_body.message)
    )
    is_hitl = (
        scenario is not None
        and scenario.execution.orchestration == "hitl"
        and not bypass_hitl
    )
    turn_store = getattr(request.app.ctx, "turn_store", None)
    hitl_factory = getattr(request.app.ctx, "hitl_factory", None)

    logger.info(
        "chat_stream_request",
        scenario=scenario.name if scenario else None,
        matched_by=matched_by,
        is_hitl=is_hitl,
        bypass_hitl=bypass_hitl,
        session_id=json_body.session_id,
        agent_name=json_body.agent_name,
        model=json_body.model,
        message_length=len(json_body.message),
    )

    async def streaming_fn(resp: ResponseStream) -> None:
        done_written = False
        try:
            session_id, agent_name, err = await _resolve_or_create_session(
                bridge,
                json_body,
                model_hint=model_hint,
                request=request,
            )
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
                turn_id = await turn_store.create_turn(
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
            # P0-1: 把 prompt_builder + scenario 透传给 bridge, 让
            # scenario.progressive_skill (on_demand / explicit) 真正生效.
            # None 时 bridge 降级到旧 build_system_prompt_with_skills 路径.
            prompt_builder = getattr(request.app.ctx, "prompt_builder", None)
            iterator = await bridge.chat(
                session_id=session_id,
                messages=[ChatMessage(role="user", content=json_body.message)],
                model=json_body.model or model_hint,
                system_prompt=params["system_prompt"],
                skills=params["skills"],
                tools=scenario_tools,
                timeout=json_body.timeout,
                mcp_token=_extract_effective_mcp_token(request),
                stream=True,
                prompt_builder=prompt_builder,
                scenario=scenario,
                current_state=None,  # single-mode streaming: 走 initial state
            )
            # 拦截链: ask_user 转 card → 加 SSE keepalive 心跳
            # keepalive 在业务事件空闲时 yield SSE 注释行, 防止 Vite/Nginx
            # 代理在长 LLM 思考时关连接
            intercepted = _stream_with_ask_user_intercept(
                iterator, allowed_card_types=card_schemas,
            )
            keepalived = _stream_with_keepalive(intercepted)
            try:
                async for chunk in keepalived:
                    if isinstance(chunk, str):
                        # 心跳注释行, 直接写裸字符串 (SSE 协议)
                        await resp.write(chunk)
                    else:
                        if _should_skip_bridge_event(chunk, session_id):
                            continue
                        if chunk.type == "done":
                            done_written = True
                        await resp.write(chunk.to_sse())
            except GeneratorExit:
                # Sanic 取消这个 coroutine 时, async for 走 GeneratorExit 路径。
                # 显式 aclose 底层 async generator, 让它走自己的 finally 收尾
                # (cancel chat_task / 释放 hub 订阅), 避免下层 generator 在
                # 处理 GeneratorExit 时被上层冒出的新异常 (例如 HTTPStatusError)
                # 顶掉, 触发 "async generator ignored GeneratorExit"。
                with contextlib.suppress(Exception):
                    await keepalived.aclose()
                with contextlib.suppress(Exception):
                    await intercepted.aclose()
                with contextlib.suppress(Exception):
                    await iterator.aclose()
                raise
            if not done_written:
                await resp.write(StreamEvent.done().to_sse())
                done_written = True
            logger.info(
                "chat_stream_completed",
                scenario=scenario.name if scenario else None,
                session_id=session_id,
                agent_name=agent_name,
            )
        except Exception as e:
            logger.error("chat_stream_failed", error=str(e), exc_info=_tb.format_exc())
            # P8: 错误透传 — 把异常以 SSE error 事件发前端, 让前端能展示
            # 可读错误并触发 EventSource 重连 (带 retry 提示).
            # 之前的 except: pass 会让 connection 静默断, 前端只能看到空 stream.
            try:
                await resp.write(
                    StreamEvent.error(
                        message=f"{type(e).__name__}: {e}",
                        code="CHAT_STREAM_FAILED",
                        retry=2000,  # 2s 后重试
                    ).to_sse()
                )
            except Exception as write_err:
                logger.warning(
                    "chat_stream_error_write_failed",
                    original_error=str(e),
                    write_error=str(write_err),
                )
        finally:
            # P8: 写一个 done 哨兵让前端知道流真的结束 (之前是 silent close).
            # 但只在非错误路径下写 — 错误路径已经发了 error 事件.
            with contextlib.suppress(Exception):
                if not done_written:
                    await resp.write(StreamEvent.done().to_sse())
                    done_written = True
            with contextlib.suppress(Exception):
                await resp.eof()

    return ResponseStream(
        streaming_fn,
        status=200,
        content_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
