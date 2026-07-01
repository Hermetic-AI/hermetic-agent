"""Repository 层公开导出.

分两类:
- ABC (抽象接口) — Service 层只依赖 ABC, 不直接 import MySQL/Memory
- MySQL/Memory 实现 — 工厂装配时用
"""

from hermetic_agent.store.repositories._base import Repository
from hermetic_agent.store.repositories.audit_log_repo import AuditLogRepository
from hermetic_agent.store.repositories.chat_turn_repo import ChatTurnRepository
from hermetic_agent.store.repositories.command_repo import CommandRepository
from hermetic_agent.store.repositories.mcp_config_repo import McpConfigRepository

# Memory 实现
from hermetic_agent.store.repositories.memory import (
    MemoryAuditLogRepository,
    MemoryChatTurnRepository,
    MemoryCommandRepository,
    MemoryMcpConfigRepository,
    MemoryMessageRepository,
    MemoryPartRepository,
    MemoryScenarioRepository,
    MemorySessionRepository,
    MemorySkillRepository,
    MemoryWorkTraceRepository,
)
from hermetic_agent.store.repositories.message_repo import MessageRepository

# MySQL 实现
from hermetic_agent.store.repositories.mysql import (
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
from hermetic_agent.store.repositories.part_repo import PartRepository
from hermetic_agent.store.repositories.prompt_repo import PromptRepository
from hermetic_agent.store.repositories.scenario_repo import ScenarioRepository
from hermetic_agent.store.repositories.session_repo import SessionRepository
from hermetic_agent.store.repositories.skill_repo import SkillRepository
from hermetic_agent.store.repositories.work_trace_repo import WorkTraceRepository

__all__ = [
    # ABC
    "Repository",
    "ScenarioRepository",
    "SessionRepository",
    "ChatTurnRepository",
    "MessageRepository",
    "PartRepository",
    "AuditLogRepository",
    "SkillRepository",
    "McpConfigRepository",
    "WorkTraceRepository",
    "PromptRepository",
    "CommandRepository",
    # MySQL
    "MySQLScenarioRepository",
    "MySQLSessionRepository",
    "MySQLChatTurnRepository",
    "MySQLMessageRepository",
    "MySQLPartRepository",
    "MySQLAuditLogRepository",
    "MySQLSkillRepository",
    "MySQLMcpConfigRepository",
    "MySQLWorkTraceRepository",
    "MySQLPromptRepository",
    "MySQLCommandRepository",
    # Memory
    "MemoryScenarioRepository",
    "MemorySessionRepository",
    "MemoryChatTurnRepository",
    "MemoryMessageRepository",
    "MemoryPartRepository",
    "MemoryAuditLogRepository",
    "MemorySkillRepository",
    "MemoryMcpConfigRepository",
    "MemoryWorkTraceRepository",
    "MemoryPromptRepository",
    "MemoryCommandRepository",
]
