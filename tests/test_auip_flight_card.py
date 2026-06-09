"""``auip.flight_card.maybe_assemble_flight_card`` 单元测试.

覆盖:
- 非目标 tool_name → None
- output 是 str 形式的 JSON, 含 flightList → Card
- output 是 dict 形式 → Card
- output 是不可解析的 str → None (不抛异常)
- flightList 为空 → None
- 3 个 plan (cheapest/fastest/comfortable) 字段完整
- Card 内部 structure 通过 Card.from_dict() 二次校验 (card_type 白名单)
"""
from __future__ import annotations

import json
from copy import deepcopy

from openagent.auip.cards import CARD_TYPES_SET, Card, CardType
from openagent.auip.flight_card import maybe_assemble_flight_card

_SAMPLE_MCP_OUTPUT = {
    "serialNumber": "260605140647A00000001",
    "searchType": "经济舱最低价",
    "flightCount": 3,
    "filteredCount": 3,
    "totalCount": 3,
    "depCityName": "北京",
    "arrCityName": "上海",
    "depDate": "2026-06-06",
    "flightList": [
        {
            "flightId": "F001",
            "flightNo": "CA1501",
            "shareFlight": False,
            "airId": "CA",
            "airlineName": "国航",
            "planeSize": "大",
            "aircraftName": "波音787(大)",
            "depCityName": "北京",
            "arrCityName": "上海",
            "depAirportName": "首都机场",
            "arrAirportName": "虹桥机场",
            "depAirportCode": "PEK",
            "arrAirportCode": "SHA",
            "depTime": "08:00",
            "arrTime": "10:20",
            "totalDuration": "2h20m",
            "lowestPrice": 850.0,
            "fullPrice": 1200.0,
            "lowestCabinName": "经济舱",
            "stopCount": 0,
        },
        {
            "flightId": "F002",
            "flightNo": "MU5102",
            "shareFlight": False,
            "airId": "MU",
            "airlineName": "东航",
            "planeSize": "中",
            "aircraftName": "空客320(中)",
            "depCityName": "北京",
            "arrCityName": "上海",
            "depAirportName": "首都机场",
            "arrAirportName": "浦东机场",
            "depAirportCode": "PEK",
            "arrAirportCode": "PVG",
            "depTime": "07:00",
            "arrTime": "08:55",
            "totalDuration": "1h55m",
            "lowestPrice": 1200.0,
            "fullPrice": 1600.0,
            "lowestCabinName": "经济舱",
            "stopCount": 0,
        },
        {
            "flightId": "F003",
            "flightNo": "CZ3104",
            "shareFlight": True,
            "shareId": "MU5102",
            "airId": "CZ",
            "airlineName": "南航",
            "planeSize": "小",
            "aircraftName": "波音737(小)",
            "depCityName": "北京",
            "arrCityName": "上海",
            "depAirportName": "大兴机场",
            "arrAirportName": "浦东机场",
            "depAirportCode": "PKX",
            "arrAirportCode": "PVG",
            "depTime": "13:00",
            "arrTime": "15:30",
            "totalDuration": "2h30m",
            "lowestPrice": 680.0,
            "fullPrice": 900.0,
            "lowestCabinName": "经济舱",
            "stopCount": 0,
        },
    ],
}


def test_non_target_tool_returns_none() -> None:
    """不是 queryFlightBasic → 直接返 None."""
    assert maybe_assemble_flight_card("ask_user", {"anything": 1}) is None
    assert maybe_assemble_flight_card("bash", "ls") is None
    assert maybe_assemble_flight_card("read", None) is None


def test_str_json_input_yields_card() -> None:
    """output 是 JSON 字符串 → 解析 + 组装 Card."""
    out = json.dumps(_SAMPLE_MCP_OUTPUT, ensure_ascii=False)
    card = maybe_assemble_flight_card("feihe-travel_queryFlightBasic", out)
    assert card is not None
    assert isinstance(card, Card)
    assert card.card_type == CardType.FLIGHT_RESULT
    assert card.card_type.value in CARD_TYPES_SET
    assert "北京" in card.title and "上海" in card.title
    plans = card.body.get("plans", [])
    assert len(plans) == 3
    ids = {p["id"] for p in plans}
    assert ids == {"cheapest", "fastest", "comfortable"}


