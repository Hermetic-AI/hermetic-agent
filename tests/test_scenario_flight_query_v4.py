"""tests/test_scenario_flight_query_v4.py — flight_query_v4 scenario 加载 + 结构校验.

v4 关键校验点:
1. scenario 能正常 load (YAML 语法 + 占位符 + 资源路径)
2. ASK_QUERY 是 v4 新增的 card_type, ask_user schema 必须包含它
3. system_prompt 极简 (≤ 20 行), 体现 v4 速度优化
4. skill 引用路径正确 (flight-query-v4 + iata 子 skill)
5. 路由关键词含 v4 标识
6. 资源 metadata 含 performance 字段 (v3 → v4 性能对比)
"""
from __future__ import annotations

from pathlib import Path

from openagent.scenarios.loader import load_scenario

WORK_DIR = Path(__file__).resolve().parents[1] / "work"


def _load_v4():
    """Load flight_query_v4 with placeholder ctx."""
    return load_scenario(
        WORK_DIR / "scenarios" / "flight_query_v4.scenario.yaml",
        ctx={
            "WORK_ROOT": str(WORK_DIR),
            "WORK_SHARED": str(WORK_DIR / "shared"),
            "SCENARIO_DIR": str(WORK_DIR / "scenarios" / "flight_query_v4"),
            "PROJECT_DIR": str(WORK_DIR / "tenants" / "tenant-A" / "projects" / "project-1"),
        },
    )


def test_v4_scenario_loads_successfully():
    cfg = _load_v4()
    assert cfg.name == "flight_query_v4"
    assert cfg.enabled is True


def test_v4_system_prompt_is_lean():
    """v4 核心: system_prompt ≤ 20 行. v3 是 40+ 行."""
    cfg = _load_v4()
    sp = cfg.execution.system_prompt or ""
    line_count = len([line for line in sp.splitlines() if line.strip()])
    assert line_count <= 20, f"v4 system_prompt 应该 ≤ 20 行, 实际 {line_count} 行"


def test_v4_asks_3_step_flow_in_prompt():
    """v4 system_prompt 必须包含 3 步固定流程 (PARSE/CALL/CARD)."""
    cfg = _load_v4()
    sp = cfg.execution.system_prompt or ""
    assert "PARSE" in sp
    assert "CALL" in sp
    assert "CARD" in sp


def test_v4_routing_keywords_include_v4():
    cfg = _load_v4()
    kws = cfg.routing.trigger_keywords or []
    assert any("v4" in k.lower() for k in kws), f"v4 路由关键词必须含 'v4' 标识, 实际 {kws}"


def test_v4_skills_reference_v4():
    """skill 名必须以 flight-query-v4 开头 (不能引到 v3 资源)."""
    cfg = _load_v4()
    skills = cfg.execution.skills or []
    assert any(s.startswith("flight-query-v4") for s in skills), \
        f"v4 scenario 必须引用 v4 skill, 实际 {skills}"
    assert all("flight-query-v3" not in s for s in skills), \
        f"v4 scenario 不应再引用 v3 skill: {skills}"


def test_v4_a2ui_has_ask_query_card_type():
    """v4 新增 ASK_QUERY 卡片, card_schemas 必须含它."""
    cfg = _load_v4()
    schemas = cfg.a2ui.card_schemas or []
    assert "ASK_QUERY" in schemas, f"v4 ASK_QUERY 卡片缺失, card_schemas={schemas}"
    # 保留 v3 的 3 种 + v4 新增 1 种
    expected = {"FLIGHT_RESULT", "CANNOT_ORDER", "ASK_QUERY", "CHAT_FALLBACK"}
    assert expected.issubset(set(schemas)), f"v4 卡片类型不全, 缺 {expected - set(schemas)}"


def test_v4_ask_user_schema_path_resolves():
    """ask_user.schema_ref 路径必须能 resolve 到真实文件."""
    cfg = _load_v4()
    assert cfg.a2ui.ask_user is not None
    schema_path = Path(cfg.a2ui.ask_user.schema_ref)
    assert schema_path.exists(), f"v4 ask_user schema 路径不存在: {schema_path}"
    assert schema_path.name == "ask_user.schema.json"


def test_v4_ask_user_schema_contains_ask_query():
    """v4 ask_user.schema.json 必须含 ASK_QUERY oneOf 块."""
    cfg = _load_v4()
    schema_path = Path(cfg.a2ui.ask_user.schema_ref)
    text = schema_path.read_text(encoding="utf-8")
    assert "ASK_QUERY" in text
    assert '"missing"' in text  # ASK_QUERY 必填字段
    assert '"plan_kind"' in text  # FLIGHT_RESULT 极简必填


def test_v4_security_tighter_than_v3():
    """v4 砍 max_turns (10→8) + 砍 max_budget_usd (0.3→0.25) + 砍 timeout (120→90)."""
    cfg = _load_v4()
    sec = cfg.security
    assert sec.max_turns <= 8, f"v4 max_turns 应该 ≤ 8, 实际 {sec.max_turns}"
    assert sec.max_budget_usd <= 0.25, f"v4 max_budget_usd 应该 ≤ 0.25, 实际 {sec.max_budget_usd}"


def test_v4_resources_metadata_includes_performance():
    """v4 metadata.performance 字段记录 v3→v4 性能对比 (审计用)."""
    cfg = _load_v4()
    perf = cfg.metadata.get("performance") or {}
    assert "end_to_end_seconds" in perf, "v4 metadata 应含 performance.end_to_end_seconds"
    assert "v3" in perf["end_to_end_seconds"]
    assert "v4" in perf["end_to_end_seconds"]
    # 量化收益: v4 应该比 v3 至少快 30%
    v3 = perf["end_to_end_seconds"]["v3"]
    v4 = perf["end_to_end_seconds"]["v4"]
    if isinstance(v3, str) and "-" in v3 and isinstance(v4, str) and "-" in v4:
        v3_avg = sum(int(x) for x in v3.split("-")) / 2
        v4_avg = sum(int(x) for x in v4.split("-")) / 2
        assert v4_avg < v3_avg * 0.7, f"v4 应该比 v3 至少快 30%, 实际 v3={v3_avg}s v4={v4_avg}s"


def test_v4_tier_is_gold():
    """v4 升 gold tier (v3 是 silver, 体现性能提升)."""
    cfg = _load_v4()
    assert cfg.tier == "gold"


def test_v4_replaces_v3():
    cfg = _load_v4()
    assert cfg.metadata.get("replaces") == "flight_query_v3@1.x"
    assert cfg.metadata.get("parent_scenario") == "flight_query_v3"


def test_v4_arch_field_in_metadata():
    """architecture 字段必须放进 metadata 块 (YAML 严格校验)."""
    cfg = _load_v4()
    assert cfg.metadata.get("architecture") == "skill-backend-presentation-decoupled"


def test_v4_arch_field():
    """v4 标记 architecture = skill-backend-presentation-decoupled (区别 v3)."""
    cfg = _load_v4()
    arch = cfg.metadata.get("architecture") or ""
    assert "presentation" in arch or "decoupled" in arch, \
        f"v4 architecture 标签缺失, 实际 {arch}"


def test_v4_tools_match_v3_mcp():
    """v4 沿用 v3 的 2 个 MCP 工具, 不引入新工具 (避免 LLM 重新选)."""
    cfg = _load_v4()
    tools = cfg.execution.tools or []
    assert "queryFlightBasic" in tools
    assert "filterFlightList" in tools


def test_v4_orchestration_single():
    cfg = _load_v4()
    assert cfg.execution.orchestration == "single"
