"""Task Scheduler Service - 任务调度服务

编排任务与 Agent 实例的映射关系，支持单任务、并行、顺序任务链与指定会话续跑。

Shared "select agent → create session → chat → wrap result" boilerplate lives
in `core.services.chat_step_service.ChatStepService`. This module is the
orchestrator (parallel / chain / single-shot / in-session).
"""

from __future__ import annotations

import asyncio
import time

import structlog

from hermetic_agent.core.services.chat_step_service import ChatStepService
from hermetic_agent.core.task_result import TaskResult
from hermetic_agent.mcp.registry import MCPRegistry
from hermetic_agent.providers.agent_bridge import AgentBridge
from hermetic_agent.providers.base import ChatMessage
from hermetic_agent.skills.registry import SkillRegistry

logger = structlog.get_logger(__name__)


class SchedulerService:
    """任务调度服务 — orchestrates the bridge for single / parallel / chain / in-session runs.

    封装"选择 Agent → 创建会话 → chat → 组装 TaskResult"的通用流程，并对外暴露
    单任务、并行、顺序任务链与在已有会话中续跑四种入口。

    Renamed from ``Scheduler`` to follow the harness `*Service` naming rule.
    """

    def __init__(
        self,
        bridge: AgentBridge,
        skill_registry: SkillRegistry,
        mcp_registry: MCPRegistry,
        default_timeout: float = 120.0,
    ) -> None:
        """构造调度服务并初始化内部 ChatStepService。"""
        self._bridge = bridge
        self._skill_registry = skill_registry
        self._mcp_registry = mcp_registry
        self._default_timeout = default_timeout
        self._step = ChatStepService(bridge)

    async def run(
        self,
        prompt: str,
        agent_name: str | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        timeout: float | None = None,
        skills: list[str] | None = None,
        tools: list[str] | None = None,
    ) -> TaskResult:
        """执行单个任务。

        Args:
            prompt: 用户提示词。
            agent_name: 指定 Agent 名；为空则由 ChatStepService 自动选择。
            model: 覆盖 Agent 默认模型。
            system_prompt: 额外的系统提示词。
            timeout: 单次 chat 超时秒数。
            skills: 要注入的技能名列表。
            tools: 要启用的 MCP 工具名列表。

        Returns:
            任务执行结果，失败时 ``success=False`` 并包含 ``error`` 字段。
        """
        logger.info("task_run_start", agent_name=agent_name, prompt_length=len(prompt or ""))
        result = await self._step.execute(
            prompt, agent_name=agent_name, model=model, system_prompt=system_prompt,
            skills=skills, tools=tools, timeout=timeout,
        )
        if result.success:
            logger.info("task_completed", agent_name=result.agent_name,
                        session_id=result.session_id, duration=result.duration)
        else:
            logger.error("task_failed", agent_name=result.agent_name,
                         session_id=result.session_id, error=result.error)
        return result

    async def run_parallel(
        self,
        prompts: list[str],
        agent_names: list[str] | None = None,
        timeout: float | None = None,
        skills: list[str] | None = None,
        tools: list[str] | None = None,
    ) -> list[TaskResult]:
        """并行执行多个任务。

        Args:
            prompts: 任务提示词列表。
            agent_names: 与 prompts 等长的 Agent 名列表，None 表示自动分配。
            timeout: 单任务超时秒数。
            skills: 要注入的技能名列表。
            tools: 要启用的 MCP 工具名列表。

        Returns:
            与 prompts 等长的 TaskResult 列表；失败的子任务以 ``success=False`` 表达。

        Raises:
            ValueError: 当 ``agent_names`` 长度与 ``prompts`` 不一致时。
        """
        logger.info("task_run_parallel_start", count=len(prompts), agent_names=agent_names)
        if agent_names and len(agent_names) != len(prompts):
            logger.error("task_run_parallel_failed", reason="agent_names_length_mismatch",
                         prompts=len(prompts), agent_names=len(agent_names))
            raise ValueError("agent_names length must match prompts length")

        tasks = [
            self.run(prompt=p, agent_name=agent_names[i] if agent_names else None,
                     timeout=timeout, skills=skills, tools=tools)
            for i, p in enumerate(prompts)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        out: list[TaskResult] = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                logger.error("task_failed",
                             agent_name=agent_names[i] if agent_names else None,
                             error=str(r))
                out.append(TaskResult(
                    success=False, error=str(r),
                    agent_name=agent_names[i] if agent_names else None,
                ))
            else:
                out.append(r)
        return out

    async def run_chain(
        self,
        prompts: list[str],
        agent_name: str | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        timeout: float | None = None,
        skills: list[str] | None = None,
        tools: list[str] | None = None,
    ) -> TaskResult:
        """顺序执行多个任务（任务链），上一个输出会作为上下文传入下一步。

        Args:
            prompts: 任务提示词列表，按顺序执行。
            agent_name: 指定 Agent 名；为空则自动选择。
            model: 覆盖默认模型。
            system_prompt: 额外的系统提示词。
            timeout: 每步 chat 的超时秒数。
            skills: 要注入的技能名列表。
            tools: 要启用的 MCP 工具名列表。

        Returns:
            最终结果包含 steps、每步 results 与累积上下文 final_context。
        """
        start = time.time()
        logger.info("chain_run_start", steps=len(prompts), agent_name=agent_name)
        instance_name, err = await self._step.select_agent(agent_name)
        if err is not None:
            logger.error("chain_failed", reason="select_agent_failed", error=err.error)
            return err

        try:
            session_info = await self._bridge.create_session(agent_name=instance_name)
        except Exception as e:
            logger.error("chain_failed", reason="create_session_error",
                         agent_name=instance_name, error=str(e))
            return TaskResult(
                success=False, error=str(e), agent_name=instance_name,
                duration=time.time() - start,
            )

        results: list[str | None] = []
        accumulated = ""
        for i, prompt in enumerate(prompts):
            full = (
                f"Previous context:\n{accumulated}\n\nCurrent task:\n{prompt}"
                if accumulated else prompt
            )
            logger.info("chain_step", step=i + 1, total=len(prompts),
                        agent_name=instance_name, session_id=session_info.session_id)
            chat_result = await self._bridge.chat(
                session_id=session_info.session_id,
                messages=[ChatMessage(role="user", content=full)],
                model=model, system_prompt=system_prompt,
                skills=skills, tools=tools, timeout=timeout,
            )
            content = chat_result.message.content if chat_result.message else None
            results.append(content)
            if content:
                accumulated += f"\n--- Step {i + 1} ---\n{content}"

        duration = time.time() - start
        logger.info("chain_completed", steps=len(prompts), agent_name=instance_name,
                    session_id=session_info.session_id, duration=duration)
        return TaskResult(
            success=True,
            result={"steps": len(prompts), "results": results, "final_context": accumulated},
            agent_name=instance_name, session_id=session_info.session_id, duration=duration,
        )

    async def run_in_session(
        self,
        session_id: str,
        prompt: str,
        timeout: float | None = None,
        skills: list[str] | None = None,
        tools: list[str] | None = None,
    ) -> TaskResult:
        """在已有会话中继续对话，不创建新会话。

        Args:
            session_id: 已有会话 ID。
            prompt: 用户提示词。
            timeout: chat 超时秒数。
            skills: 要注入的技能名列表。
            tools: 要启用的 MCP 工具名列表。

        Returns:
            任务执行结果。
        """
        logger.info("session_chat_start", session_id=session_id, prompt_length=len(prompt or ""))
        result = await self._step.execute(
            prompt, agent_name=None, timeout=timeout,
            skills=skills, tools=tools, existing_session_id=session_id,
        )
        if result.success:
            logger.info("task_completed", agent_name=result.agent_name,
                        session_id=session_id, duration=result.duration)
        else:
            logger.error("session_chat_failed", session_id=session_id, error=result.error)
        return result


# Re-exported at the bottom (not the top) to avoid a circular import: the
# `services.chat_step_service` module needs TaskResult too, and importing
# `scheduler` re-orders that. `core.task_result` is the canonical home.
__all__ = [
    "SchedulerService",
    "TaskResult",
]
