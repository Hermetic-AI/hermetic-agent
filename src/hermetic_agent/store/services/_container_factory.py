"""Settings-driven ServiceContainer 工厂.

从 ``settings.storage_backend`` 选 memory / mysql 装配策略,
再委托给 ``build_container`` 完成实际接线.
"""
from __future__ import annotations

import structlog

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


async def _mysql_repos(settings) -> dict[str, object]:
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
    dsn = getattr(
        settings, "mysql_dsn", "mysql://root@127.0.0.1:3306/hermetic_agent",
    )
    echo = getattr(settings, "mysql_echo", False)
    await init_tortoise(dsn, echo=echo, generate_schemas=True)
    logger.info(
        "container_backend_mysql",
        note="Tortoise.init + generate_schemas; no separate MySQLPool needed",
        echo=echo,
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
        repos = await _mysql_repos(settings)
    else:
        raise ValueError(f"Unsupported storage_backend: {backend!r}")
    return build_container(**repos)  # type: ignore[arg-type]


__all__ = ["build_container_from_settings"]
