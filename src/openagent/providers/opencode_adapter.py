"""OpenCode 适配器（薄壳）。

会话生命周期逻辑位于 ``opencode_lifecycle.py``；对话分发逻辑位于
``opencode_chat.py``。本模块仅作为 AgentProvider 接口的转发层。
底层 SDK 为 ``opencode-ai``，通过 HTTP 与 ``opencode serve`` 通信。
"""

from __future__ import annotations

from typing import Any, AsyncIterator

import structlog

from openagent.providers import opencode_lifecycle as lc
from openagent.providers.base import (
    AgentProvider,
    ChatMessage,
    ChatResult,
    SDKType,
    SessionInfo,
)
from openagent.providers.opencode_chat import blocking_chat, stream_chat
from openagent.store.base import SessionRepository
from openagent.streaming import StreamEvent

try:
    from opencode_ai import AsyncOpencode  # type: ignore
except ImportError:  # pragma: no cover
    from openagent._vendor.opencode import AsyncOpencode  # type: ignore

logger = structlog.get_logger(__name__)


class OpenCodeAdapter(AgentProvider):
    """opencode-ai SDK 适配器（HTTP 后端）。

    缓存按 ``agent:base_url`` 索引的 AsyncOpencode 客户端实例，并维护
    会话表与会话到 Agent 的反向映射；具体行为委托给 lifecycle 与
    chat 模块。
    """

    provider_type: SDKType = "opencode"

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
        # Cached AsyncOpencode clients (key: "agent:base_url"); session tables.
        self._clients: dict[str, AsyncOpencode] = {}
        self._sessions: dict[str, SessionInfo] = {}
        self._session_to_agent: dict[str, str] = {}

    async def create_session(
        self, agent_name: str, model: str | None = None, system_prompt: str | None = None,
        *, base_url: str | None = None, session_id: str | None = None,
        directory: str | None = None,
    ) -> SessionInfo:
        """创建或恢复 OpenCode 会话。

        Args:
            agent_name: Agent 名称。
            model: 可选模型标识。
            system_prompt: 可选系统提示词。
            base_url: opencode serve 的 HTTP 入口。
            session_id: 提供时进入 resume 流程。
            directory: 会话绑定的项目工作区路径(scenario 提供)。None
                时使用 opencode serve 启动时的 --cwd。

        Returns:
            新建或恢复的 SessionInfo。
        """
        logger.info(
            "opencode_session_create_start",
            agent_name=agent_name,
            base_url=base_url,
            has_session_id=bool(session_id),
            has_directory=bool(directory),
        )
        try:
            result = await lc.create_session(
                self, agent_name, model=model, system_prompt=system_prompt,
                base_url=base_url, session_id=session_id, directory=directory,
            )
        except Exception as e:
            logger.error("opencode_session_create_failed", agent_name=agent_name, error=str(e))
            raise
        logger.info(
            "opencode_session_created",
            session_id=result.session_id,
            agent_name=agent_name,
            directory=directory,
        )
        return result

    async def chat(
        self, session_id: str, messages: list[ChatMessage],
        *, model: str | None = None, system_prompt: str | None = None,
        tools: list[Any] | None = None, timeout: float | None = None,
        stream: bool = False,
    ) -> ChatResult | AsyncIterator[StreamEvent]:
        """按 stream 标志选择阻塞或流式 chat 通道。

        Args:
            session_id: 目标会话 ID。
            messages: 完整消息列表。
            model: 可选模型覆盖。
            system_prompt: 可选系统提示词。
            tools: 可选工具列表。
            timeout: 可选超时秒数。
            stream: True 时返回 StreamEvent 异步迭代器。

        Returns:
            ChatResult 或 StreamEvent 异步迭代器。
        """
        logger.info(
            "opencode_chat_start",
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
        logger.info("opencode_chat_completed", session_id=session_id, success=result.success)
        return result

    async def abort(self, session_id: str) -> bool:
        """中断运行中的 OpenCode 会话。

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
        """检查 opencode serve 后端是否可达。

        Args:
            base_url: opencode serve 的 HTTP 入口。

        Returns:
            True 表示后端健康。
        """
        return await lc.health_check(base_url)
