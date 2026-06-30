"""Scenario 核心场景烟雾测试 — 加载所有现有 scenario + 路由 + 注入.

跑通核心场景:
1. 加载 _default + example_echo 两个 scenario YAML (基座默认 + 业务示例)
2. 加载一个临时构造的 keyword scenario
3. 路由 URL / Header / Body / Keyword / Default 全链路
4. 注入白名单 + 拒绝记录
5. 资源校验分层: workspace_dirs / a2ui.state_machine / 技能 SKILL.md 缺失
   仍抛 ScenarioResourceError; readonly_dirs / a2ui.cards_dir 缺失只打
   warning, 场景照常加载.

Phase 1 重构后: 业务场景 (flight_booking / expense_audit / _generic) 全部
下沉到 work/shared/skills/<skill-name>/, 基座 work/scenarios/ 只剩
_default + example_echo 两个.
"""

from __future__ import annotations

from pathlib import Path

from hermetic_agent.scenarios import (
    InMemoryAuditLogger,
    ScenarioConfig,
    ScenarioInjector,
    ScenarioRegistry,
    ScenarioRouter,
)
from hermetic_agent.scenarios.config import (
    ExecutionConfig,
    ProgressiveSkillConfig,
    RoutingConfig,
    WorkspaceConfig,
)
from hermetic_agent.scenarios.loader import load_scenario

WORK_DIR = Path(__file__).resolve().parents[1] / "work"


def _ctx() -> dict[str, str]:
    return {
        "PROJECT_DIR": str(WORK_DIR),
        "WORK_SHARED": str(WORK_DIR / "shared"),
        "WORK_ROOT": str(WORK_DIR),
        "SCENARIO_DIR": str(WORK_DIR / "scenarios" / "example_echo"),
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
# 1. 加载 _default + example_echo + 1 个临时 keyword scenario
# ----------------------------------------------------------------------


def test_smoke_load_six_scenarios():
    reg = ScenarioRegistry(ctx=_ctx())
    reg.load_from_paths(WORK_DIR / "scenarios")
    reg.register(_kw_scenario("flight", ["订票", "机票"]))
    reg.register(_kw_scenario("expense", ["报销", "审核"]))
    reg.register(_kw_scenario("code_review", ["review"], priority=70))
    reg.register(_kw_scenario("customer_service", ["客服"], priority=60))

    names = set(reg.list_names())
    # 基座 YAMLs: _default, example_echo
    # in-test: flight, expense, code_review, customer_service
    expected = {
        "_default", "example_echo",
        "flight", "expense",
    }
    assert expected.issubset(names), f"missing: {expected - names}"
    assert len(reg.list_enabled()) >= 4


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
# 4. 资源校验分层 — 软硬分开
# ----------------------------------------------------------------------


def test_smoke_missing_cards_dir_only_warns(tmp_path: Path):
    """a2ui.cards_dir 缺失 → 软警告, 场景照常加载 (新契约).

    旧契约是抛 ScenarioResourceError, 但这会让 ``work/shared/docs`` 还没
    落盘的客户连 reload 都返回 0. 现在 cards_dir / readonly_dirs 都算
    可选能力, 不再阻断加载.
    """
    yaml_text = f"""
name: needs_cards
version: "1.0.0"
routing: {{priority: 100}}
execution: {{orchestration: single, skills: []}}
workspace: {{workspace_dirs: ["{tmp_path.as_posix()}"]}}
a2ui: {{enabled: true, cards_dir: "{tmp_path.as_posix()}/nonexistent_cards"}}
progressive_skill: {{strategy: none}}
"""
    p = tmp_path / "ok.scenario.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    cfg = load_scenario(p, {})  # 不抛错
    assert cfg.name == "needs_cards"


# ----------------------------------------------------------------------
# 5. _default 必须最小化
# ----------------------------------------------------------------------


def test_smoke_default_is_minimal():
    cfg = load_scenario(WORK_DIR / "scenarios" / "_default.scenario.yaml", _ctx())
    assert cfg.name == "_default"
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
