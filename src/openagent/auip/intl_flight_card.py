"""Hub-side 国际机票卡片自动组装。

拦截 ``bash`` 工具的 ``intShopping`` 返回结果，自动拼装 AGUI v2
``AIR_DOMESTIC_FLIGHT_LIST`` 卡片。LLM 无需知道 AUIP 存在。
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import structlog

from openagent.providers.streaming import StreamEvent

logger = structlog.get_logger(__name__)

AIRCRAFT_MAP = {
    "32N": "A320neo", "320": "A320", "321": "A321", "32A": "A319",
    "32Q": "A321neo", "319": "A319", "333": "A330-300", "332": "A330-200",
    "359": "A350-900", "35K": "A350-1000", "388": "A380",
    "738": "B737-800", "739": "B737-900", "7M8": "B737 MAX 8",
    "789": "B787-9", "78X": "B787-10", "77W": "B777-300ER",
    "772": "B777-200", "744": "B747-400",
}

CAB_LABELS = {"Y": "经济舱", "W": "高级经济舱", "C": "商务舱", "F": "头等舱"}
MEAL_TRUE = {"S", "M", "L", "D", "B"}
INTSHOPPING_PATH = "intShopping"


def _time_part(value: str) -> str:
    if not value:
        return ""
    return value.split(" ", 1)[1][:5] if " " in value else value[:5]


def _date_part(value: str) -> str:
    if not value:
        return ""
    return value.split(" ")[0]


def _aircraft(t: str, g: str = "") -> str:
    return AIRCRAFT_MAP.get(t) or AIRCRAFT_MAP.get(g) or t or g or ""


def _day_offset(d1: str, d2: str) -> int:
    try:
        from datetime import datetime as _dt
        return (_dt.strptime(_date_part(d2), "%Y-%m-%d") - _dt.strptime(_date_part(d1), "%Y-%m-%d")).days
    except (ValueError, TypeError):
        return 0


def _parse_output(output: Any) -> dict[str, Any] | None:
    if isinstance(output, dict):
        data = output
    elif isinstance(output, str):
        try:
            data = json.loads(output)
        except (json.JSONDecodeError, TypeError):
            return None
    else:
        return None
    if str(data.get("errorCode", "0")) != "0":
        return None
    inner = data.get("data")
    return inner if isinstance(inner, dict) else None


def _build_flights(
    data: dict[str, Any],
    city_map: dict[str, str],
    airway_map: dict[str, str],
    limit: int,
) -> list[dict[str, Any]]:
    groups = data.get("groupList", [])[:limit]
    flights: list[dict[str, Any]] = []
    for idx, group in enumerate(groups):
        trip = (group.get("tripList") or [{}])[0]
        fl_list = trip.get("flightList") or []
        if not fl_list:
            continue
        fl = fl_list[0]
        fid = fl.get("flightId", "")
        air_id = fid[:2].upper() if len(fid) >= 2 else ""
        fly_date = fl.get("flyDate", "")
        arr_date = fl.get("arrDate", "")
        dep_date = _date_part(fly_date)
        arr_date_only = _date_part(arr_date)
        air_line = trip.get("airLine", "")
        dep_code = air_line[:3] if len(air_line) >= 6 else ""
        arr_code = air_line[3:6] if len(air_line) >= 6 else ""
        price_list = group.get("priceList") or []
        lowest = 0
        cab_name = "经济舱"
        if price_list:
            p = price_list[0]
            lowest = p.get("totalPrice", 0) or p.get("price", 0) or 0
            tp = (p.get("tripList") or [{}])[0]
            cab_name = CAB_LABELS.get(tp.get("cabClass", "Y"), "经济舱")
        dur = fl.get("duration", 0) or 0
        leg = {
            "direction": "OUTBOUND",
            "flightNo": fid,
            "airlineName": airway_map.get(air_id, air_id),
            "depDate": dep_date,
            "depTime": _time_part(fly_date),
            "arrTime": _time_part(arr_date),
            "arrDate": arr_date_only,
            "depAirportName": "",
            "depTerminal": (fl.get("fromPort") or "").strip(),
            "arrAirportName": "",
            "arrTerminal": (fl.get("toPort") or "").strip(),
            "duration": dur,
            "aircraftName": _aircraft(fl.get("type", ""), fl.get("typeGroup", "")),
            "meal": str(fl.get("meal", "")).strip() in MEAL_TRUE,
            "shareFlight": False,
            "shareId": "",
            "stops": [],
            "arrDayOffset": _day_offset(dep_date, arr_date),
        }
        group_id = group.get("groupId", "")
        first_price_id = ""
        price_options: list[dict[str, Any]] = []
        for pi, p in enumerate(price_list[:5]):
            pid = p.get("priceId", "")
            if pi == 0:
                first_price_id = pid
            tp = (p.get("tripList") or [{}])[0]
            rule = tp.get("rule") or {}
            price_options.append({
                "priceId": pid,
                "totalPrice": p.get("totalPrice", 0) or 0,
                "cabClass": CAB_LABELS.get(tp.get("cabClass", "Y"), "经济舱"),
                "refund": bool(rule.get("refund")),
                "change": bool(rule.get("change")),
            })
        flights.append({
            "depCityName": city_map.get(dep_code, dep_code),
            "arrCityName": city_map.get(arr_code, arr_code),
            "depDate": dep_date,
            "depTime": leg["depTime"],
            "arrDate": arr_date_only,
            "arrTime": leg["arrTime"],
            "lowestPrice": lowest,
            "lowestCabinName": cab_name,
            "totalPrice": lowest,
            "totalDuration": dur,
            "durationMin": dur,
            "stopCount": len(fl.get("stopList") or []),
            "transferCount": 0,
            "transferCities": [],
            "airlineName": leg["airlineName"],
            "flightNo": fid,
            "airId": air_id,
            "tripType": "OW",
            "serialNo": idx + 1,
            "flightId": fid,
            "groupId": group_id,
            "priceId": first_price_id,
            "priceOptions": price_options,
            "legs": [leg],
            "depAirportName": "",
            "depTerminal": leg["depTerminal"],
            "arrAirportName": "",
            "arrTerminal": leg["arrTerminal"],
            "shareFlight": False,
            "shareId": "",
            "arrDayOffset": leg["arrDayOffset"],
        })
    return flights


def maybe_assemble_intl_flight_card(output: Any) -> StreamEvent | None:
    """尝试从 intShopping API 返回组装国际航班卡片。

    Args:
        output: bash 工具的 tool_result 输出 (str 或 dict)。

    Returns:
        ``StreamEvent.card(...)`` 或 ``None``。
    """
    data = _parse_output(output)
    if data is None:
        return None
    groups = data.get("groupList")
    if not isinstance(groups, list) or not groups:
        return None
    city_map: dict[str, str] = {}
    for c in data.get("cityList") or []:
        code = c.get("cityCode", "")
        name = c.get("cityName", "") or c.get("airPortName", "")
        if code and name:
            city_map[code] = name
    airway_map: dict[str, str] = {}
    for a in data.get("airwayList") or []:
        code = a.get("companyNo", "")
        name = a.get("companyName", "")
        if code and name:
            airway_map[code] = name
    total = len(data.get("groupList") or [])
    flight_list = _build_flights(data, city_map, airway_map, limit=10)
    if not flight_list:
        return None
    filtered = len(flight_list)
    data_str = f"共查询到{total}个航班组合"
    if filtered < total:
        data_str += f"，展示前{filtered}条"
    content_json = {
        "schemaVersion": "2",
        "dataList": [{
            "basicType": "AIR_DOMESTIC_FLIGHT_LIST",
            "dataStr": data_str,
            "dataJson": {
                "serialNumber": data.get("serialNumber", ""),
                "totalCount": total,
                "filteredCount": filtered,
                "flightList": flight_list,
            },
            "linkUrl": "",
        }],
        "thinkingSteps": ["已按您的行程条件查询国际航班并整理列表"],
    }
    card_id = f"card-{uuid.uuid4().hex[:8]}"
    return StreamEvent.card(
        card_id=card_id,
        card_type="FLIGHT_RESULT",
        card={
            "card_id": card_id,
            "card_type": "FLIGHT_RESULT",
            "schema_version": "1.0",
            "title": "国际航班查询结果",
            "body": {"contentJson": content_json},
            "fields": [],
            "options": [],
            "actions": [],
            "decision_buttons": [],
            "metadata": {},
            "dismissible": False,
        },
    )


__all__ = ["maybe_assemble_intl_flight_card", "INTSHOPPING_PATH"]
