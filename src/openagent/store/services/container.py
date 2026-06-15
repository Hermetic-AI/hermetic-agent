"""Service Container — 6 个 Service 的统一装配.

业务层只 import ServiceContainer, 通过 ``container.xxx_service.method()`` 调用.

启动期 (``build_container_from_settings``):
- ``memory``  → 直接用 ``Memory*Repository`` 装配, 无 DB 依赖
- ``mysql``   → ``Tortoise.init()`` + ``Tortoise.generate_schemas()`` 自动建表,
                然后用 ``MySQL*Repository`` (Tortoise ORM) 装配
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
    audit = AuditLogService(audit_log_repo)
    session = SessionService(session_repo, audit)
    scenario = ScenarioService(scenario_repo, audit)
    chat_turn = ChatTurnService(chat_turn_repo, audit, session)
    message = MessageService(message_repo, part_repo, audit, session)
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
    """``build_container`` 别名(README 文档用)."""
    return build_container(
        scenario_repo=scenario_repo,
        session_repo=session_repo,
        chat_turn_repo=chat_turn_repo,
        message_repo=message_repo,
        part_repo=part_repo,
        audit_log_repo=audit_log_repo,
    )


async def build_container_from_settings(
    settings, ddl_sql: str | None = None
) -> ServiceContainer:
    """从全局 settings 自动装配 ServiceContainer.

    行为:
    - ``settings.storage_backend == "memory"`` -> ``MemoryRepository`` 装配
    - ``settings.storage_backend == "mysql"``  -> ``Tortoise.init()`` + 建表 +
      ``MySQLRepository`` (Tortoise ORM) 装配

    Args:
        settings: ``openagent.config.settings.Settings`` 实例
        ddl_sql: 兼容老参数, 忽略 (Tortoise 用 ``generate_schemas`` 自动建表)

    Returns:
        装好的 ServiceContainer
    """
    from openagent.store.models._common import init_tortoise
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
        dsn = getattr(settings, "mysql_dsn", "mysql://root@127.0.0.1:3306/openagent")
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
        )

    raise ValueError(f"Unsupported storage_backend: {backend!r}")
