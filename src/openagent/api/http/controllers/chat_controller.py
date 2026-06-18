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

P-Feb-2026 改造: chat_controller 在 ``bridge.chat()`` 前后包一层
ServiceContainer 调用 — 持久化 user message + chat_turn + parts +
assistant message, 取代之前只在 adapter shim 里写一行 assistant message
的"半残"持久化. 详见 ``_persist_turn_and_user_msg`` / ``_StreamCollector``
等私有 helper. SDK adapter 里的 ``adapter._storage.create_message()``
调用 (opencode/chat.py + claude_code/chat.py 共 4 处) 已被移除, 避免
双写.
"""
from __future__ import annotations

import contextlib
import json
import os
import traceback as _tb
from typing import Any

import structlog
from sanic import Blueprint
from sanic.request import Request
from sanic.response import JSONResponse
from sanic.response.types import ResponseStream
from sanic_ext import openapi as sanic_openapi

from openagent.audit.log.log_markers import LM

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
from openagent.api.http.streaming.card_message_rewriter import rewrite_card_message
from openagent.api.http.streaming.ask_user import _ask_user_to_card  # noqa: F401 (兼容 re-export)
from openagent.providers.base import ChatMessage
from openagent.providers.streaming import StreamEvent
from openagent.store.dto.chat_turn import CreateChatTurnRequest
from openagent.store.dto.message import CreateMessageRequest
from openagent.store.dto.part import BatchCreatePartRequest, CreatePartRequest
from openagent.store.services import ServiceContainer

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


# ---------------------------------------------------------------------------
# P-Feb-2026: Persistence helpers (turn + user/assistant messages + parts)
# ---------------------------------------------------------------------------
# 设计目标: 把 ``bridge.chat()`` 之前/之后的 user message / chat_turn /
# assistant message / parts 持久化, 走新 ``ServiceContainer`` 路径 (6 实体
# + audit_log). 旧 ``MySQLStorage`` shim 里的 ``create_message(assistant)``
# 已经被从 opencode/chat.py + claude_code/chat.py 移除, controller 是
# assistant message 的唯一写入点.
#
# 失败处理: 全部 best-effort, 失败只 log warning 不影响 chat 响应本身
# (用户已经发了请求, 让他们拿到 chat 结果比存进 DB 更重要). 失败时
# turn 标 failed, audit 记录.
# ---------------------------------------------------------------------------


def _get_services(request: Request) -> ServiceContainer | None:
    """从 ``app.ctx.services`` 取 ServiceContainer. 没初始化 (例如 memory
    backend 的 unit test) 时返回 None, controller 跳过持久化但不影响 chat."""
    services = getattr(request.app.ctx, "services", None)
    _diag(
        "_get_services",
        has_services=services is not None,
        app_ctx_attrs=[k for k in dir(request.app.ctx) if not k.startswith("_")][:10],
    )
    return services


# P-Feb-2026 诊断: 这俩函数把每一步持久化调用的状态 / 入参 / 异常 trace 全部
# 打到日志. 上线后保留 — 在排查"为什么 chat_turn / parts 没存"的工单时是救命日志.
# 命中频率 = 1 次/对话, 不打 info 走 debug 避免污染生产日志.
def _diag(msg: str, **fields: Any) -> None:
    logger.debug("persist_diag", step=msg, **fields)


def _safe_json_dumps(obj: Any) -> str:
    """JSON serialize 任意对象, 兜底 ``default=str`` 处理 datetime / UUID /
    Decimal 等非原生类型. 用于 part.content 字段."""
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return str(obj)


class _StreamCollector:
    """把 ``StreamEvent`` 流缓冲成 ``(text_content, parts)`` 双元组.

    业务流: chat 跑出来的 ``StreamEvent`` 在 ``chat_stream()`` 里被 ``resp.write``
    转发给前端, 同时被 ``consume()`` 吃进 collector. 流结束后
    ``to_part_requests()`` 一次性 dump 给 ``MessageService.create`` + 
    ``PartService.batch_create``.

    关键不变量:
    - ``text`` = 所有 ``text`` 事件的 content 串接 (顺序保持)
    - ``reasoning`` = 所有 ``reasoning`` 事件的 content 串接
    - ``tool_calls`` = ``[tool_use → tool_result]`` 配对列表, LIFO 匹配
      (opencode 是先 emit tool_use 再 emit tool_result)
    """

    def __init__(self) -> None:
        self.text_chunks: list[str] = []
        self.reasoning_chunks: list[str] = []
        self.tool_calls: list[dict[str, Any]] = []
        self._pending_tool_use: dict[str, Any] | None = None

    def consume(self, event: StreamEvent) -> None:
        et = event.type
        data = event.data or {}
        if et == "text":
            self.text_chunks.append(str(data.get("content", "") or ""))
        elif et == "reasoning":
            self.reasoning_chunks.append(str(data.get("content", "") or ""))
        elif et == "tool_use":
            # 新一轮 tool_use, 暂存等 tool_result
            self._pending_tool_use = {
                "name": str(data.get("tool_name", "") or ""),
                "input": data.get("input"),
                "output": None,
            }
        elif et == "tool_result":
            payload = {
                "name": str(data.get("tool_name", "") or ""),
                "input": None,
                "output": data.get("output"),
            }
            if self._pending_tool_use is not None:
                # 配对到上一个 tool_use
                self._pending_tool_use["output"] = data.get("output")
                self.tool_calls.append(self._pending_tool_use)
                self._pending_tool_use = None
            else:
                # 没有前置 tool_use (少见, 但 opencode 偶尔会单独 emit)
                self.tool_calls.append(payload)

    @property
    def text(self) -> str:
        return "".join(self.text_chunks)

    @property
    def reasoning(self) -> str:
        return "".join(self.reasoning_chunks)

    def has_parts(self) -> bool:
        return bool(self.tool_calls) or bool(self.reasoning_chunks) or bool(self.text_chunks)

    def to_part_requests(
        self, message_id: str, session_id: str,
    ) -> list[CreatePartRequest]:
        """把收集到的事件转成 ``CreatePartRequest`` 列表 (按 position 排序).
        
        输出顺序: reasoning → text → tool_call → tool_result (每对配对).
        ``message_id`` 由 controller 在 message.create 之后回填.
        """
        parts: list[CreatePartRequest] = []
        position = 0
        if self.reasoning_chunks:
            parts.append(
                CreatePartRequest(
                    message_id=message_id,
                    session_id=session_id,
                    part_type="text",
                    content=self.reasoning,
                    position=position,
                    metadata={"role": "reasoning"},
                )
            )
            position += 1
        if self.text_chunks:
            parts.append(
                CreatePartRequest(
                    message_id=message_id,
                    session_id=session_id,
                    part_type="text",
                    content=self.text,
                    position=position,
                )
            )
            position += 1
        for tc in self.tool_calls:
            name = tc.get("name", "") or ""
            parts.append(
                CreatePartRequest(
                    message_id=message_id,
                    session_id=session_id,
                    part_type="tool_call",
                    content=_safe_json_dumps(tc.get("input") or {}),
                    position=position,
                    metadata={"tool_name": name},
                )
            )
            position += 1
            if tc.get("output") is not None:
                parts.append(
                    CreatePartRequest(
                        message_id=message_id,
                        session_id=session_id,
                        part_type="tool_result",
                        content=_safe_json_dumps(tc["output"]),
                        position=position,
                        metadata={"tool_name": name},
                    )
                )
                position += 1
        return parts


async def _persist_turn_and_user_msg(
    services: ServiceContainer,
    session_id: str,
    user_text: str,
    *,
    agent_name: str | None = None,
    model: str | None = None,
    actor_id: str | None = None,
) -> tuple[str, str] | None:
    """创建 chat_turn (pending→running) + user message. 返回 (turn_id, user_msg_id).

    失败返回 None 并 log warning, controller 会让 chat 继续 (best-effort).
    """
    _diag("enter_turn_user_msg", session_id=session_id, user_text_len=len(user_text or ""))
    try:
        turn = await services.chat_turn.create(
            CreateChatTurnRequest(
                session_id=session_id,
                agent_name=agent_name,
                model=model,
            ),
            actor_id=actor_id,
        )
        _diag("turn_created", turn_id=str(turn.id), status=getattr(turn, "status", None))
        await services.chat_turn.start(str(turn.id))
        _diag("turn_started", turn_id=str(turn.id))
        user_msg = await services.message.create(
            CreateMessageRequest(
                session_id=session_id,
                turn_id=str(turn.id),
                role="user",
                content=user_text,
            ),
            actor_id=actor_id,
        )
        _diag(
            "user_msg_created",
            user_msg_id=str(user_msg.id),
            session_msg_count=getattr(user_msg, "session_id", None),
        )
        return (str(turn.id), str(user_msg.id))
    except Exception as e:
        logger.warning(
            "persist_turn_user_msg_failed",
            session_id=session_id,
            user_text_len=len(user_text or ""),
            agent_name=agent_name,
            model=model,
            error_type=type(e).__name__,
            error=str(e),
            exc_info=_tb.format_exc(),
        )
        return None


async def _persist_assistant_message_sync(
    services: ServiceContainer,
    session_id: str,
    turn_id: str | None,
    reply_text: str,
    tool_calls: list,
    *,
    actor_id: str | None = None,
) -> str | None:
    """同步 ``/chat`` 端点: 持久化 assistant message + tool_calls 转 parts.
    
    ``tool_calls`` 来自 ``ChatResult.tool_calls`` (list[ToolCall]). 同步路径下
    opencode 不会走完整 tool_use/tool_result 流, 只把 tool_call 列表塞
    进 ChatResult. 这里把每个 ToolCall 展开成一个 ``tool_call`` part.
    """
    try:
        asst = await services.message.create(
            CreateMessageRequest(
                session_id=session_id,
                turn_id=turn_id,
                role="assistant",
                content=reply_text or "",
            ),
            actor_id=actor_id,
        )
        if tool_calls:
            parts: list[CreatePartRequest] = []
            for i, tc in enumerate(tool_calls):
                tc_name = getattr(tc, "name", "") or ""
                tc_input = getattr(tc, "input", None) or {}
                tc_id = getattr(tc, "id", "") or ""
                parts.append(
                    CreatePartRequest(
                        message_id=str(asst.id),
                        session_id=session_id,
                        part_type="tool_call",
                        content=_safe_json_dumps(tc_input),
                        position=i,
                        metadata={"tool_name": tc_name, "tool_id": tc_id},
                    )
                )
            if parts:
                await services.part.batch_create(
                    BatchCreatePartRequest(
                        message_id=str(asst.id),
                        session_id=session_id,
                        parts=parts,
                    ),
                    actor_id=actor_id,
                )
        return str(asst.id)
    except Exception as e:
        logger.warning(
            "persist_assistant_msg_sync_failed",
            session_id=session_id,
            error=str(e),
            exc_info=_tb.format_exc(),
        )
        return None


async def _persist_stream_assistant_message(
    services: ServiceContainer,
    session_id: str,
    turn_id: str | None,
    collector: _StreamCollector,
    *,
    actor_id: str | None = None,
) -> str | None:
    """流式 ``/chat/stream`` 端点: 把 ``_StreamCollector`` dump 给 service.

    顺序: 先 ``message.create`` 拿到 message_id, 再 ``part.batch_create`` 把
    collector 里的 part 一次性插进去. ``message_count`` 由 message_service
    自动 +1.
    """
    _diag(
        "enter_stream_assistant",
        turn_id=turn_id,
        text_len=len(collector.text or ""),
        text_chunks=len(collector.text_chunks),
        reasoning_chunks=len(collector.reasoning_chunks),
        tool_calls=len(collector.tool_calls),
        has_parts=collector.has_parts(),
    )
    try:
        asst = await services.message.create(
            CreateMessageRequest(
                session_id=session_id,
                turn_id=turn_id,
                role="assistant",
                content=collector.text,
            ),
            actor_id=actor_id,
        )
        _diag("asst_msg_created", asst_msg_id=str(asst.id))
        if collector.has_parts():
            part_reqs = collector.to_part_requests(str(asst.id), session_id)
            _diag("creating_parts", part_count=len(part_reqs))
            await services.part.batch_create(
                BatchCreatePartRequest(
                    message_id=str(asst.id),
                    session_id=session_id,
                    parts=part_reqs,
                ),
                actor_id=actor_id,
            )
            _diag("parts_created", part_count=len(part_reqs))
        return str(asst.id)
    except Exception as e:
        logger.warning(
            "persist_stream_assistant_msg_failed",
            session_id=session_id,
            turn_id=turn_id,
            error_type=type(e).__name__,
            error=str(e),
            exc_info=_tb.format_exc(),
        )
        return None


async def _complete_turn(
    services: ServiceContainer,
    turn_id: str,
    *,
    cost: float = 0,
    tokens_input: int = 0,
    tokens_output: int = 0,
    tokens_reasoning: int = 0,
    tokens_cache_read: int = 0,
    tokens_cache_write: int = 0,
) -> None:
    """标 turn 完成, 累加 session 聚合. cost / tokens 暂时传 0 —
    opencode SDK 当前未把 usage 回给上层, 等以后 opencode 加 ``usage`` 事件
    再 wiring."""
    try:
        await services.chat_turn.complete(
            turn_id,
            cost=cost,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            tokens_reasoning=tokens_reasoning,
            tokens_cache_read=tokens_cache_read,
            tokens_cache_write=tokens_cache_write,
        )
    except Exception as e:
        logger.warning("complete_turn_failed", turn_id=turn_id, error=str(e))


async def _fail_turn(
    services: ServiceContainer,
    turn_id: str,
    error_code: str,
    error_message: str,
) -> None:
    try:
        await services.chat_turn.fail(
            turn_id, error_code=error_code, error_message=error_message,
        )
    except Exception as e:
        logger.warning("fail_turn_failed", turn_id=turn_id, error=str(e))


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
        LM.CHAT_REQUEST,
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

        # P-Feb-2026: 持久化 turn + user message, 拿到 turn_id 后面 complete/fail 用
        services = _get_services(request)
        if services is None:
            logger.warning(
                "services_missing",
                session_id=session_id,
                note="app.ctx.services not set; chat_turn/parts persistence skipped",
            )
        turn_info = None
        if services is not None:
            turn_info = await _persist_turn_and_user_msg(
                services,
                session_id=session_id,
                user_text=json_body.message,
                agent_name=agent_name,
                model=json_body.model or model_hint,
                actor_id=None,
            )

        rewrite_result = rewrite_card_message(json_body.message)
        effective_message = rewrite_result.message
        result = await bridge.chat(
            session_id=session_id,
            messages=[ChatMessage(role="user", content=effective_message)],
            model=json_body.model or model_hint,
            system_prompt=params["system_prompt"],
            skills=params["skills"],
            tools=params["tools"],
            timeout=json_body.timeout,
            mcp_token=_extract_effective_mcp_token(request),
        )

        # P-Feb-2026: 持久化 assistant message + tool_calls, 然后 complete turn
        if services is not None and turn_info is not None:
            turn_id, _user_msg_id = turn_info
            asst_msg_id = await _persist_assistant_message_sync(
                services,
                session_id=session_id,
                turn_id=turn_id,
                reply_text=result.message.content if result.message else "",
                tool_calls=result.tool_calls or [],
                actor_id=None,
            )
            if asst_msg_id is not None and result.success:
                await _complete_turn(services, turn_id)
            elif asst_msg_id is None:
                await _fail_turn(
                    services, turn_id, "PERSIST_FAILED", "assistant message persist failed",
                )
            else:
                await _fail_turn(
                    services, turn_id,
                    error_code=result.error or "CHAT_FAILED",
                    error_message=(result.error or "chat returned success=False")[:500],
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
        # P-Feb-2026: 异常路径标 turn failed
        services = _get_services(request)
        if services is not None and turn_info is not None:
            turn_id, _ = turn_info
            await _fail_turn(
                services, turn_id,
                error_code=type(e).__name__,
                error_message=str(e)[:500],
            )
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
        LM.CHAT_STREAM,
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
        # P-Feb-2026: turn 持久化追踪. None 表示没初始化 (memory backend
        # 或 services 没挂上), 控制器仍然正常流 chat, 只是不写 DB.
        services = _get_services(request)
        turn_info: tuple[str, str] | None = None
        collector: _StreamCollector | None = None
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

            # P-Feb-2026: 持久化 turn + user message (流开始前)
            if services is not None:
                turn_info = await _persist_turn_and_user_msg(
                    services,
                    session_id=session_id,
                    user_text=json_body.message,
                    agent_name=agent_name,
                    model=json_body.model or model_hint,
                    actor_id=None,
                )
                if turn_info is not None:
                    collector = _StreamCollector()
            else:
                logger.warning(
                    "services_missing",
                    session_id=session_id,
                    note="app.ctx.services not set; chat_turn/parts persistence skipped",
                )

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
            rewrite_result = rewrite_card_message(json_body.message)
            effective_message = rewrite_result.message
            iterator = await bridge.chat(
                session_id=session_id,
                messages=[ChatMessage(role="user", content=effective_message)],
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
            # 自动发送卡片（如舱位选择），在 LLM 响应前发送
            for auto_card in rewrite_result.auto_cards:
                card_event = StreamEvent.card(
                    card_id=auto_card["card_id"],
                    card_type=auto_card["card_type"],
                    card=auto_card,
                )
                await resp.write(card_event.to_sse())
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
                        # P-Feb-2026: 同步收集事件用于流后持久化
                        if collector is not None:
                            collector.consume(chunk)
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

            # P-Feb-2026: 流结束 → 持久化 assistant message + parts, 然后 complete turn
            if services is not None and turn_info is not None and collector is not None:
                turn_id, _ = turn_info
                asst_msg_id = await _persist_stream_assistant_message(
                    services, session_id, turn_id, collector, actor_id=None,
                )
                if asst_msg_id is not None:
                    await _complete_turn(services, turn_id)
                else:
                    await _fail_turn(
                        services, turn_id, "PERSIST_FAILED", "assistant stream persist failed",
                    )

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
            # P-Feb-2026: 异常路径标 turn failed
            if services is not None and turn_info is not None:
                turn_id, _ = turn_info
                await _fail_turn(
                    services, turn_id,
                    error_code=type(e).__name__,
                    error_message=str(e)[:500],
                )
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
