"""Repository 层公开导出.

分两类:
- ABC (抽象接口) — Service 层只依赖 ABC, 不直接 import MySQL/Memory
- MySQL/Memory 实现 — 工厂装配时用
"""

from openagent.store.repositories._base import Repository
from openagent.store.repositories.audit_log_repo import AuditLogRepository
from openagent.store.repositories.chat_turn_repo import ChatTurnRepository

# Memory 实现
from openagent.store.repositories.memory import (
    MemoryAuditLogRepository,
    MemoryChatTurnRepository,
    MemoryMessageRepository,
    MemoryPartRepository,
    MemoryScenarioRepository,
    MemorySessionRepository,
)
from openagent.store.repositories.message_repo import MessageRepository

# MySQL 实现
from openagent.store.repositories.mysql import (
    MySQLAuditLogRepository,
    MySQLChatTurnRepository,
    MySQLMessageRepository,
    MySQLPartRepository,
    MySQLScenarioRepository,
    MySQLSessionRepository,
)
from openagent.store.repositories.part_repo import PartRepository
from openagent.store.repositories.scenario_repo import ScenarioRepository
from openagent.store.repositories.session_repo import SessionRepository

__all__ = [
    # ABC
    "Repository",
    "ScenarioRepository",
    "SessionRepository",
    "ChatTurnRepository",
    "MessageRepository",
    "PartRepository",
    "AuditLogRepository",
    # MySQL
    "MySQLScenarioRepository",
    "MySQLSessionRepository",
    "MySQLChatTurnRepository",
    "MySQLMessageRepository",
    "MySQLPartRepository",
    "MySQLAuditLogRepository",
    # Memory
    "MemoryScenarioRepository",
    "MemorySessionRepository",
    "MemoryChatTurnRepository",
    "MemoryMessageRepository",
    "MemoryPartRepository",
    "MemoryAuditLogRepository",
]
