"""Scenario 5 个最关键场景烟雾测试 — 加载所有现有 scenario + 路由 + 注入.

跑通 5 个核心场景:
1. 加载 _generic + _default 两个 scenario YAML
2. 加载一个临时构造的 keyword scenario
3. 路由 URL / Header / Body / Keyword / Default 全链路
4. 注入白名单 + 拒绝记录
5. 资源缺失 → ScenarioResourceError
"""

from __future__ import annotations

from pathlib import Path

import pytest

from openagent.scenarios import (
    InMemoryAuditLogger,
    ScenarioConfig,
    ScenarioInjector,
    ScenarioRegistry,
    ScenarioRouter,
)
from openagent.scenarios.config import (
    ExecutionConfig,
    ProgressiveSkillConfig,
    RoutingConfig,
    WorkspaceConfig,
)
from openagent.scenarios.errors import ScenarioResourceError
from openagent.scenarios.loader import load_scenario

WORK_DIR = Path(__file__).resolve().parents[1] / "work"


def _ctx() -> dict[str, str]:
    return {
        "PROJECT_DIR": str(WORK_DIR),
        "WORK_SHARED": str(WORK_DIR / "shared"),
        "WORK_ROOT": str(WORK_DIR),
        "SCENARIO_DIR": str(WORK_DIR / "scenarios" / "_generic"),
    }


def _kw_scenario(name: str, kw: list[str], skills: list[str] | None = None, priority: int = 50) -> ScenarioConfig:
    return ScenarioConfig(
        name=name,
        version="1.0.0",
        routing=RoutingConfig(priority=priority, trigger_keywords=kw),
        execution=ExecutionConfig(
            system_prompt=f"PROMPT_FOR_{name}",
            skills=skills or ["book-flight"],
            tools=["query_flight", "submit_order"],
            orchestration="single",
        ),
        workspace=WorkspaceConfig(workspace_dirs=["/tmp/proj"]),
        progressive_skill=ProgressiveSkillConfig(strategy="none"),
    )


# ----------------------------------------------------------------------
# 1. 加载 _generic + _default + 1 个临时 keyword scenario
# ----------------------------------------------------------------------


def test_smoke_load_six_scenarios():
    reg = ScenarioRegistry(ctx=_ctx())
    reg.load_from_paths(WORK_DIR / "scenarios")
    reg.register(_kw_scenario("flight", ["订票", "机票"]))
    reg.register(_kw_scenario("expense", ["报销", "审核"]))
    reg.register(_kw_scenario("code_review", ["review"], priority=70))
    reg.register(_kw_scenario("customer_service", ["客服"], priority=60))

    names = set(reg.list_names())
    # P0/P7 YAMLs: _generic, _default, flight_booking, expense_audit, code_review, customer_service
    # P2 in-test: flight, expense, code_review, customer_service (override同名YAML)
    expected = {
        "_generic", "_default", "flight_booking", "expense_audit",
        "flight", "expense",
    }
    assert expected.issubset(names), f"missing: {expected - names}"
    assert len(reg.list_enabled()) >= 6


# ----------------------------------------------------------------------
# 2. 6 优先级路由全链路
# ----------------------------------------------------------------------


def test_smoke_route_keyword_hit():
    reg = ScenarioRegistry(ctx=_ctx())
    reg.load_from_paths(WORK_DIR / "scenarios")
    reg.register(_kw_scenario("flight", ["订票", "机票"], priority=50))
    reg.register(_kw_scenario("expense", ["报销"], priority=80))
    router = ScenarioRouter(reg, default_scenario="_default")

    # Keyword 命中 flight
    c = router.route(body={"message": "我要订票"})
    assert c.scenario.name == "flight"
    assert c.matched_by == "keyword"


def test_smoke_route_url_body_header():
    reg = ScenarioRegistry(ctx=_ctx())
    reg.load_from_paths(WORK_DIR / "scenarios")
    reg.register(_kw_scenario("flight", ["订票"]))
    router = ScenarioRouter(reg, default_scenario="_default")

    # URL
    c = router.route("/agent/scenarios/flight/chat", body={"message": "x"})
    assert c.scenario.name == "flight"
    assert c.matched_by == "url"

    # Header
    c = router.route("", headers={"X-Scenario": "flight"}, body={"message": "x"})
    assert c.scenario.name == "flight"
    assert c.matched_by == "header"

    # Body
    c = router.route("", body={"scenario": "flight", "message": "x"})
    assert c.scenario.name == "flight"
    assert c.matched_by == "body"


