"""ScenarioRouter 单测 — 6 优先级路由."""

from __future__ import annotations

import pytest

from openagent.scenarios.config import (
    ExecutionConfig,
    RoutingConfig,
    ScenarioConfig,
    WorkspaceConfig,
)
from openagent.scenarios.errors import (
    RoutingFailedError,
    ScenarioDisabledError,
)
from openagent.scenarios.registry import ScenarioRegistry
from openagent.scenarios.router import ScenarioRouter


def _cfg(name: str, *, keywords: list[str] | None = None, priority: int = 100, enabled: bool = True) -> ScenarioConfig:
    return ScenarioConfig(
        name=name,
        version="1.0.0",
        enabled=enabled,
        routing=RoutingConfig(
            trigger_keywords=keywords or [],
            priority=priority,
        ),
        execution=ExecutionConfig(skills=[], tools=[]),
        workspace=WorkspaceConfig(workspace_dirs=["/tmp/proj"]),
        progressive_skill={"strategy": "none"},  # type: ignore[arg-type]
    )


@pytest.fixture
def reg() -> ScenarioRegistry:
    r = ScenarioRegistry()
    r.register(_cfg("flight", keywords=["订票", "机票"], priority=50))
    r.register(_cfg("expense", keywords=["报销", "审核"], priority=80))
    r.register(_cfg("code", keywords=["code review"], priority=70))
    r.register(_cfg("_default"))
    r.register(_cfg("disabled_one", keywords=["测试"], priority=10, enabled=False))
    return r


@pytest.fixture
def router(reg: ScenarioRegistry) -> ScenarioRouter:
    return ScenarioRouter(reg, default_scenario="_default")


# ----------------------------------------------------------------------
# 1. URL
# ----------------------------------------------------------------------


def test_route_url_path_match(router: ScenarioRouter):
    ctx = router.route("/agent/scenarios/flight/chat", body={"message": "你好"})
    assert ctx.scenario.name == "flight"
    assert ctx.matched_by == "url"


def test_route_url_no_match(router: ScenarioRouter):
    ctx = router.route("/agent/scenarios/nonexistent/chat", body={"message": "x"})
    # 找不到 → 走到 keyword/default
    assert ctx.scenario.name == "_default"


def test_route_url_partial_no_match(router: ScenarioRouter):
    ctx = router.route("/agent/scenarios/flight/", body={"message": "x"})
    # 末尾没有 /chat → URL 不命中
    assert ctx.matched_by != "url"


# ----------------------------------------------------------------------
# 2. Header
# ----------------------------------------------------------------------


def test_route_header_match(router: ScenarioRouter):
    ctx = router.route(
        "/agent/chat",
        headers={"X-Scenario": "expense"},
        body={"message": "随便说"},
    )
    assert ctx.scenario.name == "expense"
    assert ctx.matched_by == "header"


# ----------------------------------------------------------------------
# 3. Body
# ----------------------------------------------------------------------


def test_route_body_match(router: ScenarioRouter):
    ctx = router.route(
        "/agent/chat",
        body={"scenario": "code", "message": "review this"},
    )
    assert ctx.scenario.name == "code"
    assert ctx.matched_by == "body"


def test_route_body_scenario_takes_precedence_over_keyword(router: ScenarioRouter):
    """body.scenario 优先级高于 keyword."""
    ctx = router.route(
        "/agent/chat",
        body={"scenario": "code", "message": "订票 北京"},
    )
    assert ctx.scenario.name == "code"
    assert ctx.matched_by == "body"


# ----------------------------------------------------------------------
# 4. Keyword
# ----------------------------------------------------------------------


def test_route_keyword_match(router: ScenarioRouter):
    ctx = router.route("/agent/chat", body={"message": "我要订票"})
    assert ctx.scenario.name == "flight"
    assert ctx.matched_by == "keyword"


def test_route_keyword_no_match_falls_to_default(router: ScenarioRouter):
    ctx = router.route("/agent/chat", body={"message": "今天天气真好"})
    assert ctx.scenario.name == "_default"
    assert ctx.matched_by == "default"


def test_route_keyword_disabled_scenario_skipped(router: ScenarioRouter):
    """disabled_one 的关键词 '测试' 不应被命中."""
    ctx = router.route("/agent/chat", body={"message": "这是一个测试"})
    # 唯一 keyword 命中的是 disabled_one, 被跳过
    assert ctx.scenario.name != "disabled_one"
    assert ctx.matched_by == "default"
    # rejected 应该包含 disabled_one
    rejected_names = [c.name for c, _ in ctx.rejected]
    assert "disabled_one" in rejected_names


def test_route_priority_within_keyword(router: ScenarioRouter):
    """多个 scenario 命中同一关键词 → priority 升序胜出."""
    # 假设: 临时插入一个更高 priority 的 flight2
    router._registry.register(
        _cfg("flight_premium", keywords=["订票"], priority=10)
    )
    ctx = router.route("/agent/chat", body={"message": "我想订票"})
    assert ctx.scenario.name == "flight_premium"


def test_route_keyword_score_higher_wins(router: ScenarioRouter):
    """同 priority 时, 命中关键词数多的胜出."""
    router._registry.register(
        _cfg("multi_match", keywords=["订票", "机票", "航班"], priority=50)
    )
    # multi_match 命中 3 个关键词, flight 只命中 2 个 → multi_match 胜
    ctx = router.route("/agent/chat", body={"message": "订票 机票 航班"})
    assert ctx.scenario.name == "multi_match"


# ----------------------------------------------------------------------
# 5. Intent (stub, 默认关闭)
# ----------------------------------------------------------------------


def test_route_intent_stub_disabled(router: ScenarioRouter):
    # 默认 enable_intent_router=False, intent 阶段什么都不做
    ctx = router.route("/agent/chat", body={"message": "anything"})
    assert ctx.matched_by in ("keyword", "default")


# ----------------------------------------------------------------------
# 6. Default
# ----------------------------------------------------------------------


def test_route_default_fallback(router: ScenarioRouter):
    ctx = router.route("", body={})
    assert ctx.scenario.name == "_default"
    assert ctx.matched_by == "default"


# ----------------------------------------------------------------------
# 失败
# ----------------------------------------------------------------------


def test_route_all_fail_raises():
    """所有优先级都失败 → RoutingFailedError (default 也找不到)."""
    reg = ScenarioRegistry()
    router = ScenarioRouter(reg, default_scenario="nope")
    with pytest.raises(RoutingFailedError):
        router.route("/agent/chat", body={"message": "随便"})


def test_route_disabled_via_url_raises(reg: ScenarioRegistry):
    """URL 命中一个 disabled scenario → ScenarioDisabledError."""
    router = ScenarioRouter(reg, default_scenario="_default")
    with pytest.raises(ScenarioDisabledError):
        router.route("/agent/scenarios/disabled_one/chat")


# ----------------------------------------------------------------------
# RoutingContext
# ----------------------------------------------------------------------


def test_routing_context_to_dict(router: ScenarioRouter):
    ctx = router.route("/agent/chat", body={"message": "订票"})
    d = ctx.to_dict()
    assert d["scenario_name"] == "flight"
    assert d["matched_by"] == "keyword"
    assert isinstance(d["candidate_names"], list)
