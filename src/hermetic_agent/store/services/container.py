"""Service Container — 12 个 Service 的统一装配.

启动期 (``build_container_from_settings``, 见 ``_container_factory.py``):
- ``memory``  → ``Memory*Repository`` 装配
- ``mysql``   → ``Tortoise.init()`` + ``MySQL*Repository`` 装配
"""
from __future__ import annotations

from dataclasses import dataclass

import structlog

from hermetic_agent.store.repositories import (
    AgentRepository,
    AuditLogRepository,
    ChatTurnRepository,
    CommandRepository,
    McpConfigRepository,
    MessageRepository,
    PartRepository,
    PromptRepository,
    ScenarioRepository,
    SessionRepository,
    SkillRepository,
    WorkTraceRepository,
)
from hermetic_agent.store.services.agent_service import AgentService
from hermetic_agent.store.services.audit_log_service import AuditLogService
from hermetic_agent.store.services.chat_turn_service import ChatTurnService
from hermetic_agent.store.services.command_service import CommandService
from hermetic_agent.store.services.mcp_config_service import McpConfigService
from hermetic_agent.store.services.message_service import MessageService
from hermetic_agent.store.services.part_service import PartService
from hermetic_agent.store.services.prompt_service import PromptService
from hermetic_agent.store.services.scenario_service import ScenarioService
from hermetic_agent.store.services.session_service import SessionService
from hermetic_agent.store.services.skill_service import SkillService
from hermetic_agent.store.services.work_trace_service import WorkTraceService

logger = structlog.get_logger(__name__)


@dataclass
class ServiceContainer:
    """12 个 Service 容器."""

    audit_log: AuditLogService
    scenario: ScenarioService
    session: SessionService
    chat_turn: ChatTurnService
    message: MessageService
    part: PartService
    skill: SkillService
    mcp_config: McpConfigService
    work_trace: WorkTraceService
    prompt: PromptService
    command: CommandService
    agent: AgentService

    @property
    def skill_service(self) -> SkillService:
        return self.skill

    @property
    def mcp_config_service(self) -> McpConfigService:
        return self.mcp_config

    @property
    def prompt_service(self) -> PromptService:
        return self.prompt

    @property
    def command_service(self) -> CommandService:
        return self.command

    @property
    def agent_service(self) -> AgentService:
        return self.agent

    async def close(self) -> None:
        """关闭底层资源. ``Tortoise.close_connections()`` 由 lifecycle 调, 这里不重复."""
        logger.info("service_container_close")


def build_container(
    *,
    scenario_repo: ScenarioRepository,
    session_repo: SessionRepository,
    chat_turn_repo: ChatTurnRepository,
    message_repo: MessageRepository,
    part_repo: PartRepository,
    audit_log_repo: AuditLogRepository,
    skill_repo: SkillRepository,
    mcp_config_repo: McpConfigRepository,
    work_trace_repo: WorkTraceRepository,
    prompt_repo: PromptRepository,
    command_repo: CommandRepository,
    agent_repo: AgentRepository,
) -> ServiceContainer:
    """从 12 个 Repository 装配出 ServiceContainer."""
    audit, session, scenario, chat_turn, message, part = _core_services(
        scenario_repo, session_repo, chat_turn_repo,
        message_repo, part_repo, audit_log_repo,
    )
    skill = SkillService(skill_repo, audit)
    mcp_config = McpConfigService(mcp_config_repo, audit)
    work_trace = WorkTraceService(work_trace_repo)
    prompt = PromptService(prompt_repo, audit)
    command = CommandService(command_repo, audit)
    agent = AgentService(
        agent_repo, audit,
        skill_service=skill, mcp_config_service=mcp_config,
        prompt_service=prompt, command_service=command,
    )
    logger.info("service_container_built")
    return ServiceContainer(
        audit_log=audit, scenario=scenario, session=session,
        chat_turn=chat_turn, message=message, part=part,
        skill=skill, mcp_config=mcp_config, work_trace=work_trace,
        prompt=prompt, command=command, agent=agent,
    )


def _core_services(
    scenario_repo, session_repo, chat_turn_repo,
    message_repo, part_repo, audit_log_repo,
):
    audit = AuditLogService(audit_log_repo)
    session = SessionService(session_repo, audit)
    scenario = ScenarioService(scenario_repo, audit)
    chat_turn = ChatTurnService(chat_turn_repo, audit, session)
    message = MessageService(message_repo, part_repo, audit, session)
    part = PartService(part_repo, audit)
    return audit, session, scenario, chat_turn, message, part


def build_default_container(
    *,
    scenario_repo: ScenarioRepository,
    session_repo: SessionRepository,
    chat_turn_repo: ChatTurnRepository,
    message_repo: MessageRepository,
    part_repo: PartRepository,
    audit_log_repo: AuditLogRepository,
    skill_repo: SkillRepository,
    mcp_config_repo: McpConfigRepository,
    work_trace_repo: WorkTraceRepository,
    prompt_repo: PromptRepository,
    command_repo: CommandRepository,
    agent_repo: AgentRepository,
) -> ServiceContainer:
    """``build_container`` 别名(README 文档用)."""
    return build_container(
        scenario_repo=scenario_repo,
        session_repo=session_repo,
        chat_turn_repo=chat_turn_repo,
        message_repo=message_repo,
        part_repo=part_repo,
        audit_log_repo=audit_log_repo,
        skill_repo=skill_repo,
        mcp_config_repo=mcp_config_repo,
        work_trace_repo=work_trace_repo,
        prompt_repo=prompt_repo,
        command_repo=command_repo,
        agent_repo=agent_repo,
    )


__all__ = [
    "ServiceContainer",
    "build_container",
    "build_default_container",
]
