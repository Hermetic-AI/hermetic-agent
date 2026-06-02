"""Agent bridge — routes to the correct SDK adapter based on agent config."""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

import structlog

from openagent.providers.base import (
    AgentConfig,
    AgentProvider,
    ChatMessage,
    ChatResult,
    SDKType,
    SessionInfo,
)
from openagent.providers.claude_code_adapter import ClaudeCodeAdapter
from openagent.providers.opencode_adapter import OpenCodeAdapter
from openagent.store.base import SessionRepository

logger = structlog.get_logger(__name__)


class AgentBridge:
    """统一的 Agent 代理——根据 AgentConfig.sdk_type 路由到对应适配器。

    负责 Skill 注入、工具解析与会话到 Agent 的反向查找；对上层屏蔽
    OpenCode 与 Claude Code 两种 SDK 的差异。
    """

    def __init__(
        self,
        skill_registry: Any,
        mcp_registry: Any,
        storage: SessionRepository,
    ) -> None:
        """初始化桥接器，持有 skill/mcp 仓库与持久化层。

        Args:
            skill_registry: 全局技能注册中心，用于在 chat 时注入提示词。
            mcp_registry: MCP 工具注册中心，用于按名称解析工具对象。
            storage: 会话与消息的持久化仓库。
        """
        self._skill_registry = skill_registry
        self._mcp_registry = mcp_registry
        self._storage = storage
        self._providers: dict[str, AgentProvider] = {}
        self._agents: dict[str, AgentConfig] = {}
        self._session_to_agent: dict[str, str] = {}

    # -------------------------------------------------------------------------
    # Registration
    # -------------------------------------------------------------------------

    def register(self, config: AgentConfig) -> None:
        """注册一个 Agent 并按 sdk_type 实例化对应适配器。

        Args:
            config: Agent 配置，含名称、入口、SDK 类型等。

        Raises:
            ValueError: 当 sdk_type 不在支持列表中时。
        """
        logger.info("agent_register_start", name=config.name, sdk_type=config.sdk_type)
        if config.sdk_type == "opencode":
            adapter: AgentProvider = OpenCodeAdapter(
                skill_registry=self._skill_registry,
                mcp_registry=self._mcp_registry,
                storage=self._storage,
            )
        elif config.sdk_type == "claude_code":
            adapter = ClaudeCodeAdapter(
                skill_registry=self._skill_registry,
                mcp_registry=self._mcp_registry,
                storage=self._storage,
            )
        else:
            logger.error("agent_register_failed", name=config.name, sdk_type=config.sdk_type)
            raise ValueError(f"Unsupported sdk_type: {config.sdk_type}")

        self._providers[config.name] = adapter
        self._agents[config.name] = config
        logger.info("agent_registered", name=config.name, sdk_type=config.sdk_type)

    def get_provider(self, agent_name: str) -> AgentProvider:
        """按 Agent 名称获取对应适配器。

        Args:
            agent_name: Agent 名称。

        Returns:
            已注册的 AgentProvider 实例。

        Raises:
            KeyError: Agent 未注册时。
        """
        if agent_name not in self._providers:
            raise KeyError(f"Agent '{agent_name}' not registered")
        return self._providers[agent_name]

    def get_config(self, agent_name: str) -> AgentConfig:
        """按名称获取 Agent 配置。

        Args:
            agent_name: Agent 名称。

        Returns:
            对应的 AgentConfig。
        """
        return self._agents[agent_name]

    def list_agents(self) -> dict[str, AgentConfig]:
        """返回当前注册的所有 Agent 配置的浅拷贝。

        Returns:
            Agent 名称到 AgentConfig 的字典。
        """
        return dict(self._agents)

    # -------------------------------------------------------------------------
    # Session routing
    # -------------------------------------------------------------------------

    async def create_session(
        self,
        agent_name: str,
        model: str | None = None,
        system_prompt: str | None = None,
        session_id: str | None = None,
    ) -> SessionInfo:
        """通过对应适配器创建或恢复会话。

        Args:
            agent_name: Agent 名称。
            model: 可选模型标识。
            system_prompt: 可选系统提示词。
            session_id: 提供时进入 resume 流程。

        Returns:
            新建或恢复的 SessionInfo。
        """
        logger.info("session_create_start", agent_name=agent_name, has_session_id=bool(session_id))
        adapter = self.get_provider(agent_name)
        config = self._agents[agent_name]
        session_info = await adapter.create_session(
            agent_name=agent_name,
            model=model,
            system_prompt=system_prompt,
            base_url=config.base_url,
            session_id=session_id,
        )
        self._session_to_agent[session_info.session_id] = agent_name
        logger.info("session_created", session_id=session_info.session_id, agent_name=agent_name)
        return session_info

    def get_agent_for_session(self, session_id: str) -> str | None:
        """返回拥有指定会话的 Agent 名称。

        Args:
            session_id: 会话 ID。

        Returns:
            Agent 名称或 None（未找到时）。
        """
        return self._session_to_agent.get(session_id)

    async def chat(
        self,
        session_id: str,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        system_prompt: str | None = None,
        skills: list[str] | None = None,
        tools: list[str] | None = None,
        timeout: float | None = None,
        stream: bool = False,
    ) -> ChatResult | AsyncIterator[Any]:
        """将对话请求路由到所属会话对应的适配器。

        在转发前会注入技能到系统提示词，并将工具名解析为 MCPTool 对象。

        Args:
            session_id: 目标会话 ID。
            messages: 完整消息列表。
            model: 可选模型覆盖。
            system_prompt: 基础系统提示词。
            skills: 可选技能名称列表，会被拼接到系统提示词。
            tools: 可选工具名称列表，会被解析为 MCPTool 对象。
            timeout: 可选超时秒数。
            stream: True 时走流式通道。

        Returns:
            非流式返回 ChatResult；流式返回 StreamEvent 异步迭代器。

        Raises:
            ValueError: 会话 ID 未知时。
        """
        agent_name = self._session_to_agent.get(session_id)
        if not agent_name:
            logger.error("chat_session_not_found", session_id=session_id)
            raise ValueError(f"Session '{session_id}' not found")

        logger.info(
            "chat_start",
            session_id=session_id,
            agent_name=agent_name,
            stream=stream,
            skill_count=len(skills) if skills else 0,
            tool_count=len(tools) if tools else 0,
        )

        # Inject skills into system prompt
        if skills and self._skill_registry:
            system_prompt, _missing = self._skill_registry.build_system_prompt_with_skills(
                system_prompt or "", skills
            )
            logger.info(
                "skills_injected_into_prompt",
                session_id=session_id,
                skill_count=len(skills),
            )

        # Resolve tools to MCPTool objects
        mcp_tools = None
        if tools and self._mcp_registry:
            mcp_tools = self._mcp_registry.list_all_by_names(tools)

        adapter = self.get_provider(agent_name)
        try:
            result = await adapter.chat(
                session_id=session_id,
                messages=messages,
                model=model,
                system_prompt=system_prompt,
                tools=mcp_tools,
                timeout=timeout,
                stream=stream,
            )
        except Exception as e:
            logger.error("chat_failed", session_id=session_id, agent_name=agent_name, error=str(e))
            raise
        logger.info("chat_completed", session_id=session_id, agent_name=agent_name)
        return result

    async def abort(self, session_id: str) -> bool:
        """将 abort 请求路由到对应适配器。

        Args:
            session_id: 目标会话 ID。

        Returns:
            适配器返回的 abort 结果；会话不存在时返回 False。
        """
        agent_name = self._session_to_agent.get(session_id)
        if not agent_name:
            return False
        adapter = self.get_provider(agent_name)
        return await adapter.abort(session_id)

    async def delete(self, session_id: str) -> bool:
        """删除会话并清理桥接器内部的会话到 Agent 映射。

        Args:
            session_id: 目标会话 ID。

        Returns:
            适配器返回的删除结果；会话不存在时返回 False。
        """
        agent_name = self._session_to_agent.pop(session_id, None)
        if not agent_name:
            return False
        adapter = self.get_provider(agent_name)
        return await adapter.delete(session_id)

    async def get_messages(self, session_id: str) -> list[ChatMessage]:
        """将会话消息查询路由到对应适配器。

        Args:
            session_id: 目标会话 ID。

        Returns:
            消息列表；会话不存在时返回空列表。
        """
        agent_name = self._session_to_agent.get(session_id)
        if not agent_name:
            return []
        adapter = self.get_provider(agent_name)
        return await adapter.get_messages(session_id)

    async def get_session(self, session_id: str) -> SessionInfo | None:
        """将会话元数据查询路由到对应适配器。

        Args:
            session_id: 目标会话 ID。

        Returns:
            SessionInfo 或 None（会话不存在时）。
        """
        agent_name = self._session_to_agent.get(session_id)
        if not agent_name:
            return None
        adapter = self.get_provider(agent_name)
        return await adapter.get_session(session_id)

    async def health_check(self, base_url: str) -> bool:
        """对所有已注册适配器依次执行健康检查。

        Args:
            base_url: Agent HTTP 入口；本地适配器通常忽略。

        Returns:
            仅当所有适配器都报告健康时为 True。
        """
        for adapter in self._providers.values():
            try:
                ok = await adapter.health_check(base_url)
                if not ok:
                    return False
            except Exception as e:
                logger.warning("health_check_failed", error=str(e))
                return False
        return True
