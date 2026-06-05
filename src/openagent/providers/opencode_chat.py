"""Chat dispatch for the OpenCode adapter.

Module-level functions take the adapter instance as the first arg so they
can read its state (clients, sessions, mcp_registry, storage) without
becoming methods. The adapter class in ``opencode_adapter.py`` is a
thin shell that delegates to these functions.

Real-time streaming follows the official SDK recommendation
(https://github.com/anomalyco/opencode-sdk-python#streaming-responses):
subscribe to the long-lived ``client.event.list()`` SSE stream and filter
events for the target session_id, rather than parsing HTTP response bodies.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, AsyncIterator

import structlog

from openagent.providers.base import (
    AgentConfig,
    ChatMessage,
    ChatResult,
    SessionInfo,
    ToolCall,
)
from openagent.providers.llm_payload import (
    build_opencode_payload,
    log_opencode_request,
)
from openagent.store.base import Message as StorageMessage
from openagent.streaming import (
    OPENCODE_STREAM_END,
    StreamEvent,
    map_opencode_event,
)

try:
    from opencode_ai import AsyncOpencode  # type: ignore
except ImportError:  # pragma: no cover
    from openagent._vendor.opencode import AsyncOpencode  # type: ignore

if TYPE_CHECKING:
    from openagent.providers.opencode_adapter import OpenCodeAdapter

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Client lookup
# ---------------------------------------------------------------------------


def get_client(adapter: "OpenCodeAdapter", agent_name: str, base_url: str) -> AsyncOpencode:
    """获取或创建指定 Agent+base_url 对应的 AsyncOpencode 客户端。

    以 ``"{agent_name}:{base_url}"`` 为键在适配器内部做缓存，避免重复
    构造底层 HTTP 客户端。

    Args:
        adapter: 适配器实例，作为客户端缓存宿主。
        agent_name: Agent 名称。
        base_url: opencode serve 的 HTTP 入口。

    Returns:
        缓存或新建的 AsyncOpencode 客户端。
    """
    key = f"{agent_name}:{base_url}"
    if key not in adapter._clients:
        adapter._clients[key] = AsyncOpencode(base_url=base_url)
    return adapter._clients[key]


def _resolve_tool_names(adapter: "OpenCodeAdapter", tools: Any) -> list[dict[str, Any]] | None:
    """把 caller 传的 tools 列表 (str / MCPTool / 混合) 归一化为 opencode 格式.

    历史 caller 直接传 ``list[str]`` (scenario ``injection.final_tools``);
    也有传 ``MCPTool`` 对象 (历史 test 路径). 这里都兼容, 避免在
    opencode chat 里 ``t.name`` 触发 ``AttributeError``.
    """
    if not tools:
        return None
    names: list[str] = []
    for t in tools:
        if isinstance(t, str):
            names.append(t)
        else:
            name = getattr(t, "name", None)
            if name:
                names.append(str(name))
    if not names:
        return None
    # opencode-ai SDK 的 chat() 收 tools: Dict[str, bool] (tool_name → 是否启用),
    # 不是 list[ToolDefinition]. 见 site-packages/opencode_ai/resources/session.py:602.
    # 走 Dict 是 opencode 故意为之: tool schema 走 opencode config (provider 段),
    # chat 请求只声明"启用哪些", 跟自带 tool / MCP tool 解耦.
    # 这里给的是 MCP 名, opencode 不认识会忽略, 但 LLM 还能用 system_prompt
    # 教它的 bash+curl 调 MCP 端点 (这是 Phase 1 的 fallback).
    return {name: True for name in names}


def _workspace_query(session_info: SessionInfo) -> dict[str, Any]:
    """构造 opencode SDK 的 ``extra_query`` 参数,把会话工作区传给 server.

    opencode server 的 ``WorkspaceRoutingMiddleware`` 接受
    ``?directory=...``,用于:
      - ``InstanceState`` 按目录做 per-project 状态隔离
      - skill 发现从该目录向上扫描
      - 注入到 LLM 的 env 报告中
      - 限制文件/工具访问

    Returns:
        ``{"directory": "/path"}`` 当 session 绑定了工作区;否则空 dict。
    """
    if session_info.directory:
        return {"directory": session_info.directory}
    return {}


def _build_runtime_context(
    base_system_prompt: str | None,
    mcp_token: str | None,
) -> str | None:
    """在 scenario 的 system_prompt 末尾追加 ``<runtime-context>`` 块.

    把 per-request 的 MCP token 注入到 LLM 可见的 system 消息里 —— **不**
    走 opencode 配置或代理(那需要重启 agent 或多一层代理,用户都嫌重)。

    流程:
      1. 用户发 ``POST /agent/chat`` 带 ``X-MCP-Token: yyyy`` (或 ``Authorization: Bearer yyyy``)
      2. routes.py 读 header → bridge.chat(mcp_token=...) → adapter → 本函数
      3. 本函数把 token 拼到 system_prompt 末尾
      4. opencode serve 把 system 消息送给 LLM
      5. LLM 在调 MCP (走 Bash + curl) 时,从 system 块取 token 填 header
      6. opencode 的 Bash tool 实际执行 curl,带 token 打到 MCP 端

    返回 ``None`` 表示"原始 base_system_prompt 也是 None",无 token 时原样返回 base。
    """
    if not mcp_token:
        return base_system_prompt
    ctx = (
        "\n\n<runtime-context>\n"
        "MCP_TOKEN: " + mcp_token + "\n"
        "MCP_ENDPOINT: https://traveldev.feiheair.com/api/mcp\n"
        "MCP_AUTH_STYLE: header token: <value> | Authorization: Bearer <value>\n"
        "MCP_USAGE: 本对话专属 MCP token。调用任何 MCP 工具时,把它放到对应 "
        "header(token: ... 或 Authorization: Bearer ...)中。\n"
        "MCP_SECURITY: 不要在自然语言回复、表格、日志里回显这个 token。\n"
        "</runtime-context>"
    )
    if base_system_prompt:
        return base_system_prompt + ctx
    return ctx.lstrip("\n")


def _log_payload_kwargs(sdk_kwargs: dict[str, Any]) -> dict[str, Any]:
    """把 SDK 调用的 kwargs(用 ``id=``)翻译成 ``build_opencode_payload`` 用的(用 ``session_id=``)。

    ``opencode_payload_kwargs`` 同时服务两个调用:
      - ``client.session.chat(**sdk_kwargs)``    — SDK,参数名是 ``id``
      - ``build_opencode_payload(**sdk_kwargs)`` — 本地 log 辅助,参数名是 ``session_id``

    这两个签名不一致,所以 log 调用前翻译一次。直接 ``**sdk_kwargs`` 会因
    多余的 ``id=`` 或缺失 ``session_id=`` 抛 ``TypeError``。
    """
    out = {k: v for k, v in sdk_kwargs.items() if k != "id"}
    if "id" in sdk_kwargs:
        out["session_id"] = sdk_kwargs["id"]
    return out


# ---------------------------------------------------------------------------
# Chat dispatch
# ---------------------------------------------------------------------------


async def blocking_chat(
    adapter: "OpenCodeAdapter",
    session_id: str,
    messages: list[ChatMessage],
    *,
    model: str | None = None,
    system_prompt: str | None = None,
    tools: list[Any] | None = None,
    timeout: float | None = None,
    mcp_token: str | None = None,
) -> ChatResult:
    """阻塞式 chat——调用 SDK 并解析最终响应返回 ChatResult。

    Args:
        adapter: 适配器实例。
        session_id: 目标会话 ID。
        messages: 完整消息列表。
        model: 可选模型覆盖。
        system_prompt: 可选系统提示词（本实现未使用）。
        tools: 可选工具列表。
        timeout: 可选超时秒数。

    Returns:
        ChatResult；包含助手回复、工具调用或失败时的错误信息。
    """
    logger.info(
        "opencode_chat_start",
        session_id=session_id,
        message_count=len(messages),
        has_mcp_token=bool(mcp_token),
        mcp_token_len=len(mcp_token) if mcp_token else 0,
    )
    session_info = adapter._sessions.get(session_id)
    if not session_info:
        logger.error("opencode_chat_session_not_found", session_id=session_id)
        return ChatResult(
            success=False,
            message=ChatMessage(role="assistant", content=""),
            error=f"Session '{session_id}' not found",
            session_id=session_id,
            agent_name="",
        )

    agent_name = session_info.agent_name
    client = get_client(adapter, agent_name, session_info.agent_base_url)

    # Build last user message
    last_content = ""
    for msg in reversed(messages):
        if msg.role == "user":
            last_content = msg.content
            break

    # Build parts
    import uuid
    parts = [{"type": "text", "text": last_content, "id": f"prt_{str(uuid.uuid4())[:20]}"}]

    # Convert tools (callers may pass strings or MCPTool objects)
    tool_list = _resolve_tool_names(adapter, tools)

    opencode_payload_kwargs = dict(
        id=session_id,  # SDK param 名是 id,不是 session_id (Python kwarg 校验)
        model_id=model or session_info.model or "default",
        # providerID 必须是 opencode config.json 里 "provider" 块声明的名字.
        # 当前用 openai-compatible 接口 (OPENAI_BASE_URL 指向 minimax),
        # render_config.py 渲染出来的 config 里 provider 名是 "openai".
        # 早期这里误写成 "opencode" (opencode 自己的 brand), 会被 opencode server
        # 当成查不到的 provider → 400 Bad Request.
        provider_id="openai",
        parts=parts,
        system=_build_runtime_context(system_prompt, mcp_token),
        tools=tool_list,
        timeout=timeout,
        extra_query=_workspace_query(session_info),
    )

    log_opencode_request(build_opencode_payload(**_log_payload_kwargs(opencode_payload_kwargs)))

    try:
        result = await client.session.chat(**opencode_payload_kwargs)
    except Exception as e:
        logger.error("opencode_chat_failed", session_id=session_id, error=str(e))
        return ChatResult(
            success=False,
            message=ChatMessage(role="assistant", content=""),
            error=str(e),
            session_id=session_id,
            agent_name=agent_name,
        )

    msg_dict = result.model_dump() if hasattr(result, "model_dump") else {}
    reply = ""
    for part in msg_dict.get("parts", []):
        if part.get("type") == "text":
            reply = part.get("text", "")

    tool_calls = []
    for part in msg_dict.get("parts", []):
        if part.get("type") == "tool_use":
            tool_calls.append(ToolCall(
                id=part.get("id", ""),
                name=part.get("name", ""),
                input=part.get("input", {}),
            ))

    chat_msg = ChatMessage(role="assistant", content=reply)
    await adapter._storage.create_message(StorageMessage(
        session_id=session_id,
        role="assistant",
        content=reply,
    ))

    logger.info(
        "opencode_chat_completed",
        session_id=session_id,
        agent_name=agent_name,
        tool_call_count=len(tool_calls),
    )
    return ChatResult(
        success=True,
        message=chat_msg,
        stop_reason=msg_dict.get("stop_reason"),
        session_id=session_id,
        agent_name=agent_name,
        tool_calls=tool_calls,
    )


async def stream_chat(
    adapter: "OpenCodeAdapter",
    session_id: str,
    messages: list[ChatMessage],
    *,
    model: str | None = None,
    system_prompt: str | None = None,
    tools: list[Any] | None = None,
    timeout: float | None = None,
    mcp_token: str | None = None,
) -> AsyncIterator[StreamEvent]:
    """Stream chat progress in real time via the opencode-ai event bus.

    Per the official opencode-ai SDK docs, real-time streaming is achieved
    by subscribing to the long-lived ``client.event.list()`` SSE stream
    and filtering events for the target session. We do NOT parse HTTP
    response bodies from ``client.session.chat()`` — that endpoint
    buffers until completion, defeating the purpose of streaming.

    The flow is:
        1. Open ``client.event.list()`` (a typed ``AsyncStream`` of
           ``EventListResponse`` Pydantic models — discriminated union of
           ``message.updated``, ``message.part.updated``, ``session.idle``,
           ``session.error``, etc.).
        2. Fire ``client.session.chat(...)`` as a background task — this
           triggers the model run on the opencode serve side.
        3. Iterate the event stream; map relevant events to ``StreamEvent``
           via ``map_opencode_event``. Filter by ``session_id`` and only
           forward parts whose ``message_id`` belongs to an assistant
           message we've already seen in a ``message.updated`` event.
        4. Break the loop on the ``OPENCODE_STREAM_END`` sentinel, which
           is produced when ``session.idle`` (or ``session.error``) fires
           for our session.
        5. Close the event stream, await the chat task, and persist the
           final assistant text to storage for history retrieval.

    Args:
        adapter: 适配器实例。
        session_id: 目标会话 ID。
        messages: 完整消息列表。
        model: 可选模型覆盖。
        system_prompt: 可选系统提示词（本实现未使用）。
        tools: 可选工具列表。
        timeout: 可选超时秒数。

    Yields:
        StreamEvent 流。
    """
    logger.info(
        "opencode_stream_start",
        session_id=session_id,
        message_count=len(messages),
        has_mcp_token=bool(mcp_token),
        mcp_token_len=len(mcp_token) if mcp_token else 0,
    )
    session_info = adapter._sessions.get(session_id)
    if not session_info:
        logger.error("opencode_stream_session_not_found", session_id=session_id)
        yield StreamEvent.error(message=f"Session '{session_id}' not found")
        return

    agent_name = session_info.agent_name
    client = get_client(adapter, agent_name, session_info.agent_base_url)

    last_content = ""
    for msg in reversed(messages):
        if msg.role == "user":
            last_content = msg.content
            break

    import uuid
    parts = [{"type": "text", "text": last_content, "id": f"prt_{str(uuid.uuid4())[:20]}"}]

    tool_list = _resolve_tool_names(adapter, tools)

    yield StreamEvent.session(session_id=session_id, agent_name=agent_name)

    # State for event filtering / dedup.
    assistant_message_ids: set[str] = set()
    last_text: str = ""
    accumulated_text: str = ""

    opencode_payload_kwargs = dict(
        id=session_id,  # SDK param 名是 id,不是 session_id (Python kwarg 校验)
        model_id=model or session_info.model or "default",
        # providerID 必须是 opencode config.json 里 "provider" 块声明的名字.
        # 当前用 openai-compatible 接口 (OPENAI_BASE_URL 指向 minimax),
        # render_config.py 渲染出来的 config 里 provider 名是 "openai".
        # 早期这里误写成 "opencode" (opencode 自己的 brand), 会被 opencode server
        # 当成查不到的 provider → 400 Bad Request.
        provider_id="openai",
        parts=parts,
        system=_build_runtime_context(system_prompt, mcp_token),
        tools=tool_list,
        timeout=timeout,
        extra_query=_workspace_query(session_info),
    )
    log_opencode_request(build_opencode_payload(**_log_payload_kwargs(opencode_payload_kwargs)))

    try:
        # Open the SSE event subscription BEFORE firing the chat so we
        # do not miss the initial ``message.updated`` events.
        event_stream = await client.event.list()
        try:
            # Fire the chat as a background task. The opencode serve side
            # will start emitting events on the SSE stream we just opened.
            chat_task = asyncio.create_task(
                client.session.chat(**opencode_payload_kwargs)
            )

            async for event in event_stream:
                mapped = map_opencode_event(event, session_id, assistant_message_ids)
                if mapped is OPENCODE_STREAM_END:
                    break
                if mapped is None:
                    continue
                # Dedup text updates: the SDK sends the full text so far
                # on every ``message.part.updated`` for a text part.
                if mapped.type == "text":
                    text = mapped.data.get("content", "") or ""
                    if text == last_text:
                        continue
                    last_text = text
                    accumulated_text = text
                yield mapped

            # Surface any exception raised by the chat call so it is not
            # silently swallowed.
            try:
                await chat_task
            except Exception as task_err:
                logger.warning(
                    "opencode_chat_task_failed",
                    session_id=session_id,
                    error=str(task_err),
                )
                yield StreamEvent.error(message=str(task_err))
        finally:
            await event_stream.close()
    except Exception as e:
        logger.error("opencode_stream_failed", session_id=session_id, error=str(e))
        yield StreamEvent.error(message=str(e))
        return

    # Persist the final assistant text for history retrieval.
    if accumulated_text:
        try:
            await adapter._storage.create_message(StorageMessage(
                session_id=session_id,
                role="assistant",
                content=accumulated_text,
            ))
        except Exception as e:
            logger.warning(
                "opencode_stream_persist_failed",
                session_id=session_id,
                error=str(e),
            )
    logger.info("opencode_stream_completed", session_id=session_id, agent_name=agent_name)
