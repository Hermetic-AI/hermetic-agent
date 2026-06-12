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
- chat_stream 外层套 ``stream_with_keepalive``: 业务事件空闲 15s 时
  yield ``: keepalive\\n\\n`` SSE 注释行, 防止 Vite/Nginx 代理关连接
- timeout/httpx 超时配置在 ``opencode_chat._build_http_client``:
  connect=10/read=300/write=10/pool=5, 替代 SDK 默认 5s 兜底
- 流式 SSE 端到端超时不依赖 opencode serve 的 idle, 由 hub 复用长连接

P0 重构: 把 SSE 拦截器/翻译/状态机/启发式全部下沉到
``openagent.api.http.streaming`` 子包, controller 自身只保留 endpoint
定义和业务流编排. 同时把模块内部 helper 以同名方式 re-export,
保留旧 import path 兼容 (tests/test_ask_user_card_intercept.py 等).
"""
from __future__ import annotations

import contextlib
import os
import traceback as _tb
from typing import Any

import structlog
from sanic import Blueprint
from sanic.request import Request
from sanic.response import JSONResponse
from sanic.response.types import ResponseStream
from sanic_ext import openapi as sanic_openapi

# 内部 helper 全部下沉到 api.streaming 子包, controller 只负责"业务编排"
from openagent.api.http.extractors import extract_mcp_token, resolve_session_directory
from openagent.api.http.schemas import (
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    get_bridge,
)
from openagent.api.http.streaming import (
    ASK_USER_TOOL_NAMES,
    DoneGate,
    is_ask_user_tool,
    should_bypass_hitl_placeholder,
    stream_with_ask_user_intercept,
    stream_with_keepalive,
    turn_event_to_sse,
)
from openagent.api.http.streaming.ask_user import _ask_user_to_card  # noqa: F401 (兼容 re-export)
from openagent.providers.base import ChatMessage
from openagent.providers.streaming import StreamEvent

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# 兼容旧 import path — 历史 tests / 旧代码引用这些名字
# ---------------------------------------------------------------------------
_extract_mcp_token = extract_mcp_token
_resolve_session_directory = resolve_session_directory
_stream_with_keepalive = stream_with_keepalive
_stream_with_ask_user_intercept = stream_with_ask_user_intercept
_is_ask_user_tool = is_ask_user_tool
_should_bypass_hitl_placeholder = should_bypass_hitl_placeholder
_turn_event_to_sse = turn_event_to_sse
_ask_user_to_card = _ask_user_to_card
ASK_USER_TOOL_NAMES = ASK_USER_TOOL_NAMES  # noqa: F811 (重导出)


# ---------------------------------------------------------------------------
# OpenAPI 装饰器别名
# ---------------------------------------------------------------------------
doc_summary = sanic_openapi.summary
doc_description = sanic_openapi.description
doc_tag = sanic_openapi.tag
operation = sanic_openapi.operation
response = sanic_openapi.response
body = sanic_openapi.body

chat_bp = Blueprint("chat", url_prefix="/agent")


# ---------------------------------------------------------------------------
# Helpers (private) — controller 业务编排需要的小函数
# ---------------------------------------------------------------------------


def _tail_traceback(exc: BaseException) -> str:
    """取 traceback 最后 3 行, 用于 5xx 响应里的人话描述."""
    tb = _tb.format_exc().splitlines()
    tail = tb[-3:] if len(tb) >= 3 else tb
    return " | ".join(line.strip() for line in tail)


def _format_500(exc: BaseException, log_event: str) -> JSONResponse:
    """统一的 5xx 响应: 结构化日志 + 截断后的 traceback."""
    msg = f"{type(exc).__name__}: {exc}  [{_tail_traceback(exc)}]"
    logger.error(log_event, error=msg)
    return JSONResponse(ErrorResponse(error=msg).model_dump(), status=500)


def _scenario_error_response(scen_err: Any) -> JSONResponse:
    """统一的 scenario 错误响应: 400 + 错误码 + action 提示."""
    return JSONResponse(
        {
            "success": False,
            "code": getattr(scen_err, "code", "ROUTING_FAILED"),
            "error": str(scen_err),
            "action": getattr(scen_err, "action", None),
        },
        status=400,
    )


def _build_scenario_dict(ctx_scenario: Any, routing_ctx: Any) -> dict | None:
    """构造返回体里的 scenario 字段 (含 matched_by 元信息)."""
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
    Returns:
        (scenario, injection, error_response_or_None)
    """
    scen_err = getattr(request.ctx, "scenario_error", None)
    if scen_err is not None:
        return None, None, _scenario_error_response(scen_err)
    scenario = getattr(request.ctx, "scenario", None)
    injection = getattr(request.ctx, "injection", None)
    if scenario is None or injection is None:
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
    """从 scenario.resources.model 读模型 ID, 空白时返回 None."""
    resources = getattr(scenario, "resources", None)
    model = getattr(resources, "model", None) if resources is not None else None
    return str(model).strip() or None if model else None


