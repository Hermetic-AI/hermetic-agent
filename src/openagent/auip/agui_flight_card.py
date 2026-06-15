"""AGUI v2 国内机票卡片组装。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from openagent.auip._duration import parse_minutes
from openagent.auip._flight_mapping import _date_part, _first_number, _first_text


def build_domestic_flight_agui(
    data: dict[str, Any],
    flight_list: list[dict[str, Any]],
    airway_names: dict[str, str] | None,
    summary: dict[str, Any],
) -> dict[str, Any]:
    """把 queryFlightBasic 输出转换为 docs/agui 的 AGUI v2 envelope。"""
    request_seq_no = _first_text(data.get("requestSeqNo"), data.get("recordId")) or _seq("T")
    session_id = _first_text(data.get("sessionId")) or _seq("S")
    reason = f"共查询到{summary.get('totalCount', 0)}个航班最后筛选出{summary.get('filteredCount', 0)}个"
    return {
        "tmsErrorCode": _first_text(data.get("tmsErrorCode")),
        "errorCode": _first_text(data.get("errorCode")) or "0",
        "errorMsg": _first_text(data.get("errorMsg")),
        "enErrorMsg": _first_text(data.get("enErrorMsg")),
        "requestSeqNo": request_seq_no,
        "delay": int(_first_number(data.get("delay"))),
        "data": {
            "recordId": request_seq_no,
            "sessionId": session_id,
            "role": "assistant",
            "intent": "BOOKING:DOMESTIC_BOOKING/air_domestic_booking",
            "sceneId": "DOMESTIC_BOOKING_FLIGHT_LIST",
            "contentJson": {
                "schemaVersion": "2",
                "dataList": [
                    {
                        "basicType": "AIR_DOMESTIC_FLIGHT_LIST",
                        "dataStr": reason,
                        "dataJson": {
                            "serialNumber": _first_text(data.get("serialNumber")),
                            "totalCount": int(summary.get("totalCount") or 0),
                            "filteredCount": int(summary.get("filteredCount") or len(flight_list)),
                            "flightList": [_flight_to_agui(f, airway_names or {}) for f in flight_list],
                        },
                        "linkUrl": "",
                    }
                ],
                "thinkingSteps": ["已按您的行程条件查询航班并整理列表"],
            },
            "reason": "已按您的行程条件查询航班并整理列表",
            "chatTime": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "correlationId": _first_text(data.get("correlationId")),
        },
    }


def _flight_to_agui(raw: dict[str, Any], airway_names: dict[str, str]) -> dict[str, Any]:
    leg = _first_leg(raw)
    flight_no = _first_text(raw.get("flightNo"), raw.get("outboundFlightNo"), raw.get("flightNumber"), raw.get("flightNum"), raw.get("flightCode"), leg.get("flightNo"))
    air_id = _first_text(raw.get("airId"), raw.get("airlineCode"), raw.get("companyNo"), raw.get("carrierCode"), flight_no[:2])
    dep_time = _first_text(leg.get("depTime"), raw.get("depTime"), raw.get("departTime"), raw.get("departureTime"), raw.get("outboundDepDate"))
    arr_time = _first_text(leg.get("arrTime"), raw.get("arrTime"), raw.get("arriveTime"), raw.get("arrivalTime"), raw.get("outboundArrDate"))
    dep_date = _first_text(raw.get("depDate"), leg.get("depDate"), _date_part(dep_time))
    arr_date = _first_text(raw.get("arrDate"), leg.get("arrDate"), _date_part(arr_time), dep_date)
    duration_min = _duration_min(raw, leg)
    flight = {
        "depCityName": _first_text(raw.get("depCityName"), raw.get("departureCity"), raw.get("depCity"), leg.get("depCityName")),
        "arrCityName": _first_text(raw.get("arrCityName"), raw.get("arrivalCity"), raw.get("arrCity"), leg.get("arrCityName")),
        "depDate": dep_date,
        "lowestPrice": _first_number(raw.get("lowestPrice"), raw.get("price"), raw.get("totalPrice")),
        "lowestCabinName": _first_text(raw.get("lowestCabinName"), raw.get("cabin"), raw.get("cabinName")),
        "totalPrice": _first_number(raw.get("totalPrice"), raw.get("lowestPrice"), raw.get("price")),
        "totalDuration": duration_min,
        "durationMin": duration_min,
        "stopCount": int(_first_number(raw.get("stopCount"), raw.get("stops"))),
        "transferCount": int(_first_number(raw.get("transferCount"))),
        "transferCities": raw.get("transferCities") if isinstance(raw.get("transferCities"), list) else [],
        "airlineName": _first_text(leg.get("airlineName"), raw.get("airlineName"), raw.get("airline"), raw.get("companyName"), airway_names.get(air_id)),
        "flightNo": flight_no,
        "airId": air_id,
        "tripType": _first_text(raw.get("tripType")) or "OW",
        "serialNo": int(_first_number(raw.get("serialNo"), raw.get("sequence"))) or 1,
        "flightId": _first_text(raw.get("flightId"), raw.get("outboundFlightId"), raw.get("id"), flight_no),
        "legs": [],
        "depTime": _time_part(dep_time),
        "depAirportName": _first_text(leg.get("depAirportName"), raw.get("depAirportName"), raw.get("departureAirport")),
        "depTerminal": _first_text(leg.get("depTerminal"), raw.get("depTerminal")),
        "shareFlight": bool(raw.get("shareFlight") or leg.get("shareFlight")),
        "shareId": _first_text(raw.get("shareId"), leg.get("shareId")),
        "arrDate": arr_date,
        "arrTime": _time_part(arr_time),
        "arrAirportName": _first_text(leg.get("arrAirportName"), raw.get("arrAirportName"), raw.get("arrivalAirport")),
        "arrTerminal": _first_text(leg.get("arrTerminal"), raw.get("arrTerminal")),
        "arrDayOffset": int(_first_number(raw.get("arrDayOffset"), leg.get("arrDayOffset"))),
    }
    flight["legs"] = [_leg_to_agui(raw, leg, flight)]
    return flight


def _leg_to_agui(raw: dict[str, Any], leg: dict[str, Any], flight: dict[str, Any]) -> dict[str, Any]:
    return {
        "direction": _first_text(leg.get("direction")) or "OUTBOUND",
        "flightNo": flight["flightNo"],
        "airlineName": flight["airlineName"],
        "depDate": flight["depDate"],
        "depTime": flight["depTime"],
        "arrTime": flight["arrTime"],
        "arrDate": flight["arrDate"],
        "depAirportName": flight["depAirportName"],
        "depTerminal": flight["depTerminal"],
        "arrAirportName": flight["arrAirportName"],
        "arrTerminal": flight["arrTerminal"],
        "duration": flight["durationMin"],
        "aircraftName": _first_text(leg.get("aircraftName"), raw.get("aircraftName"), raw.get("aircraft"), raw.get("planeType")),
        "meal": _bool(raw.get("meal", leg.get("meal"))),
        "shareFlight": flight["shareFlight"],
        "shareId": flight["shareId"],
        "stops": leg.get("stops") if isinstance(leg.get("stops"), list) else [],
        "arrDayOffset": flight["arrDayOffset"],
    }


def _first_leg(raw: dict[str, Any]) -> dict[str, Any]:
    legs = raw.get("legs")
    if isinstance(legs, list) and legs and isinstance(legs[0], dict):
        return legs[0]
    return {}


def _duration_min(raw: dict[str, Any], leg: dict[str, Any]) -> int:
    value = raw.get("durationMin") or raw.get("totalDurationMin") or raw.get("totalDuration") or leg.get("duration")
    if isinstance(value, (int, float)):
        return int(value)
    parsed = parse_minutes(_first_text(value), invalid_sentinel=0)
    return int(parsed or 0)


def _time_part(value: Any) -> str:
    text = _first_text(value)
    if " " in text:
        return str(text.split(" ", 1)[1][:5])
    return str(text[:5])


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "有", "含餐"}


def _seq(prefix: str) -> str:
    return f"{prefix}{datetime.now(timezone.utc).strftime('%y%m%d%H%M%S')}B00000001"


__all__ = ["build_domestic_flight_agui"]
