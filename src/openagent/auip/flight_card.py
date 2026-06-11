"""Hub-side 智能卡组装 — 把 MCP queryFlightBasic 原始数据组装成 FLIGHT_RESULT 卡片.

v3 设计原意: LLM 调 ``ask_user`` 工具发 FLIGHT_RESULT 卡片. 但 minimax-M3 这类弱模型
不遵循复杂 system_prompt, 倾向把数据塞进 text 事件 (Markdown 表格). 前端收到 text
不知道按 card 渲染.

退一步方案 (Hub 兜底): **LLM 调 queryFlightBasic → Hub 看到 tool_result → Hub 自动拼
FLIGHT_RESULT card → emit SSE card 事件**. LLM 完全不用知道 AUIP 存在, Hub 替它做
结构化工作. 前端照常收 card 事件渲染 FlightResultCard.

触发条件:
  - tool_result.tool_name == "feihe-travel_queryFlightBasic"
  - 解析成功 + 含 flightList 数组
  - 一次 chat 只 emit 一次 (避免重复)

限制:
  - 只识别 feihe-travel 这一家 MCP. 其他 MCP 走 ask_user 路径 (LLM 调, Hub 转发).
  - Plan 分组策略: cheapest / fastest / comfortable, 各取 1-3 个航班.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

import structlog

from openagent.auip.cards import Card, CardType

logger = structlog.get_logger(__name__)


def _parse_minutes(duration: str | None) -> int:
    """``"2h20m"`` / ``"1h55m"`` → 175 / 115. 解析失败返 9999 (排到最后)."""
    if not duration:
        return 9999
    text = str(duration).strip()
    hours = 0
    minutes = 0
    h = re.search(r"(\d+)\s*(?:h|小时)", text, re.IGNORECASE)
    m = re.search(r"(\d+)\s*(?:m|分钟|分)", text, re.IGNORECASE)
    if h:
        hours = int(h.group(1))
    if m:
        minutes = int(m.group(1))
    if h or m:
        return hours * 60 + minutes
    if text.isdigit():
        return int(text)
    return 9999


def _aircraft_priority(aircraft: str | None) -> int:
    """``"大"`` (大机型) 优先, ``"中"`` 次之, ``"小"`` 最后. 决定 comfortable 排序."""
    if not aircraft:
        return 2
    if "大" in aircraft:
        return 0
    if "中" in aircraft:
        return 1
    if "小" in aircraft:
        return 2
    return 2


def _normalize_aircraft(name: str | None) -> str:
    """``"空客330(大)"`` → ``"空客330"``. 去掉机型后缀."""
    if not name:
        return ""
    return re.sub(r"[(（](大|中|小)[)）]\s*$", "", name).strip()


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        if isinstance(value, dict):
            value = value.get("name") or value.get("companyName") or value.get("text")
        text = str(value).strip()
        if text:
            return text
    return ""


def _first_number(*values: Any) -> float:
    for value in values:
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _date_part(value: Any) -> str:
    text = _first_text(value)
    return text.split(" ")[0] if text else ""


def _duration_text(raw: dict[str, Any], leg: dict[str, Any]) -> str:
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
            logger.warning("flight_card_parse_failed", tool_name="feihe-travel_queryFlightBasic", output_head=str(output)[:200])
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


def _flight_to_auip(raw: dict[str, Any], airway_names: dict[str, str] | None = None) -> dict[str, Any]:
    """MCP flightList[] 单项 → AUIP flights[] 单项 (跟 ask_user.schema.json 对齐)."""
    leg = raw.get("legs", [{}])[0] if raw.get("legs") else {}
    airway_names = airway_names or {}
    flight_no = _first_text(
        raw.get("flightNo"),
        raw.get("outboundFlightNo"),
        raw.get("flightNumber"),
        raw.get("flightNum"),
        raw.get("flightCode"),
        leg.get("flightNo"),
    )
    airline_code = _first_text(
        raw.get("airId"), raw.get("airlineCode"), raw.get("companyNo"), raw.get("carrierCode")
    ) or flight_no[:2]
    airline_name = _first_text(
        leg.get("airlineName"),
        raw.get("airlineName"),
        raw.get("airline"),
        raw.get("airName"),
        raw.get("companyName"),
        raw.get("carrierName"),
        airway_names.get(airline_code),
    )
    dep_time = _first_text(
        leg.get("depTime"), raw.get("depTime"), raw.get("departTime"), raw.get("departureTime"), raw.get("outboundDepDate")
    )
    arr_time = _first_text(
        leg.get("arrTime"), raw.get("arrTime"), raw.get("arriveTime"), raw.get("arrivalTime"), raw.get("outboundArrDate")
    )
    duration = _duration_text(raw, leg)
    return {
        "flightId": _first_text(raw.get("flightId"), raw.get("outboundFlightId"), raw.get("id"), flight_no),
        "flightNo": flight_no,
        "shareFlight": bool(raw.get("shareFlight")),
        "shareInfo": raw.get("shareId") or None,
        "airline": {
            "code": airline_code,
            "name": airline_name,
        },
        "aircraft": _normalize_aircraft(_first_text(leg.get("aircraftName"), raw.get("aircraftName"), raw.get("aircraft"), raw.get("planeType"))),
        "date": _first_text(raw.get("depDate"), leg.get("depDate"), _date_part(raw.get("outboundDepDate")), _date_part(dep_time)),
        "departure": {
            "city": _first_text(raw.get("depCityName"), raw.get("departureCity"), raw.get("depCity"), raw.get("originCity")),
            "airport": _first_text(leg.get("depAirportName"), raw.get("depAirportName"), raw.get("departureAirport"), raw.get("origin")),
            "airportCode": _first_text(raw.get("depAirportCode"), raw.get("departureAirportCode"), raw.get("originCode")),
            "terminal": leg.get("depTerminal"),
            "time": dep_time,
        },
        "arrival": {
            "city": _first_text(raw.get("arrCityName"), raw.get("arrivalCity"), raw.get("arrCity"), raw.get("destinationCity")),
            "airport": _first_text(leg.get("arrAirportName"), raw.get("arrAirportName"), raw.get("arrivalAirport"), raw.get("destination")),
            "airportCode": _first_text(raw.get("arrAirportCode"), raw.get("arrivalAirportCode"), raw.get("destinationCode")),
            "terminal": leg.get("arrTerminal"),
            "time": arr_time,
        },
        "duration": duration,
        "stops": int(raw.get("stopCount", raw.get("transferCount", 0)) or 0),
        "cabin": _first_text(raw.get("lowestCabinName"), raw.get("cabin"), raw.get("cabinName")),
        "cabinClass": _first_text(raw.get("lowestCabinName"), raw.get("cabinClass"), raw.get("cabin")),
        "price": _first_number(raw.get("lowestPrice"), raw.get("price"), raw.get("totalPrice")),
        "fullPrice": _first_number(raw.get("fullPrice"), raw.get("price"), raw.get("totalPrice")),
    }


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
            "id": "cheapest",
            "title": "最便宜",
            "subtitle": f"¥{_first_number(cheapest[0].get('lowestPrice'), cheapest[0].get('price'), cheapest[0].get('totalPrice')) or '?'} 起",
            "criteria": "price",
            "flights": [_flight_to_auip(cheapest[0], airway_names)],
        },
        {
            "id": "fastest",
            "title": "最快抵达",
            "subtitle": _duration_text(fastest[0], fastest[0].get("legs", [{}])[0] if fastest[0].get("legs") else {}) or "?",
            "criteria": "duration",
            "flights": [_flight_to_auip(fastest[0], airway_names)],
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
    if tool_name != "feihe-travel_queryFlightBasic":
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
    return Card(
        card_id=f"card-{uuid.uuid4().hex[:12]}",
        card_type=CardType.FLIGHT_RESULT,
        title=f"{summary['depCity']} → {summary['arrCity']} {summary['depDate']} 航班方案",
        body={"summary": summary, "plans": plans},
    )


__all__ = ["maybe_assemble_flight_card"]
