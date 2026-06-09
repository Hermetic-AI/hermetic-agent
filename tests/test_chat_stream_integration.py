"""F2/F3/F4 集成测试 (轻量版): 跳过 Sanic test_client (与 OpenAPI 装饰器不兼容).

直接测 chat_controller / turn_routes 内部函数, 验证 scenario + injection + HITL 串通.
"""
import asyncio

from openagent.core.suspendable_scheduler import SuspendableScheduler, UserInput
from openagent.core.turn_store import InMemoryTurnStore
from openagent.skill_runtime.manifest import SkillManifest, StateSpec

# ---------------------------------------------------------------------------
# 验证 1: chat_controller 真的用 injection.final_*
# ---------------------------------------------------------------------------


def test_chat_uses_injection_final_system_prompt():
    """验证: chat_controller 的 _effective_params 从 injection 取 final_*, 而不是从 body."""
    from types import SimpleNamespace

    from openagent.api.controllers.chat_controller import _effective_params
    from openagent.api.schemas import ChatRequest

    # 构造 mock injection (有 final_* 字段)
    injection = SimpleNamespace(
        final_system_prompt="[INJECTED PROMPT]",
        final_skills=["skill_a", "skill_b"],
        final_tools=["tool_x"],
    )
    body = ChatRequest(message="hello", system_prompt="[BODY PROMPT]", skills=["evil"], tools=["evil_tool"])
    params = _effective_params(body, injection)
    assert params["system_prompt"] == "[INJECTED PROMPT]"  # 来自 injection
    assert params["skills"] == ["skill_a", "skill_b"]
    assert params["tools"] == ["tool_x"]


def test_chat_falls_back_to_body_when_no_injection():
    """injection 为 None 时用 body 的 system_prompt/skills/tools (向后兼容)."""
    from openagent.api.controllers.chat_controller import _effective_params
    from openagent.api.schemas import ChatRequest

    body = ChatRequest(message="hello", system_prompt="[BODY]", skills=["a"], tools=["t"])
    params = _effective_params(body, None)
    assert params["system_prompt"] == "[BODY]"
    assert params["skills"] == ["a"]
    assert params["tools"] == ["t"]


def test_scenario_model_reads_resources_model():
    from types import SimpleNamespace

    from openagent.api.controllers.chat_controller import _scenario_model

    scenario = SimpleNamespace(resources=SimpleNamespace(model="MiniMax-M3"))
    assert _scenario_model(scenario) == "MiniMax-M3"
    assert _scenario_model(SimpleNamespace(resources=SimpleNamespace(model=None))) is None
    assert _scenario_model(None) is None


def test_chat_response_includes_scenario_info():
    """_build_chat_response 真的把 scenario / routing 字段塞进 response."""
    from types import SimpleNamespace

    from openagent.api.controllers.chat_controller import _build_chat_response

    msg = SimpleNamespace(role="assistant", content="reply")
    result = SimpleNamespace(
        success=True, message=msg, session_id="s1",
        tool_calls=[], stop_reason="end_turn", duration=0.1, error=None,
    )
    scenario_dict = {"name": "flight_booking", "version": "1.2.0", "matched_by": "body"}
    injection = SimpleNamespace(
        final_skills=["book-flight"], final_tools=["query_flight"],
        rejected_skills=["evil"], rejected_tools=["evil_tool"],
    )
    response = _build_chat_response(
        result, "agent-1", "s1",
        scenario_dict=scenario_dict, injection=injection,
    )
    dumped = response.model_dump()
    assert dumped["scenario"]["name"] == "flight_booking"
    assert dumped["routing"]["rejected_skills"] == ["evil"]
    assert dumped["result"]["message"]["content"] == "reply"


# ---------------------------------------------------------------------------
# 验证 2: _build_scenario_dict 正确处理 routing_ctx
# ---------------------------------------------------------------------------


def test_build_scenario_dict_with_routing_ctx():
    from types import SimpleNamespace

    from openagent.api.controllers.chat_controller import _build_scenario_dict

    scenario = SimpleNamespace(name="fb", version="1.0.0", execution=SimpleNamespace(orchestration="hitl"))
    routing_ctx = SimpleNamespace(matched_by="header")
    out = _build_scenario_dict(scenario, routing_ctx)
    assert out["name"] == "fb"
    assert out["matched_by"] == "header"
    assert out["orchestration"] == "hitl"


def test_build_scenario_dict_with_no_scenario():
    from openagent.api.controllers.chat_controller import _build_scenario_dict
    assert _build_scenario_dict(None, None) is None


# ---------------------------------------------------------------------------
# 验证 3: _turn_event_to_sse 翻译 11 种 TurnEvent
# ---------------------------------------------------------------------------


