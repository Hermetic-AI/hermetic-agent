"""MySQL Repository 实现集合.

每个实体一个 MySQL 实现, 都依赖 ``MySQLPool``.
"""

from hermetic_agent.store.repositories.mysql.audit_log_repo_mysql import MySQLAuditLogRepository
from hermetic_agent.store.repositories.mysql.chat_turn_repo_mysql import MySQLChatTurnRepository
from hermetic_agent.store.repositories.mysql.mcp_config_repo_mysql import MySQLMcpConfigRepository
from hermetic_agent.store.repositories.mysql.message_repo_mysql import MySQLMessageRepository
from hermetic_agent.store.repositories.mysql.part_repo_mysql import MySQLPartRepository
from hermetic_agent.store.repositories.mysql.prompt_repo_mysql import MySQLPromptRepository
from hermetic_agent.store.repositories.mysql.scenario_repo_mysql import MySQLScenarioRepository
from hermetic_agent.store.repositories.mysql.session_repo_mysql import MySQLSessionRepository
from hermetic_agent.store.repositories.mysql.skill_repo_mysql import MySQLSkillRepository
from hermetic_agent.store.repositories.mysql.work_trace_repo_mysql import MySQLWorkTraceRepository

__all__ = [
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
]
