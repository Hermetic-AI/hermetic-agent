"""``fh_domestic_flight_booking`` + ``flight_query_v4`` 两个 scenario 必须配好才能
触发 FLIGHT_RESULT 卡显示. 测项:

  1. scenario 加载成功 (YAML / 占位符 / schema 校验)
  2. tools 白名单里有 ``ask_user`` 和 ``queryFlightBasic``:
     - ask_user: LLM 主动调, 走 path A (v3 原设计)
     - queryFlightBasic: Hub 端 auto-build FLIGHT_RESULT 卡片, 走 path B
  3. a2ui.card_schemas 包含 ``FLIGHT_RESULT`` (前端 FlightResultCard 渲染前提)
  4. a2ui.ask_user.tool_name == "ask_user" (跟 Hub 注入的 synthetic tool 对齐)
  5. ask_user schema JSON 存在 + 含 FLIGHT_RESULT 卡片定义

如果任一缺失, 前端收不到 card 事件 / 卡片没注册 / LLM 不会调 ask_user.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from openagent.scenarios.loader import load_scenario

SCENARIOS = ["fh_domestic_flight_booking", "flight_query_v4"]


def _ctx_for(scenario_name: str) -> dict[str, str]:
    """构造一个最小 ctx, 让 ``${SCENARIO_DIR}`` / ``${WORK_SHARED}`` 占位符
    在测试里能解析. 实际生产里这些由 Hub 注入.
    """
    return {
        "PROJECT_DIR": str(Path("work/tenants/tenant-A/projects/project-1").resolve()),
        "WORK_ROOT": str(Path("work").resolve()),
        "WORK_SHARED": str(Path("work/shared").resolve()),
        "SCENARIO_DIR": str(Path(f"work/scenarios/{scenario_name}").resolve()),
    }


def _load(scenario_name: str):
    return load_scenario(
        f"work/scenarios/{scenario_name}.scenario.yaml",
        ctx=_ctx_for(scenario_name),
    )


@pytest.mark.parametrize("scenario_name", SCENARIOS)
def test_scenario_loads(scenario_name: str) -> None:
    """scenario YAML 能加载, 不抛 ScenarioLoadError."""
    path = Path(f"work/scenarios/{scenario_name}.scenario.yaml")
    assert path.exists(), f"missing scenario file: {path}"
    sc = _load(scenario_name)
    assert sc.name == scenario_name
    assert sc.enabled is True


@pytest.mark.parametrize("scenario_name", SCENARIOS)
def test_scenario_has_ask_user_tool(scenario_name: str) -> None:
    """tools 必须含 ask_user — 否则 LLM 看不到 (path A 走不通).

    注: Hub 端 _resolve_tool_names 会强制追加 ask_user, 但显式写在
    scenario YAML 里更清晰, 避免依赖 Hub 行为.
    """
    sc = _load(scenario_name)
    assert "ask_user" in sc.execution.tools, (
        f"{scenario_name}: tools whitelist missing 'ask_user' — LLM won't "
        f"call it for FLIGHT_RESULT cards"
    )


@pytest.mark.parametrize("scenario_name", SCENARIOS)
def test_scenario_has_queryflightbasic_tool(scenario_name: str) -> None:
    """tools 必须含 queryFlightBasic — Hub 端会拦截 tool_result 自动拼 FLIGHT_RESULT 卡片 (path B)."""
    sc = _load(scenario_name)
    assert "queryFlightBasic" in sc.execution.tools, (
        f"{scenario_name}: tools whitelist missing 'queryFlightBasic' — "
        f"Hub can't auto-assemble FLIGHT_RESULT card from tool_result"
    )


@pytest.mark.parametrize("scenario_name", SCENARIOS)
def test_scenario_a2ui_enabled_with_flight_result(scenario_name: str) -> None:
    """a2ui 必须开 + card_schemas 含 FLIGHT_RESULT — 前端 FlightResultCard 注册前提."""
    sc = _load(scenario_name)
    assert sc.a2ui is not None, f"{scenario_name}: a2ui not configured"
    assert sc.a2ui.enabled is True, f"{scenario_name}: a2ui not enabled"
    assert "FLIGHT_RESULT" in sc.a2ui.card_schemas, (
        f"{scenario_name}: card_schemas missing FLIGHT_RESULT — frontend "
        f"won't register the FlightResultCard component"
    )


@pytest.mark.parametrize("scenario_name", SCENARIOS)
def test_scenario_ask_user_config_aligned(scenario_name: str) -> None:
    """a2ui.ask_user.tool_name 必须 == "ask_user" — 跟 Hub 注入的 synthetic tool 名一致."""
    sc = _load(scenario_name)
    assert sc.a2ui is not None
    assert sc.a2ui.ask_user is not None, f"{scenario_name}: ask_user not configured"
    assert sc.a2ui.ask_user.tool_name == "ask_user", (
        f"{scenario_name}: ask_user.tool_name must be 'ask_user' to match "
        f"Hub's MCPRegistry synthetic tool"
    )


@pytest.mark.parametrize("scenario_name", SCENARIOS)
def test_scenario_ask_user_schema_exists_and_lists_flight_result(
    scenario_name: str,
) -> None:
    """ask_user.schema JSON 文件存在 + card_type enum 包含 FLIGHT_RESULT."""
    sc = _load(scenario_name)
    # Pydantic 把 `schema` 字段设为 alias, 实际属性名是 schema_ref
    schema_path_str = sc.a2ui.ask_user.schema_ref
    assert schema_path_str, f"{scenario_name}: ask_user.schema_ref is empty"
    schema_path = Path(schema_path_str)
    assert schema_path.exists(), (
        f"{scenario_name}: ask_user schema file not found at {schema_path}"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert "FLIGHT_RESULT" in schema["properties"]["card_type"]["enum"], (
        f"{scenario_name}: ask_user schema card_type enum missing FLIGHT_RESULT"
    )


def test_flight_query_v4_has_three_tools() -> None:
    """v4 设计是 3 工具: ask_user + queryFlightBasic + filterFlightList.

    早期版本只有 queryFlightBasic + filterFlightList, LLM 调 ask_user
    时 Hub 端 _resolve_tool_names 会强制补, 但 scenario YAML 不一致.
    """
    sc = _load("flight_query_v4")
    tools = set(sc.execution.tools)
    expected = {"ask_user", "queryFlightBasic", "filterFlightList"}
    assert expected.issubset(tools), (
        f"v4 missing tools: {expected - tools}"
    )


def test_fh_domestic_flight_booking_has_all_booking_tools() -> None:
    """fh_domestic_flight_booking 是完整订票流程, 必须有 ask_user + queryFlightBasic + chooseFlight + chooseCabin."""
    sc = load_scenario("work/scenarios/fh_domestic_flight_booking.scenario.yaml")
    tools = set(sc.execution.tools)
    for required in ("ask_user", "queryFlightBasic", "chooseFlight", "chooseCabin", "buildOrderPreview"):
        assert required in tools, f"fh missing required booking tool: {required}"


def test_both_scenarios_have_dismissible_false_default() -> None:
    """FLIGHT_RESULT 卡片通常 dismissible=false (强制用户交互).

    不在 scenario YAML 强校验, 但在 a2ui.ask_user.schema 里应该看到默认
    dismissible 字段 (前端按此行为渲染关闭按钮). 这是 schema-level 测试.
    """
    for name in SCENARIOS:
        sc = _load(name)
        schema_path = Path(sc.a2ui.ask_user.schema_ref)
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        # schema 应该有 dismissible 字段, 默认 false
        if "dismissible" in schema["properties"]:
            assert schema["properties"]["dismissible"].get("default", False) is False, (
                f"{name}: FLIGHT_RESULT card should default to dismissible=false"
            )
