"""openagent.store 测试 fixtures.

Tortoise ORM 之后, 测试不需要 ``MySQLPool`` + 外部 DDL 文件.
策略:
- 默认用 ``sqlite://:memory:`` (Tortoise 自动建表, 跨测试用 fresh connection)
- 设了 ``OPENAGENT_TEST_MYSQL_DSN`` env 走真实 MySQL (集成测试)

提供:
- ``tortoise_init``         — 启动期 ``Tortoise.init()`` + ``generate_schemas()``,
                              yield 完 ``close_connections()``
- ``truncate_all``          — 每个测试前清表 (避免脏数据)
- ``service_container``     — 装配好的 ``ServiceContainer`` (sqlite 默认 / 可切 mysql)
- ``memory_container``      — 纯内存版 ``ServiceContainer`` (无 DB 依赖, 跑得快)
"""
from __future__ import annotations

import os

import pytest_asyncio

from openagent.store import ServiceContainer, build_container
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


#: 测试用 DB. 优先用 env 指定的 MySQL (集成测试), 否则用 sqlite 内存.
TEST_DSN = os.environ.get(
    "OPENAGENT_TEST_MYSQL_DSN",
    "sqlite://:memory:",
)


async def _truncate_all() -> None:
    """测试 setup/teardown: 清空所有表. Tortoise ``Model.all().delete()``."""
    from tortoise import Tortoise

    conn = Tortoise.get_connection("default")
    for tbl in (
        "audit_logs",
        "parts",
        "messages",
        "chat_turns",
        "sessions",
        "scenarios",
    ):
        try:
            await conn.execute_query(f"DELETE FROM {tbl}")
        except Exception:
            # sqlite 内存模式每次 fixture 都是新库, 第一次可能表还没建;
            # 由调用方保证先 init.
            pass


@pytest_asyncio.fixture
async def tortoise_init():
    """Tortoise 启动 + 拆. 跨 fixture 共享.

    注意: sqlite ``:memory:`` 是 per-connection 库, Tortoise 连接池里连接
    共享同一个库文件 (``file::memory:?cache=shared``), 同一进程内 OK.
    """
    from tortoise import Tortoise

    await init_tortoise(TEST_DSN, generate_schemas=True)
    try:
        yield Tortoise
    finally:
        await Tortoise.close_connections()


@pytest_asyncio.fixture
async def service_container(tortoise_init):
    """装好的 ServiceContainer (MySQL/Tortoise). 每个测试前清表."""
    await _truncate_all()
    try:
        yield build_container(
            scenario_repo=MySQLScenarioRepository(),
            session_repo=MySQLSessionRepository(),
            chat_turn_repo=MySQLChatTurnRepository(),
            message_repo=MySQLMessageRepository(),
            part_repo=MySQLPartRepository(),
            audit_log_repo=MySQLAuditLogRepository(),
        )
    finally:
        await _truncate_all()


@pytest_asyncio.fixture
async def memory_container() -> ServiceContainer:
    """纯内存版 ServiceContainer. 不依赖 DB, 跑得快."""
    return build_container(
        scenario_repo=MemoryScenarioRepository(),
        session_repo=MemorySessionRepository(),
        chat_turn_repo=MemoryChatTurnRepository(),
        message_repo=MemoryMessageRepository(),
        part_repo=MemoryPartRepository(),
        audit_log_repo=MemoryAuditLogRepository(),
    )


# Repo-level fixtures (从 service_container 拆, 方便老风格测试).
@pytest_asyncio.fixture
async def scenario_repo(service_container):
    yield service_container.scenario._repo


@pytest_asyncio.fixture
async def session_repo(service_container):
    yield service_container.session._repo


@pytest_asyncio.fixture
async def chat_turn_repo(service_container):
    yield service_container.chat_turn._repo


@pytest_asyncio.fixture
async def message_repo(service_container):
    yield service_container.message._repo


@pytest_asyncio.fixture
async def part_repo(service_container):
    yield service_container.part._repo


@pytest_asyncio.fixture
async def audit_log_repo(service_container):
    yield service_container.audit_log._repo