def _extract_effective_mcp_token(request: Request) -> str | None:
    """Read request token, falling back to the container-level flight token.

    顺序: 1) request header (X-MCP-Token / Authorization / token);
          2) settings.flight_mcp_token_env 指向的 env 变量 (容器级别).

    fallback env var 名从 settings.flight_mcp_token_env 读 (默认
    "FLIGHT_API_KEY"), 跟 docker/render_config.py 保持一致.
    """
    token = extract_mcp_token(request)
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


async def _resolve_or_create_session(
    bridge,
    body: ChatRequest,
    *,
    model_hint: str | None = None,
    request: Request | None = None,
) -> tuple[str | None, str | None, str | None]:
    """解析 session_id / agent_name; 找不到 / 出错时返 (None, None, error_message).

    Returns:
        (session_id, agent_name, error_message) — 成功时 error_message 为 None.

    Note:
        历史上返回 (..., JSONResponse) 形式, controller 调 ``err.body.decode()``
        反向解析 JSON. P0 重构后改为直接返 str 错误消息, controller 负责
        SSE/JSON 编码. 这是 API 边界 (controller ↔ controller helper)
        不再传 HTTP 响应对象的改进.
    """
    if body.session_id:
        agent_name = bridge.get_agent_for_session(body.session_id)
        if agent_name is None:
            return None, None, f"Session '{body.session_id}' not found"
        return body.session_id, agent_name, None

    if body.agent_name:
        agent_name = body.agent_name
    else:
        agents = bridge.list_agents()
        if not agents:
            return None, None, "No agents registered"
        agent_name = next(iter(agents))

    try:
        session_info = await bridge.create_session(  # type: ignore[func-returns-value]
            agent_name=agent_name,
            model=body.model or model_hint,
            directory=resolve_session_directory(request) if request is not None else None,
        )
    except Exception as e:
        return None, None, f"{type(e).__name__}: {e}"
    return session_info.session_id, agent_name, None