def test_dict_input_yields_card() -> None:
    """output 是 dict (而不是 str) → 走另一条解析路径."""
    card = maybe_assemble_flight_card(
        "feihe-travel_queryFlightBasic",
        _SAMPLE_MCP_OUTPUT,
    )
    assert card is not None
    assert len(card.body["plans"]) == 3


def test_cheapest_is_lowest_price() -> None:
    """F003 (¥680) 应该是 cheapest — 数据里最低价."""
    card = maybe_assemble_flight_card(
        "feihe-travel_queryFlightBasic",
        _SAMPLE_MCP_OUTPUT,
    )
    cheapest = next(p for p in card.body["plans"] if p["id"] == "cheapest")
    assert cheapest["flights"][0]["flightNo"] == "CZ3104"
    assert cheapest["flights"][0]["price"] == 680.0


def test_fastest_is_shortest_duration() -> None:
    """MU5102 (1h55m) 应该是 fastest."""
    card = maybe_assemble_flight_card(
        "feihe-travel_queryFlightBasic",
        _SAMPLE_MCP_OUTPUT,
    )
    fastest = next(p for p in card.body["plans"] if p["id"] == "fastest")
    assert fastest["flights"][0]["flightNo"] == "MU5102"
    assert fastest["flights"][0]["duration"] == "1h55m"


def test_comfortable_picks_largest_aircraft() -> None:
    """CA1501 (大) 应该是 comfortable — 大机型优先."""
    card = maybe_assemble_flight_card(
        "feihe-travel_queryFlightBasic",
        _SAMPLE_MCP_OUTPUT,
    )
    comfortable = next(p for p in card.body["plans"] if p["id"] == "comfortable")
    assert comfortable["flights"][0]["flightNo"] == "CA1501"
    # aircraft 后缀 (大) 已被剥掉
    assert comfortable["flights"][0]["aircraft"] == "波音787"


def test_unparseable_string_returns_none() -> None:
    """output 是 str 但不是 JSON → None (不抛异常)."""
    assert maybe_assemble_flight_card(
        "feihe-travel_queryFlightBasic", "not json at all"
    ) is None
    assert maybe_assemble_flight_card(
        "feihe-travel_queryFlightBasic", ""
    ) is None


def test_empty_flight_list_returns_none() -> None:
    """flightList 为空 → None, 不发射空 card."""
    assert maybe_assemble_flight_card(
        "feihe-travel_queryFlightBasic",
        json.dumps({"flightList": []}, ensure_ascii=False),
    ) is None
    assert maybe_assemble_flight_card(
        "feihe-travel_queryFlightBasic",
        json.dumps({"flightList": None}, ensure_ascii=False),
    ) is None


def test_summary_fields() -> None:
    """summary 字段被正确填充."""
    card = maybe_assemble_flight_card(
        "feihe-travel_queryFlightBasic",
        _SAMPLE_MCP_OUTPUT,
    )
    s = card.body["summary"]
    assert s["depCity"] == "北京"
    assert s["arrCity"] == "上海"
    assert s["depDate"] == "2026-06-06"
    assert s["searchType"] == "经济舱最低价"
    assert s["filteredCount"] == 3


def test_summary_falls_back_to_first_flight_fields() -> None:
    output = deepcopy(_SAMPLE_MCP_OUTPUT)
    output.pop("depCityName")
    output.pop("arrCityName")
    output.pop("depDate")
    output["flightList"][0]["outboundDepDate"] = "2026-06-06 08:00"

    card = maybe_assemble_flight_card(
        "feihe-travel_queryFlightBasic",
        output,
    )

    assert card is not None
    assert "北京" in card.title
    assert "上海" in card.title
    assert card.body["summary"]["depDate"] == "2026-06-06"


def test_partial_duration_formats_do_not_break_fastest_plan() -> None:
    output = deepcopy(_SAMPLE_MCP_OUTPUT)
    output["flightList"][0]["totalDuration"] = "2h"
    output["flightList"][1]["totalDuration"] = "55m"
    output["flightList"][2]["totalDuration"] = "125"

    card = maybe_assemble_flight_card(
        "feihe-travel_queryFlightBasic",
        json.dumps(output, ensure_ascii=False),
    )

    assert card is not None
    fastest = next(plan for plan in card.body["plans"] if plan["id"] == "fastest")
    assert fastest["flights"][0]["flightNo"] == "MU5102"
