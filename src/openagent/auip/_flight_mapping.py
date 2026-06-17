"""auip/_flight_mapping.py — MCP flightList → AUIP 字段映射.

P0 重构: 把 flight_card.py 里的 ``_flight_to_auip`` 抽出来独立维护.
原文件 296 行含大量字段 fallback 链 (raw.get("flightNo") / raw.get("outboundFlightNo") /
raw.get("flightNumber") ...), 抽出来后 flight_card.py 缩到 ~200 行 (符合 L3 ≤ 250).

字段映射是**纯数据变换**, 无状态, 易于单测. 共享实现避免
flight_card.py / flight_query_presenter.py 重复维护同一套字段 fallback 链.
"""
from __future__ import annotations

from typing import Any


def _first_text(*values: Any) -> str:
    """从若干候选值中取第一个非空字符串.

    通用工具, 跟 flight_card.py 内部那个版本一致. 集中到这里避免重复定义.
    """
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
    """从若干候选值中取第一个可解析为 float 的值; 全部失败返 0.0."""
    for value in values:
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _date_part(value: Any) -> str:
    """从 "2026-06-06 08:00" 取 "2026-06-06" 部分. 空值返空串."""
    text = _first_text(value)
    return text.split(" ")[0] if text else ""


def _normalize_aircraft(name: str | None) -> str:
    """``"空客330(大)"`` → ``"空客330"``. 去掉机型后缀."""
    import re
    if not name:
        return ""
    return re.sub(r"[(（](大|中|小)[)）]\s*$", "", name).strip()


def _leg(raw: dict[str, Any]) -> dict[str, Any]:
    """安全取 leg[0]; 没有 legs 返空 dict.
    
    支持两种嵌套格式:
    - raw.legs[0] (标准 AGUI 格式)
    - raw.tripInfos[0].flightInfoList[0] (飞鹤 MCP 原始格式)
    """
    legs = raw.get("legs")
    if isinstance(legs, list) and legs and isinstance(legs[0], dict):
        return legs[0]
    trip_infos = raw.get("tripInfos")
    if isinstance(trip_infos, list) and trip_infos and isinstance(trip_infos[0], dict):
        info_list = trip_infos[0].get("flightInfoList")
        if isinstance(info_list, list) and info_list and isinstance(info_list[0], dict):
            return info_list[0]
    return {}


def flight_dict_to_auip(
    raw: dict[str, Any],
    *,
    airway_names: dict[str, str] | None = None,
    duration_text: str = "",
) -> dict[str, Any]:
    """MCP flightList[] 单项 → AUIP flights[] 单项 (跟 ask_user.schema.json 对齐).

    Args:
        raw: MCP 单个 flight dict (来自 queryFlightBasic 响应).
        airway_names: 航司码 → 名称映射; 用 None 时跳过名称 fallback.
        duration_text: 已格式化的时长字符串 (e.g. "2h20m"); 由 caller 从
            raw.totalDuration / durationMin 解析后传入, 这里不重复解析.

    Returns:
        AUIP flights[] 单项 dict.
    """
    leg = _leg(raw)
    airway_names = airway_names or {}

    flight_no = _first_text(
        raw.get("flightNo"),
        raw.get("outboundFlightNo"),
        raw.get("flightNumber"),
        raw.get("flightNum"),
        raw.get("flightCode"),
        leg.get("flightNo"),
    )
    airline_code = (
        _first_text(
            raw.get("airId"),
            raw.get("airlineCode"),
            raw.get("companyNo"),
            raw.get("carrierCode"),
        )
        or flight_no[:2]
    )
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
        leg.get("depTime"),
        raw.get("depTime"),
        raw.get("departTime"),
        raw.get("departureTime"),
        raw.get("outboundDepDate"),
    )
    arr_time = _first_text(
        leg.get("arrTime"),
        raw.get("arrTime"),
        raw.get("arriveTime"),
        raw.get("arrivalTime"),
        raw.get("outboundArrDate"),
    )

    return {
        "flightId": _first_text(
            raw.get("flightId"), raw.get("outboundFlightId"), raw.get("id"), flight_no
        ),
        "flightNo": flight_no,
        "shareFlight": bool(raw.get("shareFlight")),
        "shareInfo": raw.get("shareId") or None,
        "airline": {"code": airline_code, "name": airline_name},
        "aircraft": _normalize_aircraft(
            _first_text(
                leg.get("aircraftName"),
                raw.get("aircraftName"),
                raw.get("aircraft"),
                raw.get("planeType"),
            )
        ),
        "date": _first_text(
            raw.get("depDate"),
            leg.get("depDate"),
            _date_part(raw.get("outboundDepDate")),
            _date_part(dep_time),
        ),
        "departure": {
            "city": _first_text(
                raw.get("depCityName"),
                raw.get("departureCity"),
                raw.get("depCity"),
                raw.get("originCity"),
            ),
            "airport": _first_text(
                leg.get("depAirportName"),
                raw.get("depAirportName"),
                raw.get("departureAirport"),
                raw.get("origin"),
            ),
            "airportCode": _first_text(
                raw.get("depAirportCode"),
                raw.get("departureAirportCode"),
                raw.get("originCode"),
            ),
            "terminal": leg.get("depTerminal"),
            "time": dep_time,
        },
        "arrival": {
            "city": _first_text(
                raw.get("arrCityName"),
                raw.get("arrivalCity"),
                raw.get("arrCity"),
                raw.get("destinationCity"),
            ),
            "airport": _first_text(
                leg.get("arrAirportName"),
                raw.get("arrAirportName"),
                raw.get("arrivalAirport"),
                raw.get("destination"),
            ),
            "airportCode": _first_text(
                raw.get("arrAirportCode"),
                raw.get("arrivalAirportCode"),
                raw.get("destinationCode"),
            ),
            "terminal": leg.get("arrTerminal"),
            "time": arr_time,
        },
        "duration": duration_text,
        "stops": int(raw.get("stopCount", raw.get("transferCount", 0)) or 0),
        "cabin": _first_text(
            raw.get("lowestCabinName"), raw.get("cabin"), raw.get("cabinName")
        ),
        "cabinClass": _first_text(
            raw.get("lowestCabinName"), raw.get("cabinClass"), raw.get("cabin")
        ),
        "price": _first_number(
            raw.get("lowestPrice"), raw.get("price"), raw.get("totalPrice")
        ),
        "fullPrice": _first_number(
            raw.get("fullPrice"), raw.get("price"), raw.get("totalPrice")
        ),
    }


__all__ = [
    "flight_dict_to_auip",
    "_first_text",
    "_first_number",
    "_date_part",
    "_normalize_aircraft",
]