def _build_chat_response(
    result,
    agent_name: str,
    fallback_session_id: str,
    scenario_dict: dict | None = None,
    injection: Any = None,
) -> ChatResponse:
    """把 bridge.chat 的 ChatResult 转成对外的 ChatResponse (Pydantic)."""
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
            return JSONResponse(ErrorResponse(error=err).model_dump(), status=400)

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

    P0 重构: 用 ``DoneGate`` 替代 ``done_written`` 布尔, 避免重复写 done.
    """
    bridge = get_bridge(request)
    scen_err = getattr(request.ctx, "scenario_error", None)
    if scen_err is not None:
        code = getattr(scen_err, "code", "ROUTING_FAILED")
        err_msg = f"[{code}] {scen_err}"

        async def _scenario_err(resp: ResponseStream) -> None:
            gate = DoneGate()
            await gate.write_error_if_pending(resp, message=err_msg, code=code, retry=2000)
            await gate.write_done_if_pending(resp)
            with contextlib.suppress(Exception):
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
            gate = DoneGate()
            await gate.write_error_if_pending(resp, message=err_msg)
            await gate.write_done_if_pending(resp)
            with contextlib.suppress(Exception):
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
            gate = DoneGate()
            await gate.write_error_if_pending(resp, message="scenario setup failed")
            await gate.write_done_if_pending(resp)
            with contextlib.suppress(Exception):
                await resp.eof()
        return ResponseStream(_err, status=400, content_type="text/event-stream")
    params = _effective_params(json_body, injection)
    model_hint = _scenario_model(scenario)
    routing_ctx = getattr(request.ctx, "routing_context", None)
    matched_by = routing_ctx.matched_by if routing_ctx else "default"

    # P0-#4: 路由正则 + 日期解析, 严格校验 (不放过"从abc到def"或"13-45")
    bypass_hitl = (
        scenario is not None
        and should_bypass_hitl_placeholder(scenario, json_body.message)
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
        # P0-#3: 单一 done 哨兵 — 全程只写一次 done, 避免前端 EventSource
        # 收到多个 done 触发 reconnect 风暴.
        gate = DoneGate()
        try:
            session_id, agent_name, err = await _resolve_or_create_session(
                bridge,
                json_body,
                model_hint=model_hint,
                request=request,
            )
            if err is not None:
                await gate.write_error_if_pending(
                    resp, message=err, code="SESSION_ERROR"
                )
                await gate.write_done_if_pending(resp)
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
                    await resp.write(turn_event_to_sse(turn_evt).to_sse())
                    if turn_evt.type.value == "suspend":
                        # HITL: stop the stream after the suspend event
                        break
                logger.info(
                    "chat_stream_hitl_suspended",
                    scenario=scenario.name,
                    turn_id=turn_id,
                )
                # 写 done 哨兵 (HITL 不一定自然 emit done)
                await gate.write_done_if_pending(resp)
                return

            # 4. Normal scenario: bridge.chat(stream=True)
            # Auto-append ask_user synthetic tool so LLM can emit AUIP cards.
            scenario_tools = list(params["tools"] or [])
            tools_set = set(scenario_tools)
            if "ask_user" not in tools_set:
                scenario_tools.append("ask_user")
            # Card-type whitelist: prefer scenario.a2ui.card_schemas; default open.
            card_schemas = (
                set(scenario.a2ui.card_schemas)
                if scenario and scenario.a2ui.card_schemas
                else None
            )
            # P0-1: 把 prompt_builder + scenario 透传给 bridge, 让
            # scenario.progressive_skill (on_demand / explicit) 真正生效.
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
            intercepted = stream_with_ask_user_intercept(
                iterator, allowed_card_types=card_schemas,
            )
            keepalived = stream_with_keepalive(intercepted)
            try:
                async for chunk in keepalived:
                    if isinstance(chunk, str):
                        # 心跳注释行, 直接写裸字符串 (SSE 协议)
                        await resp.write(chunk)
                    else:
                        if _should_skip_bridge_event(chunk, session_id):
                            continue
                        if chunk.type == "done":
                            await gate.write_done(resp, chunk)
                        else:
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
            # 兜底: 流自然结束但还没写过 done, 写一次
            await gate.write_done_if_pending(resp)
            logger.info(
                "chat_stream_completed",
                scenario=scenario.name if scenario else None,
                session_id=session_id,
                agent_name=agent_name,
            )
        except Exception as e:
            logger.error("chat_stream_failed", error=str(e), exc_info=_tb.format_exc())
            # 错误透传: 把异常以 SSE error 事件发前端, 让前端能展示
            # 可读错误并触发 EventSource 重连 (带 retry 提示).
            with contextlib.suppress(Exception):
                await gate.write_error_if_pending(
                    resp,
                    message=f"{type(e).__name__}: {e}",
                    code="CHAT_STREAM_FAILED",
                    retry=2000,
                )
            # 错误路径后再发 done 收尾, 避免前端永远等不到流结束
            await gate.write_done_if_pending(resp)
        finally:
            with contextlib.suppress(Exception):
                await resp.eof()

    return ResponseStream(
        streaming_fn,
        status=200,
        content_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


def _should_skip_bridge_event(event: StreamEvent, session_id: str) -> bool:
    """adapter-private events already emitted by controller. Skip duplicates."""
    return event.type == "session" and event.data.get("session_id") == session_id
