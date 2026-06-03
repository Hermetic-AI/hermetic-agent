"""Provider 抽象接口与基础数据模型。

定义 AgentProvider 抽象基类（所有 SDK 适配器必须实现）以及适配层共用的
不可变数据模型（ChatMessage、ChatResult、SessionInfo、AgentConfig 等）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal

SDKType = Literal["opencode", "claude_code"]


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ChatMessage:
    """单条对话消息。

    表示用户、助手或工具之间的交换内容；可携带工具调用上下文。
    """
    role: str
    content: str
    tool_call_id: str | None = None
    tool_name: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class ToolCall:
    """对话中由模型发起的工具调用记录。"""
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class ChatResult:
    """一次 chat 调用的统一结果。

    包含成功标志、助手回复、所属会话、停止原因以及可选的工具调用列表与
    错误信息；调用方通过 success 字段判断业务成败。
    """
    success: bool
    message: ChatMessage
    session_id: str
    agent_name: str
    stop_reason: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    duration: float | None = None
    error: str | None = None


@dataclass
class SessionInfo:
    """由 Hub 维护的会话元数据。

    记录会话 ID、所属 Agent、Agent HTTP 入口以及可选的模型与创建时间。
    """
    session_id: str
    agent_name: str
    agent_base_url: str
    model: str | None = None
    created_at: float | None = None
    directory: str | None = None


@dataclass
class AgentConfig:
    """已注册 Agent 的配置信息。

    包含 Agent 名称、入口 URL、SDK 类型、鉴权信息、默认模型/技能/工具
    以及能力标签。
    """
    name: str
    base_url: str
    sdk_type: SDKType
    api_key: str | None = None
    username: str | None = None
    password: str | None = None
    default_model: str | None = None
    default_skills: list[str] = field(default_factory=list)
    default_tools: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Abstract provider
# ---------------------------------------------------------------------------


class AgentProvider(ABC):
    """所有 SDK 适配器必须实现的抽象基类。

    暴露统一的会话生命周期与对话接口（create_session / chat / abort /
    delete / get_* / health_check），由 AgentBridge 按 sdk_type 路由到
    具体实现。
    """

    @property
    @abstractmethod
    def provider_type(self) -> SDKType:
        """返回适配器对应的 SDK 类型，取值为 "opencode" 或 "claude_code"。"""
        ...

    @abstractmethod
    async def create_session(
        self,
        agent_name: str,
        model: str | None = None,
        system_prompt: str | None = None,
        *,
        base_url: str | None = None,
        session_id: str | None = None,
    ) -> SessionInfo:
        """创建新会话；若提供 session_id 则尝试恢复已有会话。

        Args:
            agent_name: 已注册 Agent 的名称。
            model: 可选的模型标识，为空时由实现方决定。
            system_prompt: 可选的初始系统提示词。
            base_url: 解析后的 Agent HTTP 入口，HTTP 适配器必填，本地
                适配器可忽略。
            session_id: 可选；提供时进入 resume 流程。

        Returns:
            新建或恢复的 SessionInfo。
        """
        ...

    @abstractmethod
    async def chat(
        self,
        session_id: str,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        system_prompt: str | None = None,
        tools: list[Any] | None = None,
        timeout: float | None = None,
        stream: bool = False,
    ) -> ChatResult | AsyncIterator[Any]:
        """向指定会话发送消息并获取回复。

        Args:
            session_id: 目标会话 ID。
            messages: 完整的消息列表。
            model: 可选模型覆盖。
            system_prompt: 可选系统提示词。
            tools: 可用工具列表。
            timeout: 可选超时秒数。
            stream: True 时返回 StreamEvent 异步迭代器。

        Returns:
            非流式时返回 ChatResult；流式时返回 StreamEvent 异步迭代器。
        """
        ...

    @abstractmethod
    async def abort(self, session_id: str) -> bool:
        """中断正在运行的会话。

        Args:
            session_id: 目标会话 ID。

        Returns:
            True 表示中断已下发；False 表示会话不存在或不支持。
        """
        ...

    @abstractmethod
    async def delete(self, session_id: str) -> bool:
        """删除会话并清理相关资源。

        Args:
            session_id: 目标会话 ID。

        Returns:
            True 表示成功删除；False 表示会话不存在。
        """
        ...

    @abstractmethod
    async def get_messages(self, session_id: str) -> list[ChatMessage]:
        """获取会话的完整消息历史。

        Args:
            session_id: 目标会话 ID。

        Returns:
            按时间顺序排列的消息列表；会话不存在时返回空列表。
        """
        ...

    @abstractmethod
    async def get_session(self, session_id: str) -> SessionInfo | None:
        """获取会话元数据。

        Args:
            session_id: 目标会话 ID。

        Returns:
            SessionInfo 或 None（会话不存在时）。
        """
        ...

    @abstractmethod
    async def health_check(self, base_url: str) -> bool:
        """检查适配器后端是否可达。

        Args:
            base_url: Agent HTTP 入口；本地适配器可忽略。

        Returns:
            True 表示健康。
        """
        ...
