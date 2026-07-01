"""tests/test_mcp_config_repo_owner_visibility.py — McpConfig Repository 资产可见性测试.

Phase 2 of asset-registry plan: owner/visibility 字段 + 3 个新抽象方法.
只跑 Memory 版本 (无外部 DB 依赖).

注意: 沿用 ``MemoryRepository.create()`` 的 ``str(eid)`` 归一化, 用 ``await
repo.create(s)`` 而不是直接 ``repo._store[s.id] = s`` (后者会让
``set_visibility(str(s.id), ...)`` 拿到 None, 测试是绿的但语义错了).
"""

from __future__ import annotations

import uuid

import pytest

from hermetic_agent.store.models.mcp_config import McpConfig
from hermetic_agent.store.repositories.memory.mcp_config_repo_memory import (
    MemoryMcpConfigRepository,
)


@pytest.mark.asyncio
async def test_list_visible_to_excludes_other_users_private() -> None:
    repo = MemoryMcpConfigRepository()
    own = McpConfig(
        id=uuid.uuid4(), code="c1", owner_user_id="alice", visibility="private",
    )
    other_priv = McpConfig(
        id=uuid.uuid4(), code="c2", owner_user_id="bob", visibility="private",
    )
    other_pub = McpConfig(
        id=uuid.uuid4(), code="c3", owner_user_id="bob", visibility="public",
    )
    await repo.create(own)
    await repo.create(other_priv)
    await repo.create(other_pub)

    items = await repo.list_visible_to(actor_user_id="alice", limit=50, offset=0)
    assert {c.code for c in items} == {"c1", "c3"}


@pytest.mark.asyncio
async def test_set_visibility_blocks_non_owner() -> None:
    repo = MemoryMcpConfigRepository()
    c = McpConfig(
        id=uuid.uuid4(), code="x", owner_user_id="alice", visibility="private",
    )
    await repo.create(c)

    result = await repo.set_visibility(
        str(c.id), visibility="public", actor_user_id="bob",
    )
    assert result is None
    assert (await repo.get_by_id(str(c.id))).visibility == "private"
