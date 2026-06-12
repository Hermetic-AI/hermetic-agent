"""ChatStepService — single chat-step executor.

Encapsulates the "select agent → create session → build ChatMessage → chat →
wrap into TaskResult" boilerplate that used to be duplicated in
`Scheduler.run`, `Scheduler.run_chain`, and `Scheduler.run_in_session`.
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from openagent.core.task_result import TaskResult
from openagent.providers.agent_bridge import AgentBridge
from openagent.providers.base import ChatMessage

logger = structlog.get_logger(__name__)


class ChatStepService:
    """在 AgentBridge 上执行单次 chat 步骤并组装结果。

    负责：选择 Agent、创建（或复用）会话、构造 ChatMessage、调用 chat、
    把返回结果包成 ``TaskResult``。失败路径统一走 ``_failure`` 静态方法，
    负责结构化错误日志与失败 DTO。
    """

    def __init__(self, bridge: AgentBridge) -> None:
        """绑定底层的 AgentBridge。

        Args:
            bridge: 用于调用 SDK 的桥接对象。
        """
        self._bridge = bridge

    async def select_agent(self, agent_name: str | None) -> tuple[str | None, TaskResult | None]:
        """选择本次步骤要使用的 Agent。

        Args:
            agent_name: 显式指定的 Agent 名；为空则取桥接器中的第一个。

        Returns:
            ``(name, None)`` 表示选 Agent 成功；``(None, error_result)`` 表示
            选 Agent 失败（没有注册 Agent，或指定名称不存在）。
        """
        agents = self._bridge.list_agents()
        if not agents:
            logger.error("select_agent_failed", reason="no_agents_registered")
            return None, TaskResult(success=False, error="No agents registered")
        if agent_name:
            if agent_name not in agents:
                logger.error(
                    "select_agent_failed",
                    reason="agent_not_found",
                    agent_name=agent_name,
                )
                return None, TaskResult(success=False, error=f"Agent '{agent_name}' not found")
            return agent_name, None
        return next(iter(agents)), None

    async def execute(
        self,
        prompt: str,
        agent_name: str | None = None,
        *,
        model: str | None = None,
        system_prompt: str | None = None,
        skills: list[str] | None = None,
        tools: list[str] | None = None,
        timeout: float | None = None,
        existing_session_id: str | None = None,
    ) -> TaskResult:
        """执行一次 chat 步骤并返回 ``TaskResult``。

        Args:
            prompt: 用户提示词。
            agent_name: 指定 Agent 名；为空则自动选择。
            model: 覆盖默认模型。
            system_prompt: 额外的系统提示词。
            skills: 要注入的技能名列表。
            tools: 要启用的 MCP 工具名列表。
            timeout: chat 超时秒数。
            existing_session_id: 若提供则复用此会话，跳过创建新会话。

        Returns:
            任务执行结果。成功时 ``success=True`` 且 ``result`` 为模型回复内容；
            失败时 ``success=False`` 且 ``error`` 为错误描述。
        """
        start = time.time()
        logger.info("task_execute_start", agent_name=agent_name, prompt_length=len(prompt or ""))
        instance_name, err = await self.select_agent(agent_name)
        if err is not None:
            logger.error("task_failed", agent_name=agent_name, reason="select_agent_failed")
            return err

        session_id = existing_session_id
        session_info: Any = None
        if session_id is None:
            try:
                session_info = await self._bridge.create_session(agent_name=instance_name)
                session_id = session_info.session_id
            except Exception as e:
                return self._failure(instance_name, session_id, e, start)

        try:
            message = ChatMessage(role="user", content=prompt)
            chat_result = await self._bridge.chat(
                session_id=session_id,
                messages=[message],
                model=model,
                system_prompt=system_prompt,
                skills=skills,
                tools=tools,
                timeout=timeout,
            )
        except Exception as e:
            return self._failure(instance_name, session_id, e, start)

        duration = time.time() - start
        logger.info(
            "task_completed",
            agent_name=instance_name,
            session_id=session_id,
            duration=duration,
        )
        return TaskResult(
            success=True,
            result=chat_result.message.content if chat_result.message else None,
            agent_name=instance_name,
            session_id=session_id,
            duration=duration,
        )

    @staticmethod
    def _failure(
        agent_name: str | None,
        session_id: str | None,
        exc: Exception,
        start: float,
    ) -> TaskResult:
        """统一的失败处理：记录错误日志并返回失败 DTO。"""
        duration = time.time() - start
        logger.error(
            "task_failed",
            agent_name=agent_name,
            session_id=session_id,
            error=str(exc),
            duration=duration,
        )
        return TaskResult(
            success=False,
            error=str(exc),
            agent_name=agent_name,
            session_id=session_id,
            duration=duration,
        )
