"""Memory Repository / Service 单元测试 — 无 MySQL 依赖, 跑得快."""

from __future__ import annotations

import pytest

from openagent.store import (
    CreateScenarioRequest,
    CreateSessionRequest,
)


@pytest.mark.asyncio
async def test_memory_scenario_crud(memory_container):
    c = memory_container
    s = await c.scenario.create(
        CreateScenarioRequest(code="m-1", name="mem", config={}, version=1)
    )
    fetched = await c.scenario.get_by_id(s.id)
    assert fetched.code == "m-1"

    new_v = await c.scenario.create_new_version(s.id, {"k": 2})
    assert new_v.version == 2
    assert new_v.parent_id == s.id


@pytest.mark.asyncio
async def test_memory_session_list_by_user(memory_container):
    c = memory_container
    for i in range(3):
        await c.session.create(
            CreateSessionRequest(user_id="u-A", title=f"s{i}", agent_name="a1")
        )
    for i in range(2):
        await c.session.create(
            CreateSessionRequest(user_id="u-B", title=f"s{i}", agent_name="a2")
        )
    a = await c.session.list_by_user("u-A")
    b = await c.session.list_by_user("u-B")
    assert len(a) == 3
    assert len(b) == 2


@pytest.mark.asyncio
async def test_memory_soft_delete_excludes_from_list(memory_container):
    c = memory_container
    s = await c.session.create(
        CreateSessionRequest(user_id="u-z", title="tmp", agent_name="x")
    )
    assert len(await c.session.list()) == 1
    await c.session.soft_delete(s.id, actor_id="tester")
    assert len(await c.session.list()) == 0
    # include_deleted 仍可见
    assert len(await c.session.list(include_deleted=True)) == 1


@pytest.mark.asyncio
async def test_memory_audit_log_appends_with_seq(memory_container):
    c = memory_container
    sess = await c.session.create(
        CreateSessionRequest(user_id="u-seq", title="seq-test", agent_name="a")
    )
    a1 = await c.audit_log.record(
        actor_type="user", actor_id="u-1", action="create",
        resource_type="session", resource_id=sess.id, use_seq=True,
    )
    a2 = await c.audit_log.record(
        actor_type="user", actor_id="u-1", action="update",
        resource_type="session", resource_id=sess.id, use_seq=True,
    )
    a3 = await c.audit_log.record(
        actor_type="user", actor_id="u-1", action="delete",
        resource_type="session", resource_id=sess.id, use_seq=True,
    )
    assert a1.seq == 1
    assert a2.seq == 2
    assert a3.seq == 3
    # append-only: update / delete 应抛 NotImplementedError
    audit_repo = c.audit_log._repo
    with pytest.raises(NotImplementedError):
        await audit_repo.update(a1.id, action="modified")
    with pytest.raises(NotImplementedError):
        await audit_repo.soft_delete(a1.id)
    with pytest.raises(NotImplementedError):
        await audit_repo.hard_delete(a1.id)
