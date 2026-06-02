"""Claude Code 适配器的对话分发。

模块级函数以适配器实例作为第一个参数以便读取其内部状态；这些函数是
``claude_code_adapter.py`` 类的具体实现，负责 SDK 选项构造、消息内容
抽取以及 SDK 事件到 ``StreamEvent`` 的映射。
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any, AsyncIterator

import structlog

from openagent.mcp.registry import MCPTool
from openagent.providers.base import (
    AgentConfig,
    ChatMessage,
    ChatResult,
)
from openagent.store.base import Message as StorageMessage
from openagent.streaming import StreamEvent

try:
    from claude_agent_sdk import (
        ClaudeAgentOptions,
        ClaudeSDKClient,
        ResultMessage,
    )
    from claude_agent_sdk import StreamEvent as SDKStreamEvent
    from claude_agent_sdk.types import (
        AssistantMessage,
        RateLimitEvent,
        TextBlock,
        ThinkingBlock,
        ToolResultBlock,
        ToolUseBlock,
        UserMessage,
    )
except ImportError:  # pragma: no cover
    ClaudeAgentOptions = None  # type: ignore
    ClaudeSDKClient = None  # type: ignore
    ResultMessage = None  # type: ignore
    SDKStreamEvent = None  # type: ignore
    AssistantMessage = None  # type: ignore
    TextBlock = None  # type: ignore
    ThinkingBlock = None  # type: ignore
    ToolResultBlock = None  # type: ignore
    ToolUseBlock = None  # type: ignore
    RateLimitEvent = None  # type: ignore
    UserMessage = None  # type: ignore

if TYPE_CHECKING:
    from openagent.providers.claude_code_adapter import ClaudeCodeAdapter

logger = structlog.get_logger(__name__)


# SDK plumbing helpers

def build_options(
    adapter: "ClaudeCodeAdapter",
    config: AgentConfig,
    system_prompt: str | None,
    tools: list[dict[str, Any]] | None,
) -> ClaudeAgentOptions:
    """根据 AgentConfig 与运行时参数构造 ClaudeAgentOptions。

    注意：``config.base_url`` 故意不映射到 ``cli_path``——前者是 Agent
    HTTP 入口，后者是 CLI 二进制路径；需要自定义 CLI 时请显式设置
    ``cli_path``。

    Args:
        adapter: 适配器实例（当前未使用，预留扩展）。
        config: Agent 配置。
        system_prompt: 可选系统提示词。
        tools: 可选 Claude Code 格式的工具列表。

    Returns:
        构造好的 ClaudeAgentOptions。

    Raises:
        RuntimeError: 当 claude-agent-sdk 导入失败时。
    """
    if ClaudeAgentOptions is None:
        logger.error("claude_agent_sdk_not_imported")
        raise RuntimeError(
            "claude-agent-sdk failed to import at startup. "
            "Reinstall with: pip install git+https://github.com/anthropics/claude-agent-sdk-python"
        )
    opts: dict[str, Any] = {
        "model": config.default_model or "claude-sonnet-4-20250514",
    }
    if system_prompt:
        opts["system_prompt"] = system_prompt
    if tools:
        opts["tools"] = tools
    # NOTE: `config.base_url` is intentionally NOT mapped to `cli_path`:
    # `cli_path` is the CLI binary path; `base_url` is the agent's HTTP
    # endpoint. Operators needing a custom CLI should set `cli_path`
    # explicitly. See commit history for the conflation incident.
    return ClaudeAgentOptions(**opts)


async def get_or_create_client(
    adapter: "ClaudeCodeAdapter",
    config: AgentConfig,
) -> ClaudeSDKClient:
    """获取或创建指定 Agent 的 ClaudeSDKClient（首次会主动连接）。

    Args:
        adapter: 适配器实例，作为客户端缓存的宿主。
        config: Agent 配置，用于构造首次连接时的 options。

    Returns:
        已连接（首次调用后）的 ClaudeSDKClient。
    """
    if config.name not in adapter._clients:
        logger.info("claude_code_client_create_start", agent_name=config.name)
        opts = build_options(adapter, config, None, None)
        client = ClaudeSDKClient(options=opts)
        await client.connect()  # required before query()/receive_response()
        adapter._clients[config.name] = client
        logger.info("claude_code_client_created", agent_name=config.name)
    return adapter._clients[config.name]


def extract_text(content: Any) -> str:
    """从 SDK 内容块列表/对象中提取纯文本。

    Args:
        content: SDK 返回的内容，可以是字符串、TextBlock 列表或任意对象。

    Returns:
        拼接后的纯文本字符串。
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            b.text if isinstance(b, TextBlock)
            else b if isinstance(b, str)
            else getattr(b, "text", "")
            for b in content
        )
    if hasattr(content, "text"):
        return content.text
    return str(content)


