"""Service Container — 8 个 Service 的统一装配.

启动期 (``build_container_from_settings``):
- ``memory``  → ``Memory*Repository`` 装配
- ``mysql``   → ``Tortoise.init()`` + ``MySQL*Repository`` 装配
"""
from __future__ import annotations

from dataclasses import dataclass

import structlog

from hermetic_agent.store.repositories import (
    AuditLogRepository,
    ChatTurnRepository,
    McpConfigRepository,
    MessageRepository,
    PartRepository,
    ScenarioRepository,
    SessionRepository,
    SkillRepository,
)
from hermetic_agent.store.services.audit_log_service import AuditLogService
from hermetic_agent.store.services.chat_turn_service import ChatTurnService
from hermetic_agent.store.services.mcp_config_service import McpConfigService
from hermetic_agent.store.services.message_service import MessageService
from hermetic_agent.store.services.part_service import PartService
from hermetic_agent.store.services.scenario_service import ScenarioService
from hermetic_agent.store.services.session_service import SessionService
from hermetic_agent.store.services.skill_service import SkillService

logger = structlog.get_logger(__name__)


@dataclass
class ServiceContainer:
    """8 个 Service 容器."""

    audit_log: AuditLogService
    scenario: ScenarioService
    session: SessionService
    chat_turn: ChatTurnService
    message: MessageService
    part: PartService
    skill: SkillService
    mcp_config: McpConfigService

    @property
    def skill_service(self) -> SkillService:
        return self.skill

    @property
    def mcp_config_service(self) -> McpConfigService:
        return self.mcp_config

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
) -> ServiceContainer:
    """从 8 个 Repository 装配出 ServiceContainer."""
    audit = AuditLogService(audit_log_repo)
    session = SessionService(session_repo, audit)
    scenario = ScenarioService(scenario_repo, audit)
    chat_turn = ChatTurnService(chat_turn_repo, audit, session)
    message = MessageService(message_repo, part_repo, audit, session)
    part = PartService(part_repo, audit)
    skill = SkillService(skill_repo, audit)
    mcp_config = McpConfigService(mcp_config_repo, audit)
    logger.info("service_container_built")
    return ServiceContainer(
        audit_log=audit,
        scenario=scenario,
        session=session,
        chat_turn=chat_turn,
        message=message,
        part=part,
        skill=skill,
        mcp_config=mcp_config,
    )


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
    )


async def build_container_from_settings(
    settings, ddl_sql: str | None = None
) -> ServiceContainer:
    """从全局 settings 自动装配 ServiceContainer."""
    from hermetic_agent.store.models._common import init_tortoise
    from hermetic_agent.store.repositories.memory import (
        MemoryAuditLogRepository,
        MemoryChatTurnRepository,
        MemoryMcpConfigRepository,
        MemoryMessageRepository,
        MemoryPartRepository,
        MemoryScenarioRepository,
        MemorySessionRepository,
        MemorySkillRepository,
    )
    from hermetic_agent.store.repositories.mysql import (
        MySQLAuditLogRepository,
        MySQLChatTurnRepository,
        MySQLMcpConfigRepository,
        MySQLMessageRepository,
        MySQLPartRepository,
        MySQLScenarioRepository,
        MySQLSessionRepository,
        MySQLSkillRepository,
    )

    backend = getattr(settings, "storage_backend", "memory").lower()

    if backend == "memory":
        logger.info("container_backend_memory")
        return build_container(
            scenario_repo=MemoryScenarioRepository(),
            session_repo=MemorySessionRepository(),
            chat_turn_repo=MemoryChatTurnRepository(),
            message_repo=MemoryMessageRepository(),
            part_repo=MemoryPartRepository(),
            audit_log_repo=MemoryAuditLogRepository(),
            skill_repo=MemorySkillRepository(),
            mcp_config_repo=MemoryMcpConfigRepository(),
        )

    if backend == "mysql":
        dsn = getattr(settings, "mysql_dsn", "mysql://root@127.0.0.1:3306/hermetic_agent")
        echo = getattr(settings, "mysql_echo", False)
        # Tortoise DSN: ``mysql://user:pass@host:port/db`` 同 asyncmy 一致,
        # echo 通过配置开启 SQL 日志 (Tortoise.use_tz 等高级配置未来再加).
        await init_tortoise(dsn, generate_schemas=True)
        logger.info(
            "container_backend_mysql",
            echo=echo,
            note="Tortoise.init + generate_schemas; no separate MySQLPool needed",
        )
        return build_container(
            scenario_repo=MySQLScenarioRepository(),
            session_repo=MySQLSessionRepository(),
            chat_turn_repo=MySQLChatTurnRepository(),
            message_repo=MySQLMessageRepository(),
            part_repo=MySQLPartRepository(),
            audit_log_repo=MySQLAuditLogRepository(),
            skill_repo=MySQLSkillRepository(),
            mcp_config_repo=MySQLMcpConfigRepository(),
        )

    raise ValueError(f"Unsupported storage_backend: {backend!r}")
