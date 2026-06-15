"""Service 层 — 业务编排 + 跨 Repository 协作.

职责:
- 接受 DTO, 返回 DTO (不暴露内部 Model)
- 业务规则校验 (超出 DTO pydantic 范围)
- 跨 Repository 编排 (如创建 turn 时同时更新 session 聚合)
- 写 audit_logs
- 事务边界 (用 MySQLPool.transaction)

Service 之间的依赖通过构造函数注入, 不直接 import 其他 Service.
"""

from openagent.store.services.audit_log_service import AuditLogService
from openagent.store.services.chat_turn_service import ChatTurnService
from openagent.store.services.container import (
    ServiceContainer,
    build_container,
    build_container_from_settings,
    build_default_container,
)
from openagent.store.services.message_service import MessageService
from openagent.store.services.part_service import PartService
from openagent.store.services.scenario_service import ScenarioService
from openagent.store.services.session_service import SessionService

__all__ = [
    "ScenarioService",
    "SessionService",
    "ChatTurnService",
    "MessageService",
    "PartService",
    "AuditLogService",
    "ServiceContainer",
    "build_container",
    "build_default_container",
    "build_container_from_settings",
]
