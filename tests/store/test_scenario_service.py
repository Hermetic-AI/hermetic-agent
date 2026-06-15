"""ScenarioRepository + ScenarioService 集成测试."""

from __future__ import annotations

import pytest

from openagent.store import CreateScenarioRequest
from openagent.store.dto.scenario import UpdateScenarioRequest
from openagent.store.exceptions import DuplicateError, NotFoundError


@pytest.mark.asyncio
async def test_scenario_create_and_get_by_code_version(scenario_repo):
    """场景: create -> get_by_code_version -> create_new_version."""
    from openagent.store import Scenario

    v1 = Scenario(code="flight", name="机票 v1", version=1, config={"a": 1})
    await scenario_repo.create(v1)

    fetched = await scenario_repo.get_by_code_version("flight", 1)
    assert fetched is not None
    assert fetched.id == v1.id

    # 不存在的版本
    assert await scenario_repo.get_by_code_version("flight", 99) is None

    # 创建 v2, parent_id 指向 v1
    v2 = await scenario_repo.create_new_version(v1, {"a": 2}, "机票 v2")
    assert v2.version == 2
    assert v2.parent_id == v1.id
    assert v2.code == "flight"
    assert v2.status == "draft"  # 默认 draft


@pytest.mark.asyncio
async def test_scenario_service_create_with_audit(service_container):
    """Service 层创建场景 + 自动写 audit_log."""
    req = CreateScenarioRequest(
        code="test-svc",
        name="服务创建测试",
        config={"routing": {"strategy": "default"}},
        version=1,
    )
    s = await service_container.scenario.create(req, actor_id="tester-001")
    assert s.id is not None

    # 校验 audit_log
    audits = await service_container.audit_log.list_by_resource("scenario", s.id)
    assert len(audits) == 1
    assert audits[0].action == "create"
    assert audits[0].actor_id == "tester-001"
    assert audits[0].after_data["code"] == "test-svc"


@pytest.mark.asyncio
async def test_scenario_service_duplicate_raises(service_container):
    """同 (code, version) 重复创建抛 DuplicateError."""
    from openagent.store.dto.scenario import CreateScenarioRequest

    req = CreateScenarioRequest(
        code="dup-test",
        name="dup",
        config={},
        version=1,
    )
    await service_container.scenario.create(req)

    with pytest.raises(DuplicateError):
        await service_container.scenario.create(
            CreateScenarioRequest(code="dup-test", name="dup-2", config={}, version=1)
        )


@pytest.mark.asyncio
async def test_scenario_service_update_writes_audit(service_container):
    """Service.update 写 audit, 包含 before/after."""
    s = await service_container.scenario.create(
        CreateScenarioRequest(
            code="upd-test",
            name="before",
            config={"v": 1},
            version=1,
            status="draft",
        )
    )
    updated = await service_container.scenario.update(
        s.id,
        UpdateScenarioRequest(name="after", status="enabled"),
        actor_id="tester-002",
    )
    assert updated.name == "after"
    assert updated.status == "enabled"

    audits = await service_container.audit_log.list_by_resource("scenario", s.id)
    actions = [a.action for a in audits]
    assert "update" in actions
    upd = next(a for a in audits if a.action == "update")
    assert upd.before_data["name"] == "before"
    assert "name" in upd.after_data


@pytest.mark.asyncio
async def test_scenario_service_get_not_found(service_container):
    with pytest.raises(NotFoundError):
        await service_container.scenario.get_by_id("00000000-0000-0000-0000-000000000000")