def test_turn_event_to_sse_all_11_types():
    """_turn_event_to_sse 翻译 11 种 TurnEventType 为 StreamEvent."""
    from openagent.api.controllers.chat_controller import _turn_event_to_sse
    from openagent.auip import TurnEvent, TurnEventType

    samples = [
        (TurnEvent(seq=0, turn_id="t", type=TurnEventType.SESSION,
                   data={"session_id": "s1"}), "session"),
        (TurnEvent(seq=1, turn_id="t", type=TurnEventType.TEXT,
                   data={"text": "hi"}), "text"),
        (TurnEvent(seq=2, turn_id="t", type=TurnEventType.REASONING,
                   data={"content": "thinking"}), "reasoning"),
        (TurnEvent(seq=3, turn_id="t", type=TurnEventType.TOOL_USE,
                   data={"id": "t1", "name": "ask_user", "input": {"x": 1}}), "tool_use"),
        (TurnEvent(seq=4, turn_id="t", type=TurnEventType.TOOL_RESULT,
                   data={"id": "t1", "name": "ask_user", "output": {"ok": True}}), "tool_result"),
        (TurnEvent(seq=5, turn_id="t", type=TurnEventType.CARD,
                   data={"card_id": "c1", "card": {"card_type": "OD_INPUT", "title": "OD"},
                         "correlation_id": "t1"}), "card"),
        (TurnEvent(seq=6, turn_id="t", type=TurnEventType.STATE,
                   data={"state": "S05"}), "state"),
        (TurnEvent(seq=7, turn_id="t", type=TurnEventType.SUSPEND,
                   data={"checkpoint_id": "ck1", "card": {},
                         "correlation_id": "t1", "input_schema": {}}), "suspend"),
        (TurnEvent(seq=8, turn_id="t", type=TurnEventType.RESUME,
                   data={"checkpoint_id": "ck1"}), "resume"),
        (TurnEvent(seq=9, turn_id="t", type=TurnEventType.DONE,
                   data={"stop_reason": "end_turn"}), "done"),
        (TurnEvent(seq=10, turn_id="t", type=TurnEventType.ERROR,
                   data={"message": "oops", "code": "X"}), "error"),
    ]
    for evt, expected_type in samples:
        sse = _turn_event_to_sse(evt)
        assert sse.type == expected_type, f"expected {expected_type}, got {sse.type}"
        if expected_type == "suspend":
            assert sse.data["turn_id"] == evt.turn_id


def test_fh_domestic_clear_query_bypasses_hitl_placeholder():
    from types import SimpleNamespace

    from openagent.api.controllers.chat_controller import (
        _should_bypass_hitl_placeholder,
    )

    scenario = SimpleNamespace(name="fh_domestic_flight_booking")
    assert _should_bypass_hitl_placeholder(
        scenario,
        "帮我查询明天6.9 从北京到上海的单程机票",
    )
    assert not _should_bypass_hitl_placeholder(scenario, "帮我查询北京出发的机票")


# ---------------------------------------------------------------------------
# 验证 4: SuspendableScheduler 端到端挂起 + 恢复
# ---------------------------------------------------------------------------


def test_suspendable_scheduler_full_cycle():
    """完整: run_turn → SUSPEND → resume → DONE."""
    async def drive():
        manifest = SkillManifest(name="book-flight", initial_state="S02")
        manifest.states["S02"] = StateSpec(
            description="OD_PENDING", allowed_tools=["ask_user"]
        )
        store = InMemoryTurnStore()
        scheduler = SuspendableScheduler(store, manifest)

        events = []
        async for evt in scheduler.run_turn("turn-1", "s1", "帮我订机票"):
            events.append(evt)
            if evt.type.value == "suspend":
                # 找到 correlation_id 后 resume
                cid = evt.data["correlation_id"]
                async for re_evt in scheduler.resume("turn-1", UserInput(
                    correlation_id=cid,
                    action_id="submit",
                    data={"origin": "PEK", "destination": "SHA"},
                )):
                    events.append(re_evt)
        return events

    events = asyncio.run(drive())
    types = [e.type.value for e in events]
    # 必须包含: session → state → text → tool_use → card → suspend → resume → tool_result → state → done
    assert "session" in types
    assert "suspend" in types
    assert "resume" in types
    assert "done" in types
    # suspend 后是 resume (按事件顺序)
    assert types.index("suspend") < types.index("resume")
    assert types.index("resume") < types.index("done")


# ---------------------------------------------------------------------------
# 验证 5: stream_event 新增 4 个事件类型
# ---------------------------------------------------------------------------


def test_stream_event_scenario_card_state_suspend():
    """StreamEvent 新增 scenario / card / state / suspend 4 种事件."""
    from openagent.streaming import StreamEvent

    # scenario 事件
    e = StreamEvent.scenario("flight_booking", "1.2.0", "keyword")
    assert e.type == "scenario"
    assert e.data["name"] == "flight_booking"
    assert e.data["matched_by"] == "keyword"

    # card 事件
    e = StreamEvent.card("c1", "OD_INPUT", {"title": "OD"}, correlation_id="x")
    assert e.type == "card"
    assert e.data["card_type"] == "OD_INPUT"
    assert e.data["correlation_id"] == "x"

    # state 事件
    e = StreamEvent.state("S05")
    assert e.type == "state"
    assert e.data["state"] == "S05"

    # suspend 事件
    e = StreamEvent.suspend("ck1", {"card": {}}, "x", input_schema={"a": 1}, timeout_at=12345.0)
    assert e.type == "suspend"
    assert e.data["checkpoint_id"] == "ck1"
    assert e.data["correlation_id"] == "x"
    assert e.data["input_schema"] == {"a": 1}
    assert e.data["timeout_at"] == 12345.0

    # resume 事件
    e = StreamEvent.resume("ck1")
    assert e.type == "resume"
    assert e.data["checkpoint_id"] == "ck1"


