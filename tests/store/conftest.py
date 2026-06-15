"""openagent.store 测试 fixtures.

提供:
- ``mysql_pool``        — 真实 MySQL 连接池 (每次测试前清表)
- ``scenario_repo``     — MySQL 场景仓储
- ``session_repo``      — MySQL 会话仓储
- ``message_repo``      — MySQL 消息仓储
- ``part_repo``         — MySQL 分段仓储
- ``chat_turn_repo``    — MySQL turn 仓储
- ``audit_log_repo``    — MySQL 审计仓储
- ``service_container`` — 装配好的 ServiceContainer
- ``memory_container``  — 纯内存版 ServiceContainer (无 MySQL 依赖, 跑得快)
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio

from openagent.store import (
    ServiceContainer,
    build_container,
)
from openagent.store.driver import MySQLConfig, MySQLPool
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

# 加载 v2 schema
SCHEMA_SQL = (Path(__file__).resolve().parents[2] / "docs/db/openagent-schema.sql").read_text(
    encoding="utf-8"
)

MYSQL_DSN = os.environ.get(
    "OPENAGENT_TEST_MYSQL_DSN",
    "mysql://root:1014@127.0.0.1:13306/openagent",
)


async def _truncate_all(pool: MySQLPool) -> None:
    """测试 setup/teardown: 清空所有表."""
    await pool.execute("SET FOREIGN_KEY_CHECKS=0")
    for tbl in (
        "audit_logs",
        "parts",
        "messages",
        "chat_turns",
        "sessions",
        "scenarios",
    ):
        await pool.execute(f"TRUNCATE TABLE {tbl}")
    await pool.execute("SET FOREIGN_KEY_CHECKS=1")


@pytest_asyncio.fixture
async def mysql_pool() -> AsyncIterator[MySQLPool]:
    """真实 MySQL 池. 启动期 init_schema, 测试结束 close."""
    cfg = MySQLConfig.from_dsn(MYSQL_DSN)
    pool = MySQLPool(cfg, min_size=1, max_size=4)
    await pool.connect()
    await pool.init_schema(SCHEMA_SQL)
    await _truncate_all(pool)
    try:
        yield pool
    finally:
        await _truncate_all(pool)
        await pool.close()


@pytest_asyncio.fixture
async def scenario_repo(mysql_pool: MySQLPool) -> MySQLScenarioRepository:
    return MySQLScenarioRepository(mysql_pool)


@pytest_asyncio.fixture
async def session_repo(mysql_pool: MySQLPool) -> MySQLSessionRepository:
    return MySQLSessionRepository(mysql_pool)


@pytest_asyncio.fixture
async def chat_turn_repo(mysql_pool: MySQLPool) -> MySQLChatTurnRepository:
    return MySQLChatTurnRepository(mysql_pool)


@pytest_asyncio.fixture
async def message_repo(mysql_pool: MySQLPool) -> MySQLMessageRepository:
    return MySQLMessageRepository(mysql_pool)


@pytest_asyncio.fixture
async def part_repo(mysql_pool: MySQLPool) -> MySQLPartRepository:
    return MySQLPartRepository(mysql_pool)


@pytest_asyncio.fixture
async def audit_log_repo(mysql_pool: MySQLPool) -> MySQLAuditLogRepository:
    return MySQLAuditLogRepository(mysql_pool)


@pytest_asyncio.fixture
async def service_container(
    scenario_repo,
    session_repo,
    chat_turn_repo,
    message_repo,
    part_repo,
    audit_log_repo,
) -> ServiceContainer:
    return build_container(
        scenario_repo=scenario_repo,
        session_repo=session_repo,
        chat_turn_repo=chat_turn_repo,
        message_repo=message_repo,
        part_repo=part_repo,
        audit_log_repo=audit_log_repo,
    )


@pytest_asyncio.fixture
async def memory_container() -> ServiceContainer:
    """纯内存版 ServiceContainer. 不依赖 MySQL, 跑得快."""
    return build_container(
        scenario_repo=MemoryScenarioRepository(),
        session_repo=MemorySessionRepository(),
        chat_turn_repo=MemoryChatTurnRepository(),
        message_repo=MemoryMessageRepository(),
        part_repo=MemoryPartRepository(),
        audit_log_repo=MemoryAuditLogRepository(),
    )
