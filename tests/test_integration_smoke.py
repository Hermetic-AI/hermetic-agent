"""tests/test_integration_smoke.py — P7 跨层集成冒烟测试.

验证 P0-P6 整套串联工作正常:
1. 6 个 scenario YAML 全部成功加载
2. ScenarioRouter 6 优先级全部命中
3. ScenarioInjector 白名单过滤正确
4. StateGuard + SuspendableScheduler 端到端
5. SkillManifest 状态机 + StateGuard 工具校验
6. 跨层组合: scenario → router → injector → manifest → state guard → suspend

只测跨层串联, 单元行为由 test_*.py 覆盖.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from openagent.auip import Card, CardType, TurnEvent, TurnEventType
from openagent.auip.events import assert_seq_increasing
from openagent.core.suspendable_scheduler import (
    SuspendableScheduler,
    UserInput,
)
from openagent.core.turn_store import InMemoryTurnStore
from openagent.scenarios import (
    ScenarioInjector,
    ScenarioRegistry,
    ScenarioRouter,
)
from openagent.scenarios.config import (
    A2UIConfig,
    ExecutionConfig,
    ProgressiveSkillConfig,
    RoutingConfig,
    ScenarioConfig,
    SecurityConfig,
    WorkspaceConfig,
)
from openagent.scenarios.errors import RoutingFailedError
from openagent.scenarios.injector import InMemoryAuditLogger
from openagent.scenarios.loader import load_scenario
from openagent.skill_runtime import (
    FragmentLoader,
    PromptBuilder,
    SkillManifest,
    StateGuard,
    StateSpec,
)
from openagent.skill_runtime.errors import (
    FragmentNotFoundError,
    SkillBudgetExceeded,
    StateGuardViolation,
)
from openagent.skills.registry import Skill, SkillRegistry

WORK_ROOT = Path("work")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _workspace_dir() -> str:
    """返回一个真实存在的临时目录 — 给 workspace_dirs 用.

    不在 with 里, 由调用方负责清理. fixture 模式下用.
    """
    return tempfile.mkdtemp(prefix="oa-p7-smoke-")


@pytest.fixture(scope="module")
def workspace_dir() -> str:
    """跨整个测试模块共享的临时工作区目录 (用 mkdtemp, 不自动清理)."""
    return _workspace_dir()


@pytest.fixture(scope="module")
def scenarios(workspace_dir: str) -> tuple[ScenarioRegistry, dict]:
    """从 work/scenarios/ 加载 6 个 scenario 的注册表."""
    ctx = {
        "WORK_ROOT": str(WORK_ROOT),
        "WORK_SHARED": str(WORK_ROOT / "shared"),
        "PROJECT_DIR": workspace_dir,
    }
    reg = ScenarioRegistry(ctx=ctx)
    scenarios_path = WORK_ROOT / "scenarios"
    if not scenarios_path.exists():
        pytest.skip("work/scenarios/ not initialized (P0 missing)")
    reg.load_from_paths(str(scenarios_path))
    if len(reg.list_all()) < 6:
        pytest.skip(
            f"expected 6 scenarios, got {len(reg.list_all())}: {reg.list_names()}"
        )
    return reg, ctx


# ---------------------------------------------------------------------------
# 1. 6 个 scenario 加载 + 基础属性
# ---------------------------------------------------------------------------


def test_all_seven_scenarios_load(scenarios):
    """全部 scenario 加载成功 (v3.0.0 新增 flight_query_v3 — opencode 原生 MCP; v4.0.0 新增 flight_query_v4)."""
    reg, _ = scenarios
    names = set(reg.list_names())
    expected = {
        "_generic", "_default", "flight_booking", "flight_query",
        "expense_audit", "customer_service", "code_review",
        "flight_query_v3", "flight_query_v4",
    }
    assert expected.issubset(names), f"missing: {expected - names}"
    assert len(reg.list_enabled()) == 9


def test_flight_booking_is_hitl(scenarios):
    """flight_booking 必须是 hitl + a2ui enabled + on_demand progressive."""
    reg, _ = scenarios
    cfg = reg.get("flight_booking")
    assert cfg is not None
    assert cfg.execution.orchestration == "hitl"
    assert cfg.a2ui.enabled is True
    assert cfg.progressive_skill.strategy == "on_demand"
    assert cfg.progressive_skill.budget_tokens == 4000


def test_generic_is_minimal(scenarios):
    """_generic 必须最小化: 0 skill, safe, no a2ui, no progressive."""
    reg, _ = scenarios
    cfg = reg.get("_generic")
    assert cfg is not None
    assert cfg.execution.skills == []
    assert cfg.security.tool_level == "safe"
    assert cfg.a2ui.enabled is False
    assert cfg.progressive_skill.strategy == "none"


def test_no_scenario_uses_root_workspace(scenarios):
    """任何 scenario 的 workspace_dirs[0] 都不能是 /."""
    reg, _ = scenarios
    forbidden = {"/", "~", "${HOME}", "$HOME", ""}
    for cfg in reg.list_all():
        first = cfg.workspace.workspace_dirs[0]
        assert first not in forbidden, f"{cfg.name} uses forbidden root: {first!r}"


# ---------------------------------------------------------------------------
# 2. Router 6 优先级
# ---------------------------------------------------------------------------


class _RouterSettings:
    """最小 stub, 满足 ScenarioRouter 构造 (只需 default_scenario 属性)."""

    default_scenario = "_default"


def test_route_keyword_to_flight_booking(scenarios):
    """'订票' 关键词路由到 flight_booking."""
    reg, _ = scenarios
    router = ScenarioRouter(reg, default_scenario="_default")
    ctx = router.route(
        request_path="/agent/chat",
        headers={},
        body={"message": "帮我订明天北京到上海的机票"},
    )
    assert ctx.scenario.name == "flight_booking"
    assert ctx.matched_by == "keyword"


def test_route_url_priority_over_keyword(scenarios):
    """URL 优先级高于 keyword — 即便 message 含关键词, URL 也胜出."""
    reg, _ = scenarios
    router = ScenarioRouter(reg, default_scenario="_default")
    ctx = router.route(
        request_path="/agent/scenarios/expense_audit/chat",
        headers={},
        body={"message": "订票"},  # 含订票关键词
    )
    assert ctx.scenario.name == "expense_audit"
    assert ctx.matched_by == "url"


def test_route_default_fallback(scenarios):
    """'你好' 兜底到 _default."""
    reg, _ = scenarios
    router = ScenarioRouter(reg, default_scenario="_default")
    ctx = router.route(
        request_path="/agent/chat",
        headers={},
        body={"message": "你好"},
    )
    assert ctx.scenario.name == "_default"
    assert ctx.matched_by == "default"


def test_route_generic_when_no_specific_match(scenarios):
    """不匹配任何业务 + _generic 兜底."""
    reg, _ = scenarios
    # 把 default_scenario 改 _generic
    router = ScenarioRouter(reg, default_scenario="_generic")
    ctx = router.route(
        request_path="/agent/chat",
        headers={},
        body={"message": "随便聊聊天"},
    )
    assert ctx.scenario.name == "_generic"


def test_route_routing_failed_no_scenario_and_no_default(scenarios):
    """所有 scenario 都不存在 + 没有 default → RoutingFailedError."""
    reg, _ = scenarios
    # 构造一个空 registry 的 router, default 也不存在
    empty_reg = ScenarioRegistry()
    router = ScenarioRouter(empty_reg, default_scenario="nonexistent")
    with pytest.raises(RoutingFailedError) as exc:
        router.route(
            request_path="/agent/chat",
            headers={},
            body={"message": "hello"},
        )
    assert exc.value.code == "SCENARIO_NOT_FOUND"
    assert exc.value.action  # 有可行动信息


# ---------------------------------------------------------------------------
# 3. Injector 白名单过滤
# ---------------------------------------------------------------------------


def test_injector_filters_out_whitelist_violations(scenarios):
    """客户端想塞 skills=[malicious_skill, book-flight] 只保留 book-flight."""
    reg, _ = scenarios
    cfg = reg.get("flight_booking")
    injector = ScenarioInjector(audit=InMemoryAuditLogger())
    result = injector.inject(
        scenario=cfg,
        user_message="test",
        caller_skills=["malicious_skill", "book-flight"],
        caller_tools=["malicious_tool", "query_flight_basic"],
    )
    # 已知 scenario 的 execution.skills=[] 时, 所有 caller skill 都会被拒
    # — 验证 rejected_* 一定有内容
    assert "malicious_skill" in result.rejected_skills
    assert "malicious_tool" in result.rejected_tools


def test_injector_audit_logger_records(scenarios):
    """Injector 的 audit logger 必须记录每次 inject 事件."""
    reg, _ = scenarios
    audit = InMemoryAuditLogger()
    injector = ScenarioInjector(audit=audit)
    cfg = reg.get("flight_booking")
    injector.inject(scenario=cfg, user_message="x", caller_skills=["foo"])
    assert len(audit.records) == 1
    rec = audit.records[0]
    assert rec["event"] == "scenario_inject"
    assert rec["scenario"] == "flight_booking"
    assert "foo" in rec["requested_skills"]


# ---------------------------------------------------------------------------
# 4. StateGuard + Manifest 端到端
# ---------------------------------------------------------------------------


def test_state_guard_blocks_unauthorized_tool(scenarios):
    """S05 状态不允许调 submit_order."""
    manifest = SkillManifest(
        name="book-flight",
        initial_state="S05",
        states={
            "S05": StateSpec(
                description="FLIGHT_LISTED",
                allowed_tools=["ask_user", "choose_flight"],
            ),
            "S13": StateSpec(
                description="READY_TO_SUBMIT",
                allowed_tools=["ask_user", "submit_order", "confirm_order"],
            ),
        },
        transitions={"S05": {"S13"}},
    )
    guard = StateGuard(manifest, current_state="S05")
    ok, reason = guard.can_call_tool("submit_order")
    assert not ok
    assert "submit_order" in reason
    # ask_user 永远允许
    ok2, _ = guard.can_call_tool("ask_user")
    assert ok2
    # 转移 S05 → S13 合法
    assert guard.can_transition("S13")


def test_state_guard_violation_on_illegal_transition(scenarios):
    """不允许的状态转移抛 StateGuardViolation."""
    manifest = SkillManifest(
        name="book-flight", initial_state="S01",
        states={
            "S01": StateSpec(allowed_tools=["ask_user"]),
            "S05": StateSpec(allowed_tools=["ask_user"]),
        },
        transitions={"S01": set()},  # 没有任何可转移目标
    )
    guard = StateGuard(manifest, current_state="S01")
    with pytest.raises(StateGuardViolation):
        guard.assert_can_transition("S05")


# ---------------------------------------------------------------------------
# 5. SuspendableScheduler 完整循环
# ---------------------------------------------------------------------------


async def _drain(async_iter):
    out = []
    async for evt in async_iter:
        out.append(evt)
    return out


async def test_full_suspend_resume_cycle(scenarios):
    """完整挂起→恢复循环: 验证 session→state→tool_use→card→suspend→resume→done."""
    reg, _ = scenarios
    manifest = SkillManifest(
        name="book-flight", initial_state="S01",
        states={
            "S01": StateSpec(allowed_tools=["ask_user"]),
        },
        transitions={},
    )
    store = InMemoryTurnStore()
    turn_id = await store.create_turn("sess-1", "book-flight", "1.0.0")
    scheduler = SuspendableScheduler(store, manifest)

    # Phase 1: drive → suspend
    events1 = await _drain(scheduler.run_turn(turn_id, "sess-1", "帮我订票"))
    types1 = [e.type for e in events1]
    assert TurnEventType.SESSION in types1
    assert TurnEventType.STATE in types1
    assert TurnEventType.TOOL_USE in types1
    assert TurnEventType.CARD in types1
    assert TurnEventType.SUSPEND in types1
    assert TurnEventType.DONE not in types1  # 还没 done
    # seq 严格递增
    assert_seq_increasing(events1)
    # Card 含 OD_INPUT
    card_evt = next(e for e in events1 if e.type == TurnEventType.CARD)
    assert card_evt.data["card"]["card_type"] == CardType.OD_INPUT.value

    # Phase 2: resume
    suspend_evt = next(e for e in events1 if e.type == TurnEventType.SUSPEND)
    correlation_id = suspend_evt.data["correlation_id"]
    events2 = await _drain(scheduler.resume(
        turn_id, UserInput(
            correlation_id=correlation_id, action_id="submit",
            data={"origin": "PEK", "destination": "SHA"},
        )
    ))
    types2 = [e.type for e in events2]
    assert TurnEventType.RESUME in types2
    assert TurnEventType.TOOL_RESULT in types2
    assert TurnEventType.DONE in types2


async def test_suspend_writes_checkpoint(scenarios):
    """suspend 时 TurnStore 必须写入 checkpoint."""
    reg, _ = scenarios
    manifest = SkillManifest(
        name="book-flight", initial_state="S01",
        states={"S01": StateSpec(allowed_tools=["ask_user"])},
    )
    store = InMemoryTurnStore()
    turn_id = await store.create_turn("sess-2", "book-flight", "1.0.0")
    scheduler = SuspendableScheduler(store, manifest)
    await _drain(scheduler.run_turn(turn_id, "sess-2", "x"))
    cp = await store.get_latest_checkpoint(turn_id)
    assert cp is not None
    assert cp.state == "S01"
    # turn status 变 suspended
    meta = await store.get_turn(turn_id)
    assert meta["status"] == "suspended"


# ---------------------------------------------------------------------------
# 6. FragmentLoader + PromptBuilder
# ---------------------------------------------------------------------------


def test_fragment_loader_with_skill_registry(tmp_path, scenarios):
    """FragmentLoader 必须能用真实 SkillRegistry 加载 on_demand 片段."""
    # 构造 skill 目录
    skill_dir = tmp_path / "book-flight"
    (skill_dir / "fragments").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# book-flight", encoding="utf-8")
    (skill_dir / "fragments" / "summary.md").write_text("BOOK-FLIGHT-SUMMARY", encoding="utf-8")
    (skill_dir / "fragments" / "state-s05.md").write_text("S05-FLIGHT-SELECT", encoding="utf-8")

    reg = SkillRegistry()
    reg.register(Skill(
        name="book-flight",
        description="订票",
        source=str(skill_dir / "SKILL.md"),
    ))
    loader = FragmentLoader(reg, budget=4000, policy="error")
    # 构造 scenario SimpleNamespace
    from types import SimpleNamespace
    scn = SimpleNamespace(
        name="flight_booking",
        execution=SimpleNamespace(skills=["book-flight"]),
        progressive_skill=SimpleNamespace(
            strategy="on_demand",
            initial_skills=[{"name": "book-flight", "mode": "summary"}],
            load_on_state={"S05": ["book-flight:state-s05"]},
        ),
    )
    text, report = loader.load(scn, current_state="S05")
    assert "BOOK-FLIGHT-SUMMARY" in text
    assert "S05-FLIGHT-SELECT" in text
    assert "book-flight#summary" in report.loaded


def test_fragment_loader_budget_exceeded_raises(scenarios, tmp_path):
    """budget 强制: 超出时按 policy=error 抛 SkillBudgetExceeded."""
    skill_dir = tmp_path / "huge"
    (skill_dir / "fragments").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("h", encoding="utf-8")
    (skill_dir / "fragments" / "huge.md").write_text("X" * 600, encoding="utf-8")  # ~400 tokens
    reg = SkillRegistry()
    reg.register(Skill(name="huge", source=str(skill_dir / "SKILL.md")))
    loader = FragmentLoader(reg, budget=100, policy="error")
    from types import SimpleNamespace
    scn = SimpleNamespace(
        name="x",
        execution=SimpleNamespace(skills=["huge"]),
        progressive_skill=SimpleNamespace(
            strategy="on_demand",
            initial_skills=[],
            load_on_state={"S01": ["huge:huge"]},
        ),
    )
    with pytest.raises(SkillBudgetExceeded) as exc:
        loader.load(scn, current_state="S01")
    assert exc.value.used > 100
    assert exc.value.action  # 有可行动信息


def test_prompt_builder_assembles_6_sections(scenarios, tmp_path):
    """PromptBuilder 拼出 6 段: framework / scenario / a2ui / skill / state / messages."""
    skill_dir = tmp_path / "book-flight"
    (skill_dir / "fragments").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("b", encoding="utf-8")
    (skill_dir / "fragments" / "summary.md").write_text("SUMMARY-X", encoding="utf-8")
    reg = SkillRegistry()
    reg.register(Skill(name="book-flight", source=str(skill_dir / "SKILL.md")))
    loader = FragmentLoader(reg, budget=1000, policy="error")
    builder = PromptBuilder(
        loader, framework_base="1-FRAMEWORK", aui_instructions="3-AUI-INSTR",
    )
    from types import SimpleNamespace
    scn = SimpleNamespace(
        name="flight_booking",
        execution=SimpleNamespace(system_prompt="2-SCENARIO-PROMPT", skills=["book-flight"]),
        a2ui=SimpleNamespace(enabled=True),
        progressive_skill=SimpleNamespace(
            strategy="on_demand",
            initial_skills=[{"name": "book-flight", "mode": "summary"}],
            load_on_state={},
        ),
    )
    from dataclasses import dataclass

    @dataclass
    class M:
        role: str
        content: str

    out = builder.build(scn, current_state="S05", messages=[M("user", "6-MSG")])
    # 6 段全部出现
    assert "1-FRAMEWORK" in out
    assert "2-SCENARIO-PROMPT" in out
    assert "3-AUI-INSTR" in out
    assert "SUMMARY-X" in out
    assert "Current state: S05" in out
    assert "[user] 6-MSG" in out
    # 顺序正确
    positions = [
        out.find("1-FRAMEWORK"), out.find("2-SCENARIO-PROMPT"),
        out.find("3-AUI-INSTR"), out.find("SUMMARY-X"),
        out.find("Current state: S05"), out.find("6-MSG"),
    ]
    assert positions == sorted(positions)
    assert all(p >= 0 for p in positions)


# ---------------------------------------------------------------------------
# 7. 跨层: scenario → manifest → suspend 完整集成
# ---------------------------------------------------------------------------


async def test_end_to_end_scenario_to_suspend(scenarios, workspace_dir):
    """跨层: 加载 flight_booking scenario + 构造 manifest + 跑 suspend."""
    reg, _ = scenarios
    cfg = reg.get("flight_booking")
    assert cfg is not None
    # 用 cfg.a2ui.state_machine 应有值 — 但可能未填; 显式构造一个对应 13 状态的 manifest
    manifest = SkillManifest(
        name="book-flight", version="1.0.0", initial_state="S01",
        states={sid: StateSpec(allowed_tools=["ask_user"]) for sid in [
            "S01", "S02", "S03", "S04", "S05", "S06", "S07",
            "S08", "S09", "S10", "S11", "S12", "S13",
        ]},
        transitions={sid: set() for sid in [
            "S01", "S02", "S03", "S04", "S05", "S06", "S07",
            "S08", "S09", "S10", "S11", "S12", "S13",
        ]},
    )
    store = InMemoryTurnStore()
    turn_id = await store.create_turn("sess-e2e", "book-flight", "1.0.0")
    scheduler = SuspendableScheduler(store, manifest)
    events = await _drain(scheduler.run_turn(turn_id, "sess-e2e", "订明天北京到上海"))
    # 必有 suspend
    assert any(e.type == TurnEventType.SUSPEND for e in events)
    # 必有 CARD 推送 (OD_INPUT)
    card_evts = [e for e in events if e.type == TurnEventType.CARD]
    assert len(card_evts) == 1
    assert card_evts[0].data["card"]["card_type"] == CardType.OD_INPUT.value