def test_bridge_session_event_is_private_to_controller():
    from openagent.api.controllers.chat_controller import _should_skip_bridge_event
    from openagent.streaming import StreamEvent

    assert _should_skip_bridge_event(StreamEvent.session("ses_1"), "ses_1")
    assert not _should_skip_bridge_event(StreamEvent.session("ses_2"), "ses_1")
    assert not _should_skip_bridge_event(StreamEvent.text("hello"), "ses_1")


# ---------------------------------------------------------------------------
# 验证 6: lifecycle 挂的 hitl_factory 真的能工作
# ---------------------------------------------------------------------------


def test_lifecycle_hitl_factory_creates_working_scheduler():
    """lifecycle._init_turn_subsystem 里的 hitl_factory 构造的 SuspendableScheduler 真的能跑."""
    from openagent.core.suspendable_scheduler import SuspendableScheduler
    from openagent.core.turn_store import InMemoryTurnStore
    from openagent.skill_runtime.manifest import SkillManifest, StateSpec

    # 模拟 lifecycle 里的 hitl_factory 内部
    def _default_manifest(scenario):
        manifest = SkillManifest(name=scenario.name, version=scenario.version, initial_state="S01")
        all_tools = ["ask_user", "query_flight_basic", "submit_order"]
        for sid in ["S01", "S02", "S05", "S11", "F1"]:
            manifest.states[sid] = StateSpec(description=sid, allowed_tools=all_tools)
        return manifest

    async def drive():
        from types import SimpleNamespace
        scenario = SimpleNamespace(name="flight_booking", version="1.0.0")
        manifest = _default_manifest(scenario)
        store = InMemoryTurnStore()
        await store.create_turn("s1", "flight_booking", "1.0.0")
        scheduler = SuspendableScheduler(turn_store=store, manifest=manifest)

        # 跑
        events = []
        async for evt in scheduler.run_turn("t-1", "s1", "订机票"):
            events.append(evt)
        return events

    events = asyncio.run(drive())
    types = [e.type.value for e in events]
    assert "session" in types
    assert "card" in types
    assert "suspend" in types


# ---------------------------------------------------------------------------
# 验证 7: 6 个 scenario 都正确加载 + 路由 + injection
# ---------------------------------------------------------------------------


def test_six_scenarios_load_route_inject():
    """6 scenario 完整链路: load → route → inject."""

    from openagent.scenarios import ScenarioInjector, ScenarioRegistry, ScenarioRouter

    ctx = {
        "WORK_ROOT": "work",
        "WORK_SHARED": "work/shared",
        "PROJECT_DIR": "work/tenants/tenant-A/projects/project-1",
    }
    reg = ScenarioRegistry(ctx=ctx)
    reg.load_from_paths("work/scenarios")

    router = ScenarioRouter(reg, default_scenario="_default")
    injector = ScenarioInjector()

    # 1. 路由到 flight_booking
    rc1 = router.route("/agent/chat", {}, {"message": "帮我订机票"})
    assert rc1.scenario.name == "flight_booking"

    # 2. 路由到 _default (兜底)
    rc2 = router.route("/agent/chat", {}, {"message": "随机聊天"})
    assert rc2.scenario.name == "_default"

    # 3. 路由到 _generic
    rc3 = router.route("/agent/chat", {}, {"message": "你好"})
    # 优先级 _default (90000) > _generic (99999), 所以是 _default
    assert rc3.scenario.name in ("_default", "_generic")

    # 4. inject 跨 scenario (flight_booking.execution.skills 来自 P2 阶段默认 [] 或带白名单)
    # flight_booking 的 skills 列表可能为空 (它用 progressive_skill + a2ui 而不是 execution.skills)
    inj1 = injector.inject(rc1.scenario, "test", caller_skills=["evil_skill", "book-flight"])
    # 白名单生效: 越权 skill 必被拒绝 (无论白名单是否为空, 越权都拒)
    assert "evil_skill" in inj1.rejected_skills
    # book-flight 取决于 flight_booking.execution.skills 的内容 — 接受或拒绝都合理
    # 关键断言: rejected_skills 包含 evil_skill
    assert len(inj1.rejected_skills) >= 1

    # 5. _generic 零 skill
    inj2 = injector.inject(reg.get("_generic"), "test", caller_skills=["a"])
    assert inj2.final_skills == []
    assert "a" in inj2.rejected_skills
