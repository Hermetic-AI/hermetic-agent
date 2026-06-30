"""Claude Code 适配器（薄壳）。

会话生命周期逻辑位于 ``claude_code_lifecycle.py``；对话分发逻辑位于
``claude_code_chat.py``。本模块仅作为 AgentProvider 接口的转发层。
底层 SDK 为 ``claude-agent-sdk``，本地调用 Claude Code CLI，无 HTTP。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

import structlog

from hermetic_agent.providers.base import (
    AgentProvider,
    ChatMessage,
    ChatResult,
    SDKType,
    SessionInfo,
)
from hermetic_agent.providers.claude_code import lifecycle as lc
from hermetic_agent.providers.claude_code.chat import blocking_chat, stream_chat
from hermetic_agent.providers.streaming import StreamEvent
from hermetic_agent.store.base import SessionRepository

try:
    from claude_agent_sdk import ClaudeSDKClient
except ImportError:  # pragma: no cover
    ClaudeSDKClient = None  # type: ignore

if TYPE_CHECKING:
    from hermetic_agent.mcp.registry import MCPTool

logger = structlog.get_logger(__name__)


class ClaudeCodeAdapter(AgentProvider):
    """claude-agent-sdk 适配器（本地 CLI）。

    维护每个 Agent 的 ClaudeSDKClient 实例、会话元数据以及会话到
    Agent 的反向映射；具体行为委托给 lifecycle 与 chat 模块。
    """

    provider_type: SDKType = "claude_code"

    def __init__(
        self,
        skill_registry: Any,
        mcp_registry: Any,
        storage: SessionRepository,
    ) -> None:
        """初始化适配器持有的 skill/mcp 仓库、存储与客户端缓存。

        Args:
            skill_registry: 全局技能注册中心。
            mcp_registry: MCP 工具注册中心。
            storage: 会话与消息持久化仓库。
        """
        self._skill_registry = skill_registry
        self._mcp_registry = mcp_registry
        self._storage = storage
        # Per-agent SDK clients, session metadata, and session -> agent map.
        self._clients: dict[str, ClaudeSDKClient] = {}
        self._sessions: dict[str, SessionInfo] = {}
        self._session_to_agent: dict[str, str] = {}

    async def create_session(
        self, agent_name: str, model: str | None = None, system_prompt: str | None = None,
        *, base_url: str | None = None,  # ignored for local SDK
        session_id: str | None = None,
    ) -> SessionInfo:
        """创建或恢复 Claude Code 会话。

        Args:
            agent_name: Agent 名称。
            model: 可选模型标识。
            system_prompt: 可选系统提示词。
            base_url: 本地 SDK 不使用，保留以满足接口。
            session_id: 提供时进入 resume 流程。

        Returns:
            新建或恢复的 SessionInfo。
        """
        logger.info("claude_code_session_create_start", agent_name=agent_name, has_session_id=bool(session_id))
        try:
            result = await lc.create_session(
                self, agent_name, model=model, system_prompt=system_prompt,
                base_url=base_url, session_id=session_id,
            )
        except Exception as e:
            logger.error("claude_code_session_create_failed", agent_name=agent_name, error=str(e))
            raise
        logger.info("claude_code_session_created", session_id=result.session_id, agent_name=agent_name)
        return result

    async def chat(
        self, session_id: str, messages: list[ChatMessage],
        *, model: str | None = None, system_prompt: str | None = None,
        tools: list[MCPTool] | None = None, timeout: float | None = None,
        stream: bool = False,
    ) -> ChatResult | AsyncIterator[StreamEvent]:
        """按 stream 标志选择阻塞或流式 chat 通道。

        Args:
            session_id: 目标会话 ID。
            messages: 完整消息列表。
            model: 可选模型覆盖。
            system_prompt: 可选系统提示词。
            tools: 可选 MCPTool 列表。
            timeout: 可选超时秒数。
            stream: True 时返回 StreamEvent 异步迭代器。

        Returns:
            ChatResult 或 StreamEvent 异步迭代器。
        """
        logger.info(
            "claude_code_chat_start",
            session_id=session_id,
            stream=stream,
            message_count=len(messages),
        )
        if stream:
            return stream_chat(
                self, session_id, messages, model=model, system_prompt=system_prompt,
                tools=tools, timeout=timeout,
            )
        result = await blocking_chat(
            self, session_id, messages, model=model, system_prompt=system_prompt,
            tools=tools, timeout=timeout,
        )
        logger.info("claude_code_chat_completed", session_id=session_id, success=result.success)
        return result

    async def abort(self, session_id: str) -> bool:
        """中断运行中的 Claude Code 会话。

        Args:
            session_id: 目标会话 ID。

        Returns:
            True 表示成功下发中断。
        """
        return await lc.abort(self, session_id)

    async def delete(self, session_id: str) -> bool:
        """删除会话及本地跟踪状态。

        Args:
            session_id: 目标会话 ID。

        Returns:
            True 表示成功删除。
        """
        return await lc.delete(self, session_id)

    async def get_messages(self, session_id: str) -> list[ChatMessage]:
        """读取会话历史消息。

        Args:
            session_id: 目标会话 ID。

        Returns:
            消息列表。
        """
        return await lc.get_messages(self, session_id)

    async def get_session(self, session_id: str) -> SessionInfo | None:
        """获取会话元数据。

        Args:
            session_id: 目标会话 ID。

        Returns:
            SessionInfo 或 None。
        """
        return await lc.get_session(self, session_id)

    async def health_check(self, base_url: str) -> bool:
        """检查本地 Claude CLI 是否可用。

        Args:
            base_url: 接口占位参数，本地 SDK 不使用。

        Returns:
            True 表示 CLI 可用。
        """
        return await lc.health_check(base_url)
