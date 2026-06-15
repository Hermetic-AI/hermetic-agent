"""Service Container — 6 个 Service 的统一装配.

业务层只 import ServiceContainer, 通过 ``container.xxx_service.method()`` 调用.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from openagent.store.repositories import (
    AuditLogRepository,
    ChatTurnRepository,
    MessageRepository,
    PartRepository,
    ScenarioRepository,
    SessionRepository,
)
from openagent.store.services.audit_log_service import AuditLogService
from openagent.store.services.chat_turn_service import ChatTurnService
from openagent.store.services.message_service import MessageService
from openagent.store.services.part_service import PartService
from openagent.store.services.scenario_service import ScenarioService
from openagent.store.services.session_service import SessionService

logger = structlog.get_logger(__name__)


@dataclass
class ServiceContainer:
    """6 个 Service 容器."""

    audit_log: AuditLogService
    scenario: ScenarioService
    session: SessionService
    chat_turn: ChatTurnService
    message: MessageService
    part: PartService

    async def close(self) -> None:
        """关闭底层资源(由 factory 注入, 此处不直接关 pool)."""
        logger.info("service_container_close")


def build_container(
    *,
    scenario_repo: ScenarioRepository,
    session_repo: SessionRepository,
    chat_turn_repo: ChatTurnRepository,
    message_repo: MessageRepository,
    part_repo: PartRepository,
    audit_log_repo: AuditLogRepository,
) -> ServiceContainer:
    """从 6 个 Repository 装配出 ServiceContainer.

    Args:
        *_repo: 6 个 Repository 实现(ABC 子类, MySQL / Memory 均可)

    Returns:
        装好的 ServiceContainer

    Notes:
        Service 之间的依赖(SessionService 写聚合 / ChatTurnService 用 SessionService
        写聚合 / MessageService 用 SessionService 写 message_count)通过循环引用解决.
    """
    # 1. AuditLogService 无依赖
    audit = AuditLogService(audit_log_repo)

    # 2. SessionService 依赖 audit
    session = SessionService(session_repo, audit)

    # 3. ScenarioService 依赖 audit
    scenario = ScenarioService(scenario_repo, audit)

    # 4. ChatTurnService 依赖 audit + session (聚合)
    chat_turn = ChatTurnService(chat_turn_repo, audit, session)

    # 5. MessageService 依赖 audit + part_repo + session (message_count)
    message = MessageService(message_repo, part_repo, audit, session)

    # 6. PartService 依赖 audit
    part = PartService(part_repo, audit)

    logger.info("service_container_built")
    return ServiceContainer(
        audit_log=audit,
        scenario=scenario,
        session=session,
        chat_turn=chat_turn,
        message=message,
        part=part,
    )


def build_default_container(
    *,
    scenario_repo: ScenarioRepository,
    session_repo: SessionRepository,
    chat_turn_repo: ChatTurnRepository,
    message_repo: MessageRepository,
    part_repo: PartRepository,
    audit_log_repo: AuditLogRepository,
) -> ServiceContainer:
    """build_container 别名(README 文档用)."""
    return build_container(
        scenario_repo=scenario_repo,
        session_repo=session_repo,
        chat_turn_repo=chat_turn_repo,
        message_repo=message_repo,
        part_repo=part_repo,
        audit_log_repo=audit_log_repo,
    )


def build_container_from_settings(
    settings, ddl_sql: str | None = None
) -> ServiceContainer:
    """从全局 settings 自动装配 ServiceContainer.

    行为:
    - settings.storage_backend == "memory" -> MemoryRepository 装配(自动)
    - settings.storage_backend == "mysql"  -> MySQLRepository 装配, 启动期 init_schema

    Args:
        settings: openagent.config.settings.Settings 实例
        ddl_sql: MySQL 后端启动期 DDL(可空, 不传则不执行)

    Returns:
        装好的 ServiceContainer
    """
    from openagent.store.repositories.memory import (
        MemoryAuditLogRepository,
        MemoryChatTurnRepository,
        MemoryMessageRepository,
        MemoryPartRepository,
        MemoryScenarioRepository,
        MemorySessionRepository,
    )
    from openagent.store.repositories.mysql import (
        MySQLAuditLogRepository,
        MySQLChatTurnRepository,
        MySQLMessageRepository,
        MySQLPartRepository,
        MySQLScenarioRepository,
        MySQLSessionRepository,
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
        )

    if backend == "mysql":
        from openagent.store.driver import MySQLConfig, MySQLPool

        dsn = getattr(settings, "mysql_dsn", "mysql://root@127.0.0.1:3306/openagent")
        cfg = MySQLConfig.from_dsn(dsn)
        pool = MySQLPool(
            cfg,
            min_size=getattr(settings, "mysql_pool_min_size", 5),
            max_size=getattr(settings, "mysql_pool_max_size", 20),
            echo=getattr(settings, "mysql_echo", False),
        )
        # 注: pool.connect() 需在应用启动期显式调 (lifecycle / app startup),
        # 这里只建 pool 不连, 保持函数纯.
        logger.info("container_backend_mysql", url=cfg.to_url_safe())
        return build_container(
            scenario_repo=MySQLScenarioRepository(pool),
            session_repo=MySQLSessionRepository(pool),
            chat_turn_repo=MySQLChatTurnRepository(pool),
            message_repo=MySQLMessageRepository(pool),
            part_repo=MySQLPartRepository(pool),
            audit_log_repo=MySQLAuditLogRepository(pool),
        )

    raise ValueError(f"Unsupported storage_backend: {backend!r}")