# Chat dispatch

async def blocking_chat(
    adapter: "ClaudeCodeAdapter",
    session_id: str,
    messages: list[ChatMessage],
    *,
    model: str | None = None,
    system_prompt: str | None = None,
    tools: list[MCPTool] | None = None,
    timeout: float | None = None,
) -> ChatResult:
    """阻塞式 chat——收集所有事件后返回最终结果。

    Args:
        adapter: 适配器实例。
        session_id: 目标会话 ID。
        messages: 完整消息列表。
        model: 可选模型覆盖。
        system_prompt: 可选系统提示词。
        tools: 可选 MCPTool 列表。
        timeout: 可选超时秒数（本实现未使用，保留以满足接口）。

    Returns:
        ChatResult，包含助手回复与可能的错误信息。

    Raises:
        ValueError: 会话 ID 未知时。
    """
    logger.info("claude_code_chat_start", session_id=session_id, message_count=len(messages))
    session_info = adapter._sessions.get(session_id)
    if not session_info:
        logger.error("claude_code_chat_session_not_found", session_id=session_id)
        raise ValueError(f"Session '{session_id}' not found")

    agent_name = session_info.agent_name
    config = AgentConfig(
        name=agent_name,
        base_url="local",
        sdk_type="claude_code",
        default_model=model or session_info.model,
    )
    client = await get_or_create_client(adapter, config)

    # Build prompt from messages (last user message)
    last_user_msg = ""
    for msg in reversed(messages):
        if msg.role == "user":
            last_user_msg = msg.content
            break

    # Build options
    tool_names = [t.name for t in tools] if tools else None
    opts = build_options(
        adapter,
        config,
        system_prompt,
        adapter._mcp_registry.to_claude_code_format(tool_names) if tool_names else None,
    )
    if session_info.session_id:
        opts = replace(opts, resume=session_info.session_id)

    result_message: ResultMessage | None = None
    assistant_content = ""

    try:
        # Correct SDK pattern: query() (await) then receive_response() (async for)
        await client.query(prompt=last_user_msg, session_id=session_id)
        async for event in client.receive_response():
            if isinstance(event, ResultMessage):
                result_message = event
                assistant_content = extract_text(event.result)
            elif isinstance(event, AssistantMessage):
                assistant_content = extract_text(event.content)
            elif isinstance(event, SDKStreamEvent):
                pass  # handle sub-events if needed

        await adapter._storage.create_message(StorageMessage(
            session_id=session_id, role="user", content=last_user_msg,
        ))
        if assistant_content:
            await adapter._storage.create_message(StorageMessage(
                session_id=session_id, role="assistant", content=assistant_content,
            ))

        logger.info(
            "claude_code_chat_completed",
            session_id=session_id,
            agent_name=agent_name,
            has_result=result_message is not None,
        )
        return ChatResult(
            success=True,
            message=ChatMessage(role="assistant", content=assistant_content),
            stop_reason=result_message.stop_reason if result_message else None,
            session_id=session_id,
            agent_name=agent_name,
            duration=None,
        )
    except Exception as e:
        logger.error("claude_code_chat_failed", session_id=session_id, error=str(e))
        return ChatResult(
            success=False,
            message=ChatMessage(role="assistant", content=""),
            error=str(e),
            session_id=session_id,
            agent_name=agent_name,
        )


