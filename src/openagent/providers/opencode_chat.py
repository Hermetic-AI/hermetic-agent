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
    logger.info("opencode_chat_start", session_id=session_id, message_count=len(messages))
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

    # Convert tools (callers pass MCPTool objects, not raw dicts)
    tool_list = None
    if tools:
        tool_list = adapter._mcp_registry.to_opencode_format([t.name for t in tools])

    try:
        result = await client.session.chat(
            session_id,
            model_id=model or session_info.model or "default",
            provider_id="opencode",
            parts=parts,
            system=system_prompt,
            tools=tool_list,
            timeout=timeout,
            **_workspace_query(session_info),
        )
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
    logger.info("opencode_stream_start", session_id=session_id, message_count=len(messages))
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

    tool_list = None
    if tools:
        tool_list = adapter._mcp_registry.to_opencode_format([t.name for t in tools])

    yield StreamEvent.session(session_id=session_id, agent_name=agent_name)

    # State for event filtering / dedup.
    assistant_message_ids: set[str] = set()
    last_text: str = ""
    accumulated_text: str = ""

    try:
        # Open the SSE event subscription BEFORE firing the chat so we
        # do not miss the initial ``message.updated`` events.
        event_stream = await client.event.list()
        try:
            # Fire the chat as a background task. The opencode serve side
            # will start emitting events on the SSE stream we just opened.
            chat_task = asyncio.create_task(
                client.session.chat(
                    session_id,
                    model_id=model or session_info.model or "default",
                    provider_id="opencode",
                    parts=parts,
                    system=system_prompt,
                    tools=tool_list,
                    timeout=timeout,
                    **_workspace_query(session_info),
                )
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
