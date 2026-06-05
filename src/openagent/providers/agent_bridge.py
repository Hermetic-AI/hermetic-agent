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
        *,
        directory: str | None = None,
    ) -> SessionInfo:
        """Create session via correct adapter.

        Args:
            agent_name: 目标 Agent 名称。
            model: 可选模型标识。
            system_prompt: 可选系统提示词。
            directory: 会话绑定的项目工作区路径(由 scenario 提供)。
                opencode adapter 会透传到 server 的 WorkspaceRouting
                middleware,实现 session 级别的工作区隔离。
        """
        adapter = self.get_provider(agent_name)
        config = self._agents[agent_name]
        session_info = await adapter.create_session(
            agent_name=agent_name,
            model=model,
            system_prompt=system_prompt,
            base_url=config.base_url,
            directory=directory,
        )
        self._session_to_agent[session_info.session_id] = agent_name
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
        mcp_token: str | None = None,
        # --- 渐进式 SKILL 加载 (P0-1 新增, 全部可选, 不破坏既有 caller) ---
        prompt_builder: Any = None,
        scenario: Any = None,
        current_state: str | None = None,
    ) -> ChatResult | AsyncIterator[Any]:
        """Route chat to the adapter that owns this session.

        Args:
            session_id: 目标会话 ID。
            messages: 完整消息列表。
            model: 可选模型覆盖。
            system_prompt: 可选系统提示词。
            skills: 可选 skill 名称列表(经白名单过滤后注入)。
            tools: 可选 MCP 工具名称列表(经白名单过滤后下发)。
            timeout: 可选超时秒数。
            stream: True 时返回 AsyncIterator[StreamEvent]。
            mcp_token: per-request MCP 认证 token;由 routes._extract_mcp_token 从
                chat header(X-MCP-Token / Authorization: Bearer)提取,
                最终注入到 system_prompt 的 <runtime-context> 块让 LLM 自己填入
                MCP 调用的 header。None = 当前请求无 token。
            prompt_builder: 可选 ``skill_runtime.PromptBuilder``。若提供且
                ``scenario`` 非 None, 走新 P6 渐进式加载路径; 否则降级到
                下方 ``build_system_prompt_with_skills`` 的旧全量内联路径.
            scenario: 可选 ScenarioConfig (duck-typed). 与 prompt_builder
                一起用; 单独传会被忽略.
            current_state: 当前 state id; ``on_demand`` / ``explicit`` 策略
                用来选 load_on_state 段; None 时回退 "S01".
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
            has_prompt_builder=prompt_builder is not None,
            has_scenario=scenario is not None,
        )

        # --- Skill 注入: 渐进式 (P6) > 旧全量 (向后兼容) ---
        if prompt_builder is not None and scenario is not None:
            # P1-3: 在 system_prompt 顶部 prepend 一次 metadata 列表 (L1).
            # LLM 据此知道"哪些 skill 可用 + 何时该调 read_skill 加载完整内容".
            # 列表只显示 scenario 白名单内的 skill (与 injector 的 final_skills
            # 一致), 避免泄漏未授权的 skill.
            if self._skill_registry is not None:
                allowed = getattr(
                    getattr(scenario, "execution", None), "skills", []
                ) or []
                metadata_block = self._skill_registry.metadata_list(allowed)
                if metadata_block:
                    system_prompt = metadata_block + "\n\n" + (system_prompt or "")

            # 新路径: 由 PromptBuilder 根据 scenario.progressive_skill.strategy
            # 决定加载哪些 skill 片段 (none / all / on_demand / explicit).
            state_id = current_state or "S01"
            try:
                skill_section, report = prompt_builder.render_skill_section(
                    scenario, state_id
                )
                if skill_section:
                    system_prompt = (system_prompt or "") + "\n\n" + skill_section
                logger.info(
                    "skills_loaded_via_prompt_builder",
                    session_id=session_id,
                    scenario=getattr(scenario, "name", None),
                    state=state_id,
                    loaded=report.loaded,
                    total_tokens=report.total_tokens,
                )
            except Exception as e:
                # PromptBuilder 抛异常不能阻塞整个 chat; 降级到旧路径
                logger.warning(
                    "prompt_builder_failed_falling_back",
                    session_id=session_id,
                    error=str(e),
                )
                if skills and self._skill_registry:
                    system_prompt, _missing = (
                        self._skill_registry.build_system_prompt_with_skills(
                            system_prompt or "", skills
                        )
                    )
        elif skills and self._skill_registry:
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
                mcp_token=mcp_token,
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
