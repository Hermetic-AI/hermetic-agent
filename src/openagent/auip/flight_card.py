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
    h = re.search(r"(\d+)h", duration)
    m = re.search(r"(\d+)m", duration)
    return int(h.group(1)) * 60 + int(m.group(1)) if h or m else 9999


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


def _flight_to_auip(raw: dict[str, Any]) -> dict[str, Any]:
    """MCP flightList[] 单项 → AUIP flights[] 单项 (跟 ask_user.schema.json 对齐)."""
    leg = raw.get("legs", [{}])[0] if raw.get("legs") else {}
    return {
        "flightId": raw.get("flightId") or raw.get("flightNo", ""),
        "flightNo": raw.get("flightNo", ""),
        "shareFlight": bool(raw.get("shareFlight")),
        "shareInfo": raw.get("shareId") or None,
        "airline": {
            "code": raw.get("airId") or "",
            "name": leg.get("airlineName") or raw.get("airlineName") or "",
        },
        "aircraft": _normalize_aircraft(leg.get("aircraftName") or raw.get("aircraftName")),
        "date": raw.get("depDate") or "",
        "departure": {
            "city": raw.get("depCityName") or "",
            "airport": leg.get("depAirportName") or raw.get("depAirportName") or "",
            "airportCode": raw.get("depAirportCode") or "",
            "terminal": leg.get("depTerminal"),
            "time": leg.get("depTime") or raw.get("depTime") or "",
        },
        "arrival": {
            "city": raw.get("arrCityName") or "",
            "airport": leg.get("arrAirportName") or raw.get("arrAirportName") or "",
            "airportCode": raw.get("arrAirportCode") or "",
            "terminal": leg.get("arrTerminal"),
            "time": leg.get("arrTime") or raw.get("arrTime") or "",
        },
        "duration": raw.get("totalDuration") or "",
        "stops": int(raw.get("stopCount", 0) or 0),
        "cabin": raw.get("lowestCabinName") or "",
        "cabinClass": raw.get("lowestCabinName") or "",
        "price": float(raw.get("lowestPrice", 0) or 0),
        "fullPrice": float(raw.get("fullPrice", 0) or 0),
    }


def _build_plans(flight_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从 flightList 抽 3 个 plan: cheapest / fastest / comfortable, 各 1 班."""
    if not flight_list:
        return []
    # cheapest: 按 price 升序
    cheapest = sorted(flight_list, key=lambda f: float(f.get("lowestPrice", 9e9) or 9e9))
    # fastest: 按 duration 升序 (parse 2h20m)
    fastest = sorted(flight_list, key=lambda f: _parse_minutes(f.get("totalDuration")))
    # comfortable: 大机型优先, 同机型起飞早优先
    comfortable = sorted(
        flight_list,
        key=lambda f: (_aircraft_priority(f.get("planeSize") or ""), f.get("outboundDepDate") or ""),
    )
    return [
        {
            "id": "cheapest",
            "title": "最便宜",
            "subtitle": f"¥{cheapest[0].get('lowestPrice', '?')} 起",
            "criteria": "price",
            "flights": [_flight_to_auip(cheapest[0])],
        },
        {
            "id": "fastest",
            "title": "最快抵达",
            "subtitle": fastest[0].get("totalDuration", "?"),
            "criteria": "duration",
            "flights": [_flight_to_auip(fastest[0])],
        },
        {
            "id": "comfortable",
            "title": "舒适首选",
            "subtitle": comfortable[0].get("aircraftName") or comfortable[0].get("planeSize") or "舒适机型",
            "criteria": "comfort",
            "flights": [_flight_to_auip(comfortable[0])],
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
    # output 可能是 str (JSON string) 或 dict
    if isinstance(output, dict):
        data = output
    elif isinstance(output, str):
        try:
            data = json.loads(output)
        except (json.JSONDecodeError, TypeError):
            logger.warning("flight_card_parse_failed", tool_name=tool_name, output_head=str(output)[:200])
            return None
    else:
        return None

    flight_list = data.get("flightList") or []
    if not isinstance(flight_list, list) or not flight_list:
        return None

    plans = _build_plans(flight_list)
    if not plans:
        return None

    summary = {
        "totalCount": int(data.get("flightCount") or data.get("totalCount") or 0),
        "filteredCount": int(data.get("filteredCount") or len(flight_list)),
        "searchType": data.get("searchType") or "全量查询",
        "depCity": data.get("depCityName") or "",
        "arrCity": data.get("arrCityName") or "",
        "depDate": data.get("depDate") or "",
    }
    return Card(
        card_id=f"card-{uuid.uuid4().hex[:12]}",
        card_type=CardType.FLIGHT_RESULT,
        title=f"{summary['depCity']} → {summary['arrCity']} {summary['depDate']} 航班方案",
        body={"summary": summary, "plans": plans},
    )


__all__ = ["maybe_assemble_flight_card"]
