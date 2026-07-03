"""ScenarioMiddleware 单测 — 拦截 + 路由 + 注入 + ctx 挂载."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sanic import Sanic

from hermetic_agent.scenarios.config import (
    ExecutionConfig,
    ProgressiveSkillConfig,
    RoutingConfig,
    ScenarioConfig,
    WorkspaceConfig,
)
from hermetic_agent.scenarios.errors import (
    ScenarioError,
    ScenarioNotFoundError,
)
from hermetic_agent.scenarios.injector import ScenarioInjector
from hermetic_agent.scenarios.middleware import ScenarioMiddleware
from hermetic_agent.scenarios.registry import ScenarioRegistry
from hermetic_agent.scenarios.router import ScenarioRouter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _scenario(
    name: str,
    *,
    skills: list[str] | None = None,
    tools: list[str] | None = None,
    keywords: list[str] | None = None,
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
        workspace=WorkspaceConfig(workspace_dirs=["/tmp/proj"]),
        progressive_skill=ProgressiveSkillConfig(strategy="none"),
    )


@pytest.fixture
def app_with_scenarios() -> Sanic:
    """最小 Sanic app + scenario 组件注入到 app.ctx (每个测试唯一名字)."""
    # Sanic 禁止重名 (非 test mode), 用 uuid 区分
    app = Sanic(f"test-scenario-middleware-{uuid.uuid4().hex[:8]}")

    reg = ScenarioRegistry()
    reg.register(_scenario("_default"))
    reg.register(_scenario("flight", skills=["book-flight"], tools=["query_flight"],
                           keywords=["I want to book"]))
    reg.register(_scenario("expense", keywords=["expense"]))

    app.ctx.scenario_registry = reg
    app.ctx.scenario_router = ScenarioRouter(reg, default_scenario="_default")
    app.ctx.scenario_injector = ScenarioInjector()
    return app


# ---------------------------------------------------------------------------
# _is_chat_path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path,expected", [
    ("/agent/chat", True),
    ("/agent/chat/stream", True),
    ("/agent/scenarios/flight/chat", True),
    ("/agent/scenarios/flight/chat/stream", True),
    ("/agent/skills", False),
    ("/agent/pool", False),
    ("/health", False),
    ("/ready", False),
    ("/agent/scenarios", False),
    ("/agent/scenarios/flight", False),
])
def test_is_chat_path(path: str, expected: bool):
    assert ScenarioMiddleware._is_chat_path(path) is expected


# ---------------------------------------------------------------------------
# 拦截 + ctx 挂载
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_middleware_skips_non_chat_path(app_with_scenarios: Sanic):
    """非 chat 路径 middleware 不写 ctx."""
    mw = ScenarioMiddleware(app_with_scenarios)

    class _Req:
        path = "/agent/skills"
        body = b""
        json = None
        headers = {}
        class ctx:
            pass

    req = _Req()
    await mw(req)
    # ctx 上不应有 scenario / scenario_error
    assert not hasattr(req.ctx, "scenario")
    assert not hasattr(req.ctx, "scenario_error")


@pytest.mark.asyncio
async def test_middleware_sets_ctx_for_valid_request(app_with_scenarios: Sanic):
    """chat 请求被路由 + 注入 + 挂到 ctx."""
    mw = ScenarioMiddleware(app_with_scenarios)

    class _Req:
        path = "/agent/chat"
        body = b'{"message": "I want to book", "skills": ["book-flight", "extra"]}'
        json = {"message": "I want to book", "skills": ["book-flight", "extra"]}
        headers = {"content-type": "application/json"}
        class ctx:
            pass

    req = _Req()
    await mw(req)

    assert hasattr(req.ctx, "scenario")
    assert req.ctx.scenario.name == "flight"
    assert req.ctx.routing_context.matched_by == "keyword"
    assert "book-flight" in req.ctx.injection.final_skills
    assert "extra" in req.ctx.injection.rejected_skills
    assert not hasattr(req.ctx, "scenario_error")


@pytest.mark.asyncio
async def test_middleware_routes_url_scenario_path(app_with_scenarios: Sanic):
    """URL /agent/scenarios/<name>/chat 直接命中 URL 阶段."""
    mw = ScenarioMiddleware(app_with_scenarios)

    class _Req:
        path = "/agent/scenarios/flight/chat"
        body = b'{"message": "hello"}'
        json = {"message": "hello"}
        headers = {}
        class ctx:
            pass

    req = _Req()
    await mw(req)
    assert req.ctx.scenario.name == "flight"
    assert req.ctx.routing_context.matched_by == "url"


@pytest.mark.asyncio
async def test_middleware_routes_default_when_no_match(app_with_scenarios: Sanic):
    """没关键词命中 → 走 _default."""
    mw = ScenarioMiddleware(app_with_scenarios)

    class _Req:
        path = "/agent/chat"
        body = b'{"message": "hello"}'
        json = {"message": "hello"}
        headers = {}
        class ctx:
            pass

    req = _Req()
    await mw(req)
    assert req.ctx.scenario.name == "_default"
    assert req.ctx.routing_context.matched_by == "default"


# ---------------------------------------------------------------------------
# 失败 → ctx.scenario_error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_middleware_records_scenario_error_on_routing_failure(
    app_with_scenarios: Sanic,
):
    """所有优先级都失败 → ScenarioError 挂到 ctx."""
    # 把 default 也搞成不存在的, 强制失败
    bad_router = ScenarioRouter(
        app_with_scenarios.ctx.scenario_registry, default_scenario="nope"
    )
    app_with_scenarios.ctx.scenario_router = bad_router
    mw = ScenarioMiddleware(app_with_scenarios)

    class _Req:
        path = "/agent/chat"
        body = b'{"message": "hello"}'
        json = {"message": "hello"}
        headers = {}
        class ctx:
            pass

    req = _Req()
    await mw(req)
    assert hasattr(req.ctx, "scenario_error")
    assert isinstance(req.ctx.scenario_error, ScenarioError)
    assert req.ctx.scenario_error.code == "SCENARIO_NOT_FOUND"
    # 不应挂 scenario
    assert not hasattr(req.ctx, "scenario")


@pytest.mark.asyncio
async def test_middleware_records_scenario_error_when_injector_missing(
    app_with_scenarios: Sanic,
):
    """injector 未初始化 → ctx.scenario_error."""
    app_with_scenarios.ctx.scenario_injector = None
    mw = ScenarioMiddleware(app_with_scenarios)

    class _Req:
        path = "/agent/chat"
        body = b'{"message": "x"}'
        json = {"message": "x"}
        headers = {}
        class ctx:
            pass

    req = _Req()
    await mw(req)
    assert hasattr(req.ctx, "scenario_error")
    assert "not initialized" in str(req.ctx.scenario_error)


# ---------------------------------------------------------------------------
# 不破坏 chat 主路径
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_middleware_uses_live_ctx_router_after_reload(
    app_with_scenarios: Sanic,
):
    """middleware 每次从 app.ctx 读最新 router (支持 /agent/scenarios/reload)."""
    mw = ScenarioMiddleware(app_with_scenarios)

    # 注入一个新 router 到 ctx (模拟 reload)
    new_reg = ScenarioRegistry()
    new_reg.register(_scenario("new_scenario", keywords=["hot"]))
    new_reg.register(_scenario("_default"))
    app_with_scenarios.ctx.scenario_router = ScenarioRouter(
        new_reg, default_scenario="_default"
    )

    class _Req:
        path = "/agent/chat"
        body = b'{"message": "hot"}'
        json = {"message": "hot"}
        headers = {}
        class ctx:
            pass

    req = _Req()
    await mw(req)
    assert req.ctx.scenario.name == "new_scenario"
