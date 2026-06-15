"""Hub-side 智能卡组装 — 把 MCP queryFlightBasic 原始数据组装成 FLIGHT_RESULT 卡片.

v3 设计原意: LLM 调 ``ask_user`` 工具发 FLIGHT_RESULT 卡片. 但 minimax-M3 这类弱模型
不遵循复杂 system_prompt, 倾向把数据塞进 text 事件 (Markdown 表格). 前端收到 text
不知道按 card 渲染.

退一步方案 (Hub 兜底): **LLM 调 queryFlightBasic → Hub 看到 tool_result → Hub 自动拼
FLIGHT_RESULT card → emit SSE card 事件**. LLM 完全不用知道 AUIP 存在, Hub 替它做
结构化工作. 前端照常收 card 事件渲染 FlightResultCard.

触发条件:
  - tool_result.tool_name == "feihe-travel_queryFlightBasic" or "feihe-travel__queryFlightBasic"
  - 解析成功 + 含 flightList 数组
  - 一次 chat 只 emit 一次 (避免重复)

限制:
  - 只识别 feihe-travel 这一家 MCP. 其他 MCP 走 ask_user 路径 (LLM 调, Hub 转发).
  - Plan 分组策略: cheapest / fastest / comfortable, 各取 1-3 个航班.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import structlog

from openagent.auip._duration import parse_minutes
from openagent.auip._flight_mapping import (
    _date_part,
    _first_number,
    _first_text,
    flight_dict_to_auip,
)
from openagent.auip.agui_flight_card import build_domestic_flight_agui
from openagent.auip.cards import Card, CardType

logger = structlog.get_logger(__name__)
QUERY_FLIGHT_BASIC_TOOL_NAMES = {
    "feihe-travel_queryFlightBasic",
    "feihe-travel__queryFlightBasic",
}


# 兼容 shim: tests 历史可能 ``from openagent.auip.flight_card import _parse_minutes``.
# 真实实现已统一到 ``openagent.auip._duration.parse_minutes``.
_parse_minutes = parse_minutes


def _aircraft_priority(aircraft: str | None) -> int:
    """``"大"`` (大机型) 优先, ``"中"`` 次之, ``"小"`` 最后. 决定 confortable 排序."""
    if not aircraft:
        return 2
    if "大" in aircraft:
        return 0
    if "中" in aircraft:
        return 1
    if "小" in aircraft:
        return 2
    return 2


def _flight_to_auip(raw: dict[str, Any], airway_names: dict[str, str] | None = None) -> dict[str, Any]:
    """兼容 shim — 委托到 ``auip._flight_mapping.flight_dict_to_auip``.

    老 ``tests/test_auip_flight_card.py`` 等历史 import path 保留.
    """
    leg = raw.get("legs", [{}])[0] if raw.get("legs") else {}
    return flight_dict_to_auip(
        raw,
        airway_names=airway_names,
        duration_text=_duration_text(raw, leg),
    )


def _duration_text(raw: dict[str, Any], leg: dict[str, Any]) -> str:
    """从 MCP raw dict 抽时长字符串, 优先 totalDuration 文本格式, 退到 durationMin 数字."""
    duration = _first_text(raw.get("totalDuration"), raw.get("duration"), leg.get("duration"))
    if duration:
        return duration
    duration_min = raw.get("durationMin") or raw.get("totalDurationMin")
    if duration_min is None:
        return ""
    try:
        return f"{int(duration_min)}分钟"
    except (TypeError, ValueError):
        return ""


def _airway_names(data: dict[str, Any]) -> dict[str, str]:
    """从 data.airways / data.airlines 抽 {code: name} 映射."""
    names: dict[str, str] = {}
    for item in data.get("airways") or data.get("airlines") or []:
        if not isinstance(item, dict):
            continue
        code = _first_text(item.get("companyNo"), item.get("code"), item.get("airId"))
        name = _first_text(item.get("companyName"), item.get("fullCompanyName"), item.get("name"))
        if code and name:
            names[code] = name
    return names


def _extract_data(output: Any) -> dict[str, Any] | None:
    if isinstance(output, dict):
        data = output
    elif isinstance(output, str):
        try:
            data = json.loads(output)
        except (json.JSONDecodeError, TypeError):
            logger.warning("flight_card_parse_failed", tool_name="queryFlightBasic", output_head=str(output)[:200])
            return None
    else:
        return None

    content = data.get("result", {}).get("content") if isinstance(data.get("result"), dict) else data.get("content")
    if isinstance(content, list) and content:
        text = content[0].get("text") if isinstance(content[0], dict) else None
        if isinstance(text, str):
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return data
    return data


def _build_plans(flight_list: list[dict[str, Any]], airway_names: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """从 flightList 抽 3 个 plan: cheapest / fastest / comfortable, 各 1 班."""
    if not flight_list:
        return []
    # cheapest: 按 price 升序
    cheapest = sorted(flight_list, key=lambda f: _first_number(f.get("lowestPrice"), f.get("price"), f.get("totalPrice")) or 9e9)
    # fastest: 按 duration 升序 (parse 2h20m)
    fastest = sorted(flight_list, key=lambda f: f.get("durationMin") or _parse_minutes(_duration_text(f, f.get("legs", [{}])[0] if f.get("legs") else {})))
    # comfortable: 大机型优先, 同机型起飞早优先
    comfortable = sorted(
        flight_list,
        key=lambda f: (_aircraft_priority(f.get("planeSize") or f.get("aircraftName") or f.get("aircraft") or ""), f.get("outboundDepDate") or f.get("departTime") or ""),
    )
    return [
        {
            "id": "fastest",
            "title": "最快抵达",
            "subtitle": _duration_text(fastest[0], fastest[0].get("legs", [{}])[0] if fastest[0].get("legs") else {}) or "?",
            "criteria": "duration",
            "flights": [_flight_to_auip(fastest[0], airway_names)],
        },
        {
            "id": "cheapest",
            "title": "最便宜",
            "subtitle": f"¥{_first_number(cheapest[0].get('lowestPrice'), cheapest[0].get('price'), cheapest[0].get('totalPrice')) or '?'} 起",
            "criteria": "price",
            "flights": [_flight_to_auip(cheapest[0], airway_names)],
        },
        {
            "id": "comfortable",
            "title": "舒适首选",
            "subtitle": comfortable[0].get("aircraftName") or comfortable[0].get("aircraft") or comfortable[0].get("planeSize") or "舒适机型",
            "criteria": "comfort",
            "flights": [_flight_to_auip(comfortable[0], airway_names)],
        },
    ]


def maybe_assemble_flight_card(tool_name: str, output: Any) -> Card | None:
    """``tool_result`` 事件触发: 如果是 queryFlightBasic 且有 flightList → 返回 Card.

    Args:
        tool_name: opencode tool_result 事件的 tool_name
        output: 工具原始输出 (str 或 dict)

    Returns:
        ``Card`` 实例 (card_type=FLIGHT_RESULT), 或 ``None`` (不是这个工具 / 解析失败 /
        无航班).
    """
    if tool_name not in QUERY_FLIGHT_BASIC_TOOL_NAMES:
        return None
    # output 可能是 str (JSON string), dict, 或 MCP content[].text 包装.
    data = _extract_data(output)
    if data is None:
        return None

    flight_list = data.get("flightList") or []
    if not isinstance(flight_list, list) or not flight_list:
        return None

    airway_names = _airway_names(data)
    plans = _build_plans(flight_list, airway_names)
    if not plans:
        return None

    first_flight = flight_list[0] if isinstance(flight_list[0], dict) else {}
    first_legs = first_flight.get("legs") if isinstance(first_flight.get("legs"), list) else []
    first_leg = first_legs[0] if first_legs and isinstance(first_legs[0], dict) else {}
    first_dep_date = (
        _first_text(first_flight.get("depDate"), first_leg.get("depDate"))
        or _date_part(first_flight.get("outboundDepDate") or first_flight.get("departTime"))
        or first_leg.get("depDate")
        or ""
    )
    summary = {
        "totalCount": int(data.get("flightCount") or data.get("totalCount") or 0),
        "filteredCount": int(data.get("filteredCount") or len(flight_list)),
        "searchType": data.get("searchType") or "全量查询",
        "depCity": _first_text(data.get("depCityName"), data.get("departureCity"), first_flight.get("depCityName"), first_flight.get("departureCity"), first_flight.get("depCity")),
        "arrCity": _first_text(data.get("arrCityName"), data.get("arrivalCity"), first_flight.get("arrCityName"), first_flight.get("arrivalCity"), first_flight.get("arrCity")),
        "depDate": _first_text(data.get("depDate"), data.get("departureDate"), first_dep_date),
    }
    title = "机票已发送"
    if summary["depCity"] and summary["arrCity"]:
        title = f"{summary['depCity']}到{summary['arrCity']}机票已发送"
    agui = build_domestic_flight_agui(data, flight_list, airway_names, summary)
    return Card(
        card_id=f"card-{uuid.uuid4().hex[:12]}",
        card_type=CardType.FLIGHT_RESULT,
        title=title,
        body={"summary": summary, "plans": plans, "agui": agui},
    )


__all__ = ["maybe_assemble_flight_card", "QUERY_FLIGHT_BASIC_TOOL_NAMES"]