async def stream_chat(
    adapter: "ClaudeCodeAdapter",
    session_id: str,
    messages: list[ChatMessage],
    *,
    model: str | None = None,
    system_prompt: str | None = None,
    tools: list[MCPTool] | None = None,
    timeout: float | None = None,
) -> AsyncIterator[StreamEvent]:
    """流式 chat——按到达顺序 yield StreamEvent。

    Args:
        adapter: 适配器实例。
        session_id: 目标会话 ID。
        messages: 完整消息列表。
        model: 可选模型覆盖。
        system_prompt: 可选系统提示词。
        tools: 可选 MCPTool 列表。
        timeout: 可选超时秒数（本实现未使用）。

    Yields:
        StreamEvent，包含 session/text/reasoning/tool_use/tool_result/done/error。

    Raises:
        ValueError: 会话 ID 未知时。
    """
    logger.info("claude_code_stream_start", session_id=session_id, message_count=len(messages))
    session_info = adapter._sessions.get(session_id)
    if not session_info:
        logger.error("claude_code_stream_session_not_found", session_id=session_id)
        raise ValueError(f"Session '{session_id}' not found")

    agent_name = session_info.agent_name
    config = AgentConfig(
        name=agent_name,
        base_url="local",
        sdk_type="claude_code",
        default_model=model or session_info.model,
    )
    client = await get_or_create_client(adapter, config)

    # Build prompt
    last_user_msg = ""
    for msg in reversed(messages):
        if msg.role == "user":
            last_user_msg = msg.content
            break

    yield StreamEvent.session(session_id=session_id, agent_name=agent_name)

    try:
        # Correct SDK pattern: query() (await) then receive_response() (async for)
        await client.query(prompt=last_user_msg, session_id=session_id)
        async for event in client.receive_response():
            for se in map_sdk_event(event):
                yield se
    except Exception as e:
        logger.error("claude_code_stream_failed", session_id=session_id, error=str(e))
        yield StreamEvent.error(message=str(e))


def map_sdk_event(event: Any) -> AsyncIterator[StreamEvent]:
    """将 SDK 事件映射为一个或多个统一的 StreamEvent。

    Args:
        event: 来自 ``client.receive_response()`` 的 SDK 事件。

    Yields:
        对应类型的 StreamEvent（text/reasoning/tool_use/tool_result/done/error）。
    """
    if isinstance(event, SDKStreamEvent):
        # SDK sub-event
        content = getattr(event, "content", None)
        if content:
            yield StreamEvent.text(content=str(content))
        reasoning = getattr(event, "thinking", None)
        if reasoning:
            yield StreamEvent.reasoning(content=str(reasoning))
        parent_id = getattr(event, "parent_tool_use_id", None)
        if parent_id:
            yield StreamEvent.tool_result(
                tool_name=str(parent_id),
                output=str(content) if content else "",
            )

    elif isinstance(event, AssistantMessage):
        # Assistant message with content blocks
        content = event.content
        if isinstance(content, list):
            for block in content:
                if isinstance(block, TextBlock):
                    yield StreamEvent.text(content=block.text)
                elif isinstance(block, ThinkingBlock):
                    yield StreamEvent.reasoning(content=block.thinking)
                elif isinstance(block, ToolUseBlock):
                    yield StreamEvent.tool_use(
                        tool_name=block.name,
                        input_data=block.input or {},
                        tool_call_id=block.id,
                    )
                elif isinstance(block, ToolResultBlock):
                    yield StreamEvent.tool_result(
                        tool_name=block.tool_use_id,
                        output=block.content or "",
                    )
        elif isinstance(content, str) and content:
            yield StreamEvent.text(content=content)

    elif isinstance(event, ResultMessage):
        # Final result
        text = extract_text(event.result)
        if text:
            yield StreamEvent.text(content=text)
        reason = getattr(event, "stop_reason", None)
        yield StreamEvent.done(stop_reason=reason or "end_turn")

    elif isinstance(event, UserMessage):
        # Echo user message
        content = extract_text(event.content)
        if content:
            yield StreamEvent.text(content=content)

    elif isinstance(event, RateLimitEvent):
        yield StreamEvent.error(message=f"Rate limit: {event}")
