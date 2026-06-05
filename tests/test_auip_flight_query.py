"""tests/test_auip_flight_query.py — P7/P9 v4: flight_query_presenter 单元测试.

覆盖 _build_plans / _flight_to_auip / _derive_tags / _parse_duration / _build_summary.
LLM 永远不直接填 plans[] / flights[], 全部由本模块 1ms 出.
"""
from __future__ import annotations

from openagent.auip.flight_query_presenter import (
    PLAN_KIND_CHEAPEST,
    PLAN_KIND_COMFORTABLE,
    PLAN_KIND_DEFAULT,
    PLAN_KIND_FASTEST,
    PLAN_KIND_USER_EXPLICIT,
    _build_plans,
    _build_summary,
    _cabin_to_class,
    _comfort_score,
    _derive_tags,
    _duration_minutes,
    _endpoint,
    _flight_to_auip,
    _parse_duration,
    _price,
    present_flight_result,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _flight(
    *,
    flight_id: str = "f1",
    flight_no: str = "CA1501",
    air_id: str = "CA",
    lowest_price: float = 550.0,
    full_price: float | None = 1630.0,
    duration: str = "2h20m",
    stops: int = 0,
    dep_date: str = "2026-06-06",
    dep_code: str = "PEK",
    arr_code: str = "PVG",
    cabin: str = "经济舱",
    airline_name: str = "中国国际航空",
    aircraft: str = "波音 737",
    dep_time: str = "09:00",
    arr_time: str = "11:20",
    meal: bool = True,
    share: bool = False,
) -> dict:
    return {
        "flightId": flight_id, "flightNo": flight_no, "shareFlight": share,
        "airId": air_id, "lowestPrice": lowest_price, "fullPrice": full_price,
        "totalDuration": duration, "stopCount": stops, "depDate": dep_date,
        "depAirportCode": dep_code, "arrAirportCode": arr_code,
        "lowestCabinName": cabin,
        "legs": [{
            "airlineName": airline_name, "aircraftName": aircraft,
            "depTime": dep_time, "arrTime": arr_time,
            "depAirportName": f"{airline_name[:2]}机场",
            "arrAirportName": "到达机场",
            "depTerminal": "T3", "arrTerminal": "T2", "meal": meal,
        }],
    }


# ---------------------------------------------------------------------------
# _parse_duration
# ---------------------------------------------------------------------------


def test_parse_duration_2h20m() -> None:
    assert _parse_duration("2h20m") == 140


def test_parse_duration_3h() -> None:
    assert _parse_duration("3h") == 180


def test_parse_duration_150m() -> None:
    assert _parse_duration("150m") == 150


def test_parse_duration_empty() -> None:
    assert _parse_duration("") == 0


def test_parse_duration_garbage() -> None:
    assert _parse_duration("??") == 0


# ---------------------------------------------------------------------------
# Sort keys
# ---------------------------------------------------------------------------


def test_price_uses_lowestprice() -> None:
    assert _price(_flight(lowest_price=999)) == 999
    assert _price(_flight(lowest_price=0)) == 0


def test_duration_minutes_parses_2h20m() -> None:
    assert _duration_minutes(_flight(duration="2h20m")) == 140


def test_duration_minutes_unparseable_uses_99999() -> None:
    assert _duration_minutes(_flight(duration="??")) == 99999


def test_comfort_score_direct_large() -> None:
    """直飞 + 大飞机 (无餐) = 100 + 50 = 150."""
    f = _flight(stops=0, meal=False)
    f["legs"][0]["aircraftName"] = "波音 747"
    assert _comfort_score(f) == 150


def test_comfort_score_direct_small() -> None:
    """直飞 + 小飞机 (无餐) = 100."""
    assert _comfort_score(_flight(stops=0, meal=False)) == 100


def test_comfort_score_with_meal() -> None:
    """1 停 + 有餐 = 5."""
    assert _comfort_score(_flight(stops=1, meal=True)) == 5


def test_cabin_to_class_first() -> None:
    assert _cabin_to_class("头等舱") == "FIRST"


def test_cabin_to_class_business() -> None:
    assert _cabin_to_class("公务舱") == "BUSINESS"


def test_cabin_to_class_premium_economy() -> None:
    assert _cabin_to_class("超经济舱") == "PREMIUM_ECONOMY"


def test_cabin_to_class_default_economy() -> None:
    assert _cabin_to_class("经济舱") == "ECONOMY"


def test_cabin_to_class_empty() -> None:
    assert _cabin_to_class("") == "ECONOMY"


# ---------------------------------------------------------------------------
# _endpoint
# ---------------------------------------------------------------------------


def test_endpoint_dep_maps_city() -> None:
    leg = {"depAirportName": "首都", "depTime": "09:00", "depTerminal": "T3"}
    out = _endpoint(leg, "dep", "PEK")
    assert out == {
        "city": "北京", "airport": "首都", "airportCode": "PEK",
        "terminal": "T3", "time": "09:00",
    }


def test_endpoint_unknown_code_passes_through() -> None:
    leg = {"depAirportName": "X", "depTime": "00:00"}
    out = _endpoint(leg, "dep", "XYZ")
    assert out["city"] == "XYZ"
    assert out["terminal"] is None


# ---------------------------------------------------------------------------
# _flight_to_auip (field mapping)
# ---------------------------------------------------------------------------


def test_flight_to_auip_basic_fields() -> None:
    out = _flight_to_auip(_flight(), 0)
    assert out["flightId"] == "f1"
    assert out["flightNo"] == "CA1501"
    assert out["shareFlight"] is False
    assert out["airline"] == {"code": "CA", "name": "中国国际航空"}
    assert out["aircraft"] == "波音 737"
    assert out["date"] == "2026-06-06"
    assert out["duration"] == "2h20m"
    assert out["stops"] == 0
    assert out["cabin"] == "经济舱"
    assert out["cabinClass"] == "ECONOMY"
    assert out["meal"] == "是"
    assert out["price"] == 550.0
    assert "shareInfo" not in out
    assert out["fullPrice"] == 1630.0


def test_flight_to_auip_share_flight_has_share_info() -> None:
    out = _flight_to_auip(_flight(share=True, airline_name="东方航空"), 0)
    assert out["shareFlight"] is True
    assert out["shareInfo"] == "共享东方航空"


def test_flight_to_auip_no_full_price_omits_key() -> None:
    out = _flight_to_auip(_flight(full_price=None), 0)
    assert "fullPrice" not in out


def test_flight_to_auip_meal_false() -> None:
    out = _flight_to_auip(_flight(meal=False), 0)
    assert out["meal"] == "否"


def test_flight_to_auip_no_meal_field() -> None:
    f = _flight()
    del f["legs"][0]["meal"]
    out = _flight_to_auip(f, 0)
    assert out["meal"] is None


def test_flight_to_auip_no_legs() -> None:
    f = _flight()
    f["legs"] = []
    out = _flight_to_auip(f, 0)
    assert out["airline"] == {"code": "CA", "name": ""}
    assert out["stops"] == 0


def test_flight_to_auip_default_idx_in_id_when_missing() -> None:
    """flightId key 缺失时 fallback 到 flt-{idx}."""
    f = _flight()
    del f["flightId"]
    out = _flight_to_auip(f, 7)
    assert out["flightId"] == "flt-7"


def test_flight_to_auip_aircraft_cleans_size_suffix() -> None:
    f = _flight(aircraft="波音 737 (中)")
    out = _flight_to_auip(f, 0)
    assert out["aircraft"] == "波音 737"


# ---------------------------------------------------------------------------
# _derive_tags
# ---------------------------------------------------------------------------


def test_tags_direct_large_aircraft() -> None:
    f = _flight(stops=0)
    f["legs"][0]["aircraftName"] = "空客 A350"
    assert "大飞机直飞" in _derive_tags(f)


def test_tags_direct_small_aircraft() -> None:
    assert "直飞" in _derive_tags(_flight(stops=0))


def test_tags_with_meal() -> None:
    """有 meal 字段 → 加"含餐" tag. 用 meal=True 显式 + stops=1 + duration 长 + 无折扣避免其他 tag 抢占."""
    f = _flight(meal=True, stops=1, duration="4h", lowest_price=1000, full_price=1000)
    assert "含餐" in _derive_tags(f)


def test_tags_morning_departure() -> None:
    f = _flight(dep_time="08:00", meal=False, stops=1)  # 去直飞/含餐干扰
    assert "早班" in _derive_tags(f)


def test_tags_night_departure() -> None:
    f = _flight(dep_time="20:00", meal=False, stops=1)
    assert "晚班" in _derive_tags(f)


def test_tags_quick_under_2_5h() -> None:
    f = _flight(duration="2h")
    assert "最快" in _derive_tags(f)


def test_tags_slow_3h_no_fastest() -> None:
    f = _flight(duration="3h")
    assert "最快" not in _derive_tags(f)


def test_tags_discount_over_30pct() -> None:
    """lowestPrice < fullPrice * 0.7 → 显示省X%."""
    f = _flight(lowest_price=500, full_price=1000)
    tags = _derive_tags(f)
    assert any(t.startswith("省") and t.endswith("%") for t in tags)


def test_tags_no_discount_under_30pct() -> None:
    f = _flight(lowest_price=800, full_price=1000)
    tags = _derive_tags(f)
    assert not any(t.startswith("省") for t in tags)


def test_tags_capped_at_3() -> None:
    f = _flight(stops=0, meal=True, dep_time="08:00")
    f["legs"][0]["aircraftName"] = "A350"
    f["lowestPrice"] = 100
    f["fullPrice"] = 1000
    assert len(_derive_tags(f)) <= 3


# ---------------------------------------------------------------------------
# _build_plans
# ---------------------------------------------------------------------------


def test_default_plan_kind_yields_3_plans() -> None:
    fl = [_flight(flight_id="a"), _flight(flight_id="b", lowest_price=1000), _flight(flight_id="c", duration="3h")]
    plans = _build_plans(fl, PLAN_KIND_DEFAULT)
    assert len(plans) == 3
    assert [p["id"] for p in plans] == ["fastest", "cheapest", "comfortable"]


def test_cheapest_yields_1_plan() -> None:
    fl = [_flight(lowest_price=100), _flight(lowest_price=500)]
    plans = _build_plans(fl, PLAN_KIND_CHEAPEST)
    assert len(plans) == 1
    assert plans[0]["id"] == "cheapest"
    assert plans[0]["flights"][0]["price"] == 100


def test_fastest_yields_1_plan() -> None:
    fl = [_flight(duration="2h"), _flight(duration="5h")]
    plans = _build_plans(fl, PLAN_KIND_FASTEST)
    assert len(plans) == 1
    assert plans[0]["id"] == "fastest"
    assert plans[0]["flights"][0]["duration"] == "2h"


def test_comfortable_yields_1_plan() -> None:
    fl = [_flight(flight_id="a", stops=0), _flight(flight_id="b", stops=2)]
    plans = _build_plans(fl, PLAN_KIND_COMFORTABLE)
    assert plans[0]["id"] == "comfortable"
    assert plans[0]["flights"][0]["flightId"] == "a"


def test_user_explicit_takes_first() -> None:
    fl = [_flight(flight_id="first"), _flight(flight_id="second")]
    plans = _build_plans(fl, PLAN_KIND_USER_EXPLICIT)
    assert plans[0]["id"] == "recommended"
    assert plans[0]["flights"][0]["flightId"] == "first"


def test_top3_limits_to_3() -> None:
    fl = [_flight(flight_id=f"f{i}", lowest_price=1000 - i * 10) for i in range(10)]
    plans = _build_plans(fl, PLAN_KIND_CHEAPEST)
    assert len(plans[0]["flights"]) == 3


# ---------------------------------------------------------------------------
# _build_summary
# ---------------------------------------------------------------------------


def test_summary_empty_flight_list() -> None:
    out = _build_summary([], plan_kind=PLAN_KIND_DEFAULT)
    assert out["totalCount"] == 0
    assert out["searchType"] == "全量查询"
    assert out["depCity"] == ""


def test_summary_uses_first_flight_for_cities() -> None:
    fl = [_flight(dep_code="PEK", arr_code="PVG", dep_date="2026-06-06")]
    out = _build_summary(fl, plan_kind=PLAN_KIND_DEFAULT)
    assert out["depCity"] == "北京"
    assert out["arrCity"] == "上海"
    assert out["depDate"] == "2026-06-06"


def test_summary_search_type_by_plan_kind() -> None:
    fl = [_flight()]
    assert _build_summary(fl, plan_kind=PLAN_KIND_CHEAPEST)["searchType"] == "经济舱最低价"
    assert _build_summary(fl, plan_kind=PLAN_KIND_FASTEST)["searchType"] == "最快抵达"
    assert _build_summary(fl, plan_kind=PLAN_KIND_COMFORTABLE)["searchType"] == "舒适首选"
    assert _build_summary(fl, plan_kind=PLAN_KIND_USER_EXPLICIT)["searchType"] == "按你需求"


# ---------------------------------------------------------------------------
# present_flight_result (public API)
# ---------------------------------------------------------------------------


def test_present_default_3_plans_with_summary() -> None:
    fl = [_flight(), _flight(flight_id="b", lowest_price=200)]
    out = present_flight_result({"plan_kind": "default", "flightList": fl})
    assert "summary" in out
    assert "plans" in out
    assert len(out["plans"]) == 3
    assert out["summary"]["totalCount"] == 2


def test_present_empty_flight_list() -> None:
    out = present_flight_result({"plan_kind": "default", "flightList": []})
    assert out["plans"] == []
    assert out["summary"]["totalCount"] == 0


def test_present_invalid_plan_kind_falls_back_to_default() -> None:
    fl = [_flight(), _flight(flight_id="b")]
    out = present_flight_result({"plan_kind": "BOGUS", "flightList": fl})
    assert len(out["plans"]) == 3  # default 3 方案


def test_present_no_flight_list_treated_as_empty() -> None:
    out = present_flight_result({"plan_kind": "default"})
    assert out["plans"] == []


def test_present_preference_ignored_for_now() -> None:
    """preference 字段预留, v4.1 接入. 当前不报错."""
    fl = [_flight()]
    out = present_flight_result({"plan_kind": "cheapest", "flightList": fl, "preference": "最快"})
    assert out["plans"][0]["id"] == "cheapest"  # plan_kind 胜出


def test_present_each_plan_kind_round_trip() -> None:
    """5 种 plan_kind 都能完整通过."""
    fl = [_flight(), _flight(flight_id="b", lowest_price=200, duration="4h")]
    for kind in [PLAN_KIND_DEFAULT, PLAN_KIND_CHEAPEST, PLAN_KIND_FASTEST,
                 PLAN_KIND_COMFORTABLE, PLAN_KIND_USER_EXPLICIT]:
        out = present_flight_result({"plan_kind": kind, "flightList": fl})
        assert "summary" in out
        assert "plans" in out
        assert len(out["plans"]) >= 1
        # 每个 plan 的 flight 都有 flightId 字段
        for plan in out["plans"]:
            for f in plan["flights"]:
                assert "flightId" in f
                assert "price" in f
                assert "tags" in f
