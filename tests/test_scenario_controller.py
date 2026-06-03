"""ScenarioController 端点测试 — 5 核心 + 4 stub 端点."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path

import pytest
from sanic import Sanic

from openagent.api.controllers.scenario_controller import scenario_bp
from openagent.config.settings import Settings
from openagent.scenarios.config import (
    ExecutionConfig,
    ProgressiveSkillConfig,
    RoutingConfig,
    ScenarioConfig,
    WorkspaceConfig,
)
from openagent.scenarios.injector import ScenarioInjector
from openagent.scenarios.registry import ScenarioRegistry
from openagent.scenarios.router import ScenarioRouter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_workspace_dir() -> str:
    """真实存在的临时目录 — 给 workspace_dirs 用 (loader 校验存在性)."""
    with tempfile.TemporaryDirectory(prefix="oa-scen-test-") as d:
        yield d


def _scenario(
    name: str,
    *,
    skills: list[str] | None = None,
    tools: list[str] | None = None,
    keywords: list[str] | None = None,
    workspace_dir: str = "",
) -> ScenarioConfig:
    return ScenarioConfig(
        name=name,
        version="1.0.0",
        enabled=True,
        routing=RoutingConfig(trigger_keywords=keywords or []),
        execution=ExecutionConfig(
            system_prompt=f"PROMPT_{name}",
            skills=skills or [],
            tools=tools or [],
            orchestration="single",
        ),
        workspace=WorkspaceConfig(workspace_dirs=[workspace_dir or os.getcwd()]),
        progressive_skill=ProgressiveSkillConfig(strategy="none"),
    )


@pytest.fixture
def app_with_registry(real_workspace_dir: str) -> Sanic:
    """Sanic app + scenario blueprint + ctx 注入 (用 uuid 保证唯一)."""
    app = Sanic(f"test-scenario-controller-{uuid.uuid4().hex[:8]}")
    app.blueprint(scenario_bp)

    reg = ScenarioRegistry()
    reg.register(_scenario("_default", workspace_dir=real_workspace_dir))
    reg.register(_scenario("_generic", workspace_dir=real_workspace_dir))
    reg.register(_scenario(
        "flight",
        skills=["book-flight"], tools=["query_flight"],
        keywords=["book"],
        workspace_dir=real_workspace_dir,
    ))

    app.ctx.scenario_registry = reg
    app.ctx.scenario_router = ScenarioRouter(reg, default_scenario="_default")
    app.ctx.scenario_injector = ScenarioInjector()
    app.ctx.settings = Settings(
        scenario_paths=["work/scenarios"],
        default_scenario="_default",
        work_root="work",
    )
    return app


def _get(app: Sanic, path: str):
    return app.test_client.get(path)


def _post(app: Sanic, path: str, body: dict | None = None):
    return app.test_client.post(path, json=body or {})


def _delete(app: Sanic, path: str):
    return app.test_client.delete(path)


# ---------------------------------------------------------------------------
# 1. 列表
# ---------------------------------------------------------------------------


def test_list_scenarios_returns_all(app_with_registry: Sanic):
    _, resp = _get(app_with_registry, "/agent/scenarios/")
    assert resp.status_code == 200
    data = resp.json
    assert data["success"] is True
    assert data["total"] == 3
    names = {s["name"] for s in data["scenarios"]}
    assert {"_default", "_generic", "flight"} == names


# ---------------------------------------------------------------------------
# 2. 查询单个
# ---------------------------------------------------------------------------


def test_get_scenario_returns_specific(app_with_registry: Sanic):
    _, resp = _get(app_with_registry, "/agent/scenarios/flight")
    assert resp.status_code == 200
    data = resp.json
    assert data["success"] is True
    assert data["scenario"]["name"] == "flight"
    assert data["scenario"]["execution"]["skills"] == ["book-flight"]


def test_get_scenario_returns_404_for_missing(app_with_registry: Sanic):
    _, resp = _get(app_with_registry, "/agent/scenarios/nonexistent")
    assert resp.status_code == 404
    data = resp.json
    assert data["success"] is False
    assert data["code"] == "SCENARIO_NOT_FOUND"
    assert "nonexistent" in data["error"]
    assert "_default" in data["available"]


# ---------------------------------------------------------------------------
# 3. 注册
# ---------------------------------------------------------------------------


def test_register_scenario_persists(app_with_registry: Sanic, real_workspace_dir: str):
    body = {
        "name": "new_scenario",
        "version": "1.0.0",
        "routing": {"trigger_keywords": ["alpha"]},
        "execution": {"orchestration": "single", "skills": [], "tools": []},
        "workspace": {"workspace_dirs": [real_workspace_dir]},
        "progressive_skill": {"strategy": "none"},
        "security": {
            "denied_commands": ["rm -rf", "sudo", "dd"],
        },
    }
    _, resp = _post(app_with_registry, "/agent/scenarios/", body)
    assert resp.status_code == 201
    data = resp.json
    assert data["success"] is True
    assert data["scenario"]["name"] == "new_scenario"
    # 验证已写入注册表
    assert app_with_registry.ctx.scenario_registry.get("new_scenario") is not None


def test_register_scenario_validates_missing_name(app_with_registry: Sanic):
    body = {
        "version": "1.0.0",
        "routing": {},
        "execution": {},
        "workspace": {"workspace_dirs": [os.getcwd()]},
    }
    _, resp = _post(app_with_registry, "/agent/scenarios/", body)
    assert resp.status_code == 400
    assert resp.json["code"] == "VALIDATION_FAILED"


def test_register_scenario_validates_schema(app_with_registry: Sanic):
    """YAML schema 校验失败 → 400 + SCENARIO_VALIDATION_FAILED."""
    body = {
        "name": "Invalid-Name",  # 大写 + 横线 → name pattern 不通过
        "version": "1.0.0",
        "routing": {},
        "execution": {},
        "workspace": {"workspace_dirs": [os.getcwd()]},
        "progressive_skill": {"strategy": "none"},
    }
    _, resp = _post(app_with_registry, "/agent/scenarios/", body)
    assert resp.status_code == 400
    assert resp.json["code"] == "SCENARIO_VALIDATION_FAILED"


def test_register_scenario_overrides_existing(app_with_registry: Sanic, real_workspace_dir: str):
    """同名第二次注册 → override=True 默认覆盖."""
    body = {
        "name": "flight",
        "version": "2.0.0",
        "routing": {"trigger_keywords": ["override"]},
        "execution": {"orchestration": "single", "skills": [], "tools": []},
        "workspace": {"workspace_dirs": [real_workspace_dir]},
        "progressive_skill": {"strategy": "none"},
        "security": {"denied_commands": ["rm -rf", "sudo", "dd"]},
    }
    _, resp = _post(app_with_registry, "/agent/scenarios/", body)
    assert resp.status_code == 201
    cfg = app_with_registry.ctx.scenario_registry.get("flight")
    assert cfg is not None
    assert cfg.version == "2.0.0"


# ---------------------------------------------------------------------------
# 4. 删除
# ---------------------------------------------------------------------------


def test_delete_scenario_removes(app_with_registry: Sanic):
    _, resp = _delete(app_with_registry, "/agent/scenarios/flight")
    assert resp.status_code == 200
    data = resp.json
    assert data["success"] is True
    assert data["name"] == "flight"
    # 注册表里没了
    assert app_with_registry.ctx.scenario_registry.get("flight") is None


def test_delete_scenario_returns_404(app_with_registry: Sanic):
    _, resp = _delete(app_with_registry, "/agent/scenarios/nonexistent")
    assert resp.status_code == 404
    assert resp.json["code"] == "SCENARIO_NOT_FOUND"


# ---------------------------------------------------------------------------
# 5. 重载
# ---------------------------------------------------------------------------


def test_reload_scenarios(app_with_registry: Sanic):
    _, resp = _post(app_with_registry, "/agent/scenarios/reload")
    assert resp.status_code == 200
    data = resp.json
    assert data["success"] is True
    assert "loaded" in data
    assert "scenarios" in data


# ---------------------------------------------------------------------------
# 6. 校验
# ---------------------------------------------------------------------------


def test_validate_scenario_existing(app_with_registry: Sanic):
    _, resp = _get(app_with_registry, "/agent/scenarios/_generic/validate")
    assert resp.status_code == 200
    data = resp.json
    assert data["success"] is True
    assert data["name"] == "_generic"
    assert data["valid"] is True
    assert data["errors"] == []


def test_validate_scenario_missing(app_with_registry: Sanic):
    _, resp = _get(app_with_registry, "/agent/scenarios/nonexistent/validate")
    assert resp.status_code == 200
    data = resp.json
    assert data["valid"] is False
    assert any("not found" in e for e in data["errors"])


# ---------------------------------------------------------------------------
