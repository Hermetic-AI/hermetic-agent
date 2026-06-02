"""存储层入口：导出 Session/Message/Part 模型与仓储抽象，并注册可用后端。

同时保留旧名（``StorageBackend``、``MemoryStorage``、``PostgresStorage``）
作为向后兼容别名，避免破坏调用方。
"""

from __future__ import annotations

from openagent.store.base import (
    Message,
    Part,
    Session,
    SessionRepository,
    SessionRepositoryFactory,
)
from openagent.store.memory import MemorySessionRepository
from openagent.store.postgres import PostgresSessionRepository

# Register repositories so the factory can find them. Old class names
# (MemoryStorage / PostgresStorage / StorageBackend / StorageBackendFactory)
# remain available as back-compat aliases in their respective modules.
SessionRepositoryFactory.register("postgres", PostgresSessionRepository)
SessionRepositoryFactory.register("memory", MemorySessionRepository)

# Re-export the legacy names so callers like app.py that import
# `StorageBackendFactory` continue to work.
StorageBackend = SessionRepository
StorageBackendFactory = SessionRepositoryFactory
MemoryStorage = MemorySessionRepository
PostgresStorage = PostgresSessionRepository

__all__ = [
    "SessionRepository",
    "Session",
    "Message",
    "Part",
    "SessionRepositoryFactory",
    "PostgresSessionRepository",
    "MemorySessionRepository",
    # Back-compat:
    "StorageBackend",
    "StorageBackendFactory",
    "PostgresStorage",
    "MemoryStorage",
]
