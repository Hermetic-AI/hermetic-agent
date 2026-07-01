"""Settings-driven ServiceContainer 工厂.

从 ``settings.storage_backend`` 选 memory / mysql 装配策略,
再委托给 ``build_container`` 完成实际接线.
"""
from __future__ import annotations

import structlog

from hermetic_agent.store.repositories.agent_repo import AgentRepository
from hermetic_agent.store.repositories.audit_log_repo import AuditLogRepository
from hermetic_agent.store.repositories.chat_turn_repo import ChatTurnRepository
from hermetic_agent.store.repositories.command_repo import CommandRepository
from hermetic_agent.store.repositories.mcp_config_repo import McpConfigRepository
from hermetic_agent.store.repositories.message_repo import MessageRepository
from hermetic_agent.store.repositories.part_repo import PartRepository
from hermetic_agent.store.repositories.prompt_repo import PromptRepository
from hermetic_agent.store.repositories.scenario_repo import ScenarioRepository
from hermetic_agent.store.repositories.session_repo import SessionRepository
from hermetic_agent.store.repositories.skill_repo import SkillRepository
from hermetic_agent.store.repositories.work_trace_repo import WorkTraceRepository
from hermetic_agent.store.services.container import ServiceContainer, build_container

logger = structlog.get_logger(__name__)


def _memory_repos() -> dict[str, object]:
    from hermetic_agent.store.repositories.memory import (
        MemoryAgentRepository,
        MemoryAuditLogRepository,
        MemoryChatTurnRepository,
        MemoryCommandRepository,
        MemoryMcpConfigRepository,
        MemoryMessageRepository,
        MemoryPartRepository,
        MemoryPromptRepository,
        MemoryScenarioRepository,
        MemorySessionRepository,
        MemorySkillRepository,
        MemoryWorkTraceRepository,
    )
    return {
        "scenario_repo": MemoryScenarioRepository(),
        "session_repo": MemorySessionRepository(),
        "chat_turn_repo": MemoryChatTurnRepository(),
        "message_repo": MemoryMessageRepository(),
        "part_repo": MemoryPartRepository(),
        "audit_log_repo": MemoryAuditLogRepository(),
        "skill_repo": MemorySkillRepository(),
        "mcp_config_repo": MemoryMcpConfigRepository(),
        "work_trace_repo": MemoryWorkTraceRepository(),
        "prompt_repo": MemoryPromptRepository(),
        "command_repo": MemoryCommandRepository(),
        "agent_repo": MemoryAgentRepository(),
    }


async def _mysql_repos() -> dict[str, object]:
    from hermetic_agent.store.models._common import init_tortoise
    from hermetic_agent.store.repositories.mysql import (
        MySQLAgentRepository,
        MySQLAuditLogRepository,
        MySQLChatTurnRepository,
        MySQLCommandRepository,
        MySQLMcpConfigRepository,
        MySQLMessageRepository,
        MySQLPartRepository,
        MySQLPromptRepository,
        MySQLScenarioRepository,
        MySQLSessionRepository,
        MySQLSkillRepository,
        MySQLWorkTraceRepository,
    )
    dsn = "mysql://root@127.0.0.1:3306/hermetic_agent"
    await init_tortoise(dsn, generate_schemas=True)
    logger.info(
        "container_backend_mysql",
        note="Tortoise.init + generate_schemas; no separate MySQLPool needed",
    )
    return {
        "scenario_repo": MySQLScenarioRepository(),
        "session_repo": MySQLSessionRepository(),
        "chat_turn_repo": MySQLChatTurnRepository(),
        "message_repo": MySQLMessageRepository(),
        "part_repo": MySQLPartRepository(),
        "audit_log_repo": MySQLAuditLogRepository(),
        "skill_repo": MySQLSkillRepository(),
        "mcp_config_repo": MySQLMcpConfigRepository(),
        "work_trace_repo": MySQLWorkTraceRepository(),
        "prompt_repo": MySQLPromptRepository(),
        "command_repo": MySQLCommandRepository(),
        "agent_repo": MySQLAgentRepository(),
    }


async def build_container_from_settings(
    settings, _ddl_sql: str | None = None,
) -> ServiceContainer:
    """从全局 settings 自动装配 ServiceContainer (memory / mysql 二选一)."""
    backend = getattr(settings, "storage_backend", "memory").lower()
    if backend == "memory":
        logger.info("container_backend_memory")
        repos = _memory_repos()
    elif backend == "mysql":
        repos = await _mysql_repos()
    else:
        raise ValueError(f"Unsupported storage_backend: {backend!r}")
    return build_container(**repos)  # type: ignore[arg-type]


__all__ = ["build_container_from_settings"]


# Re-export to keep import path stable
_ = (
    AgentRepository, AuditLogRepository, ChatTurnRepository,
    CommandRepository, McpConfigRepository, MessageRepository,
    PartRepository, PromptRepository, ScenarioRepository,
    SessionRepository, SkillRepository, WorkTraceRepository,
)
