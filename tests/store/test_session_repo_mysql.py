"""MySQL SessionRepository 集成测试."""

from __future__ import annotations

import pytest

from openagent.store import Session


@pytest.mark.asyncio
async def test_session_crud_lifecycle(session_repo):
    """完整 CRUD: create -> get -> update -> list -> soft_delete -> get_by_id 返回 None."""

    # 1. create
    s = Session(
        user_id="u-001",
        title="hello",
        model="claude-sonnet-4-5",
        agent_name="default",
        metadata={"client": "web", "tags": ["a", "b"]},
    )
    await session_repo.create(s)

    # 2. get_by_id
    fetched = await session_repo.get_by_id(s.id)
    assert fetched is not None
    assert fetched.title == "hello"
    assert fetched.metadata == {"client": "web", "tags": ["a", "b"]}
    assert fetched.cost == 0
    assert fetched.message_count == 0

    # 3. update
    updated = await session_repo.update(s.id, title="hi", status="closed")
    assert updated is not None
    assert updated.title == "hi"
    assert updated.status == "closed"

    # 4. list_by_user
    items = await session_repo.list_by_user("u-001")
    assert len(items) == 1
    assert items[0].id == s.id

    # 5. update_aggregates
    agg = await session_repo.update_aggregates(
        s.id,
        cost_delta=0.05,
        tokens_input_delta=100,
        tokens_output_delta=50,
        message_count=3,
    )
    assert agg is not None
    assert float(agg.cost) == 0.05
    assert agg.tokens_input == 100
    assert agg.tokens_output == 50
    assert agg.message_count == 3

    # 6. soft_delete
    ok = await session_repo.soft_delete(s.id)
    assert ok is True

    # 7. get_by_id 默认过滤 is_deleted=0, 返回 None
    after_delete = await session_repo.get_by_id(s.id)
    assert after_delete is None


@pytest.mark.asyncio
async def test_session_list_filters(session_repo):
    """list 多条件过滤 + count."""
    for i in range(3):
        await session_repo.create(
            Session(user_id="u-001", title=f"s{i}", agent_name="agent-a")
        )
    for i in range(2):
        await session_repo.create(
            Session(user_id="u-002", title=f"s{i}", agent_name="agent-b")
        )

    a_count = await session_repo.count(user_id="u-001")
    b_count = await session_repo.count(user_id="u-002")
    assert a_count == 3
    assert b_count == 2

    agent_a = await session_repo.list(agent_name="agent-a", limit=10)
    assert len(agent_a) == 3

    none = await session_repo.list(user_id="u-999", limit=10)
    assert none == []


@pytest.mark.asyncio
async def test_session_metadata_json_roundtrip(session_repo):
    """metadata dict 写入读出保持一致(验证 JSON 列 + to_db_json/from_db_json)."""
    meta = {
        "client": "web",
        "lang": "zh-CN",
        "nested": {"k": "v", "list": [1, 2, 3]},
        "tags": ["alpha", "beta"],
        "count": 42,
    }
    s = Session(user_id="u-x", title="json-test", metadata=meta)
    await session_repo.create(s)
    fetched = await session_repo.get_by_id(s.id)
    assert fetched is not None
    assert fetched.metadata == meta


@pytest.mark.asyncio
async def test_session_get_nonexistent_returns_none(session_repo):
    """不存在的 ID 返回 None, 不抛 NotFoundError(Repository 层)."""
    result = await session_repo.get_by_id("00000000-0000-0000-0000-000000000000")
    assert result is None


@pytest.mark.asyncio
async def test_session_hard_delete(session_repo):
    s = Session(user_id="u-1", title="x")
    await session_repo.create(s)
    ok = await session_repo.hard_delete(s.id)
    assert ok is True
    assert await session_repo.get_by_id(s.id) is None