def test_smoke_route_default_fallback():
    reg = ScenarioRegistry(ctx=_ctx())
    reg.load_from_paths(WORK_DIR / "scenarios")
    router = ScenarioRouter(reg, default_scenario="_default")
    c = router.route(body={"message": "今天天气"})
    assert c.scenario.name == "_default"
    assert c.matched_by == "default"


# ----------------------------------------------------------------------
# 3. 注入白名单 + 拒绝
# ----------------------------------------------------------------------


def test_smoke_inject_whitelist_intersection():
    reg = ScenarioRegistry()
    reg.register(
        _kw_scenario("flight", ["订票"], skills=["book-flight", "policy-check"])
    )
    flight = reg.get("flight")
    assert flight is not None

    inj = ScenarioInjector(audit=InMemoryAuditLogger())
    result = inj.inject(
        flight,
        user_message="订票",
        caller_skills=["book-flight", "spam-skill"],
        caller_tools=["query_flight", "hack_tool"],
        caller_system_prompt="附加提示",
    )

    # 白名单交集
    assert result.final_skills == ["book-flight"]
    assert result.final_tools == ["query_flight"]
    # 多余项被拒
    assert "spam-skill" in result.rejected_skills
    assert "hack_tool" in result.rejected_tools
    # 提示词追加
    assert "PROMPT_FOR_flight" in result.final_system_prompt
    assert "附加提示" in result.final_system_prompt
    # system_prompt: scenario 自己的在前, caller 的在后
    assert result.final_system_prompt.index("PROMPT_FOR_flight") < result.final_system_prompt.index("附加提示")


# ----------------------------------------------------------------------
# 4. 资源缺失 → ScenarioResourceError
# ----------------------------------------------------------------------


def test_smoke_missing_resource_raises(tmp_path: Path):
    yaml_text = f"""
name: needs_cards
version: "1.0.0"
routing: {{priority: 100}}
execution: {{orchestration: hitl, skills: []}}
workspace: {{workspace_dirs: ["{tmp_path.as_posix()}"]}}
a2ui: {{enabled: true, cards_dir: "{tmp_path.as_posix()}/nonexistent_cards"}}
progressive_skill: {{strategy: none}}
"""
    p = tmp_path / "bad.scenario.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    with pytest.raises(ScenarioResourceError) as ei:
        load_scenario(p, {})
    assert ei.value.missing
    assert any("nonexistent_cards" in m for m in ei.value.missing)


# ----------------------------------------------------------------------
# 5. _generic 必须最小化
# ----------------------------------------------------------------------


def test_smoke_generic_is_minimal():
    cfg = load_scenario(WORK_DIR / "scenarios" / "_generic.scenario.yaml", _ctx())
    assert cfg.name == "_generic"
    assert cfg.security.tool_level == "safe"
    assert cfg.a2ui.enabled is False
    assert cfg.execution.skills == []
    assert cfg.execution.tools == []
    assert cfg.progressive_skill.strategy == "none"
    assert cfg.enabled is True


# ----------------------------------------------------------------------
# 6. (Bonus) 全部 6 个 scenario 在路由行为上的端到端验证
# ----------------------------------------------------------------------


def test_smoke_full_pipeline_e2e():
    reg = ScenarioRegistry(ctx=_ctx())
    reg.load_from_paths(WORK_DIR / "scenarios")
    reg.register(_kw_scenario("flight", ["订票"], priority=10))
    reg.register(_kw_scenario("expense", ["报销"], priority=20))
    router = ScenarioRouter(reg, default_scenario="_default")
    inj = ScenarioInjector(audit=InMemoryAuditLogger())

    # 流程: 用户发 "订票" → 路由到 flight → 注入 skills/tools
    ctx_route = router.route(body={"message": "我要订票"})
    assert ctx_route.scenario.name == "flight"
    inj_result = inj.inject(
        ctx_route.scenario,
        user_message="我要订票",
        caller_skills=["book-flight", "extra"],
        caller_tools=["query_flight"],
    )
    assert "book-flight" in inj_result.final_skills
    assert "extra" in inj_result.rejected_skills
