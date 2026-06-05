"""flight_query presenter (L3) — LLM 极简输入 (plan_kind + flightList) 转完整 AUIP 卡片.

业务规则集中在本模块, 不在 LLM 脑子里. v4 SKILL.md 砍到 110 行,
"3 方案怎么排" / "tag 怎么派生" / "字段怎么映射" 全在这里 1ms 出.
"""
from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


PLAN_KIND_DEFAULT = "default"
PLAN_KIND_CHEAPEST = "cheapest"
PLAN_KIND_FASTEST = "fastest"
PLAN_KIND_COMFORTABLE = "comfortable"
PLAN_KIND_USER_EXPLICIT = "user_explicit"
VALID_PLAN_KINDS = frozenset({
    PLAN_KIND_DEFAULT, PLAN_KIND_CHEAPEST, PLAN_KIND_FASTEST,
    PLAN_KIND_COMFORTABLE, PLAN_KIND_USER_EXPLICIT,
})
_LARGE_AIRCRAFT = ("747", "777", "787", "A350", "A380")
_CABIN_CLASS_MAP = (
    ("头等", "FIRST"), ("一等", "FIRST"),
    ("公务", "BUSINESS"), ("商务", "BUSINESS"),
    ("超经", "PREMIUM_ECONOMY"), ("高级", "PREMIUM_ECONOMY"),
)
_AIRPORT_TO_CITY = {
    "PEK": "北京", "PKX": "北京", "BJS": "北京",
    "SHA": "上海", "PVG": "上海",
    "CAN": "广州", "SZX": "深圳", "CTU": "成都", "HGH": "杭州",
    "CKG": "重庆", "XIY": "西安", "KMG": "昆明", "NKG": "南京",
}
_SEARCH_TYPE_LABEL = {
    PLAN_KIND_CHEAPEST: "经济舱最低价", PLAN_KIND_FASTEST: "最快抵达",
    PLAN_KIND_COMFORTABLE: "舒适首选", PLAN_KIND_USER_EXPLICIT: "按你需求",
}


def present_flight_result(raw: dict) -> dict:
    """LLM 极简 payload (plan_kind + flightList) → 完整 AUIP FLIGHT_RESULT 卡片 body.

    输出不含 card_type/title 包装, 由 caller 拼.
    """
    plan_kind = raw.get("plan_kind", PLAN_KIND_DEFAULT)
    if plan_kind not in VALID_PLAN_KINDS:
        logger.warning("flight_query_invalid_plan_kind", plan_kind=plan_kind)
        plan_kind = PLAN_KIND_DEFAULT
    fl = raw.get("flightList") or []
    if not fl:
        return {"summary": _build_summary(fl, plan_kind=plan_kind), "plans": []}
    return {"summary": _build_summary(fl, plan_kind=plan_kind), "plans": _build_plans(fl, plan_kind)}


def _build_plans(fl: list[dict], plan_kind: str) -> list[dict]:
    if plan_kind == PLAN_KIND_DEFAULT:
        return [
            _make_plan(PLAN_KIND_FASTEST, "最快抵达", "用时最短", "duration", _top3(fl, _duration_minutes)),
            _make_plan(PLAN_KIND_CHEAPEST, "最便宜", "价格最低", "price", _top3(fl, _price)),
            _make_plan(PLAN_KIND_COMFORTABLE, "直飞首选", "大飞机直飞", "comfort", _top3(fl, _comfort_score, reverse=True)),
        ]
    if plan_kind == PLAN_KIND_CHEAPEST:
        return [_make_plan(PLAN_KIND_CHEAPEST, "最便宜", "价格最低", "price", _top3(fl, _price))]
    if plan_kind == PLAN_KIND_FASTEST:
        return [_make_plan(PLAN_KIND_FASTEST, "最快抵达", "用时最短", "duration", _top3(fl, _duration_minutes))]
    if plan_kind == PLAN_KIND_COMFORTABLE:
        return [_make_plan(PLAN_KIND_COMFORTABLE, "舒适首选", "大飞机直飞", "comfort", _top3(fl, _comfort_score, reverse=True))]
    return [_make_plan("recommended", "为你找到", "已按你需求筛选", "user", fl[:3])]


def _make_plan(plan_id: str, title: str, subtitle: str, criteria: str, flights: list[dict]) -> dict:
    return {
        "id": plan_id, "title": title, "subtitle": subtitle, "criteria": criteria,
        "flights": [_flight_to_auip(f, i) for i, f in enumerate(flights)],
    }


def _top3(fl: list[dict], key, reverse: bool = False) -> list[dict]:
    if not fl:
        return []
    try:
        return sorted(fl, key=key, reverse=reverse)[:3]
    except Exception as e:
        logger.warning("flight_query_sort_failed", error=str(e))
        return fl[:3]


def _price(f: dict) -> float:
    return float(f.get("lowestPrice") or 0)


def _duration_minutes(f: dict) -> int:
    m = _parse_duration(f.get("totalDuration") or "")
    return m if m > 0 else 99999


def _comfort_score(f: dict) -> int:
    """越大越舒适: 直飞 (0 停) + 大飞机 + 有餐."""
    score = 0
    if int(f.get("stopCount", 1)) == 0:
        score += 100
    leg = (f.get("legs") or [{}])[0] if f.get("legs") else {}
    if any(k in (leg.get("aircraftName") or "").upper() for k in _LARGE_AIRCRAFT):
        score += 50
    if leg.get("meal"):
        score += 5
    return score


def _parse_duration(s: str) -> int:
    """'2h20m' -> 140. '150m' -> 150. '3h' -> 180."""
    if not s:
        return 0
    h, m = 0, 0
    if "h" in s:
        try:
            h = int(s.split("h")[0].strip())
        except (ValueError, IndexError):
            h = 0
        rest = s.split("h", 1)[1]
    else:
        rest = s
    if "m" in rest:
        try:
            m = int(rest.replace("m", "").strip())
        except ValueError:
            m = 0
    return h * 60 + m


# ---- Field mapping (MCP flightList[i] → AUIP FlightSegment) -----------------


def _flight_to_auip(raw: dict, idx: int) -> dict:
    leg = (raw.get("legs") or [{}])[0] if raw.get("legs") else {}
    cabin = raw.get("lowestCabinName", "")
    meal = leg.get("meal")
    out: dict = {
        "flightId": raw.get("flightId", f"flt-{idx}"),
        "flightNo": raw.get("flightNo", ""),
        "shareFlight": bool(raw.get("shareFlight", False)),
        "airline": {"code": raw.get("airId", ""), "name": leg.get("airlineName", "")},
        "aircraft": _clean_aircraft(leg.get("aircraftName", "")),
        "date": raw.get("depDate", ""),
        "departure": _endpoint(leg, "dep", raw.get("depAirportCode", "")),
        "arrival": _endpoint(leg, "arr", raw.get("arrAirportCode", "")),
        "duration": raw.get("totalDuration", ""),
        "stops": int(raw.get("stopCount", 0)),
        "cabin": cabin,
        "cabinClass": _cabin_to_class(cabin),
        "meal": "是" if meal is True else ("否" if meal is False else None),
        "price": float(raw.get("lowestPrice") or 0),
        "tags": _derive_tags(raw),
    }
    if raw.get("shareFlight") and leg.get("airlineName"):
        out["shareInfo"] = f"共享{leg['airlineName']}"
    if raw.get("fullPrice"):
        out["fullPrice"] = float(raw["fullPrice"])
    return out


def _endpoint(leg: dict, prefix: str, airport_code: str) -> dict:
    return {
        "city": _AIRPORT_TO_CITY.get(airport_code, airport_code),
        "airport": leg.get(f"{prefix}AirportName", ""),
        "airportCode": airport_code,
        "terminal": leg.get(f"{prefix}Terminal"),
        "time": leg.get(f"{prefix}Time", ""),
    }


def _cabin_to_class(cabin: str) -> str:
    for keyword, cls in _CABIN_CLASS_MAP:
        if keyword in cabin:
            return cls
    return "ECONOMY"


def _clean_aircraft(name: str) -> str:
    return name.replace("(大)", "").replace("(中)", "").replace("(小)", "").strip()


# ---- Tag derivation --------------------------------------------------------


def _derive_tags(raw: dict) -> list[str]:
    """0-3 个 tag, 优先级: 省X%/直飞/最快/含餐/早班/晚班, 去重保 3."""
    tags: list[str] = []
    price = float(raw.get("lowestPrice") or 0)
    full = float(raw.get("fullPrice") or 0)
    if full > 0 and price > 0 and price < full * 0.7:
        tags.append(f"省{round((1 - price / full) * 100)}%")
    leg = (raw.get("legs") or [{}])[0] if raw.get("legs") else {}
    if int(raw.get("stopCount", 1)) == 0:
        ac_upper = (leg.get("aircraftName") or "").upper()
        tags.append("大飞机直飞" if any(k in ac_upper for k in _LARGE_AIRCRAFT) else "直飞")
    if _parse_duration(raw.get("totalDuration", "")) <= 150:
        tags.append("最快")
    if leg.get("meal"):
        tags.append("含餐")
    try:
        h = int((leg.get("depTime") or "").split(":")[0])
    except (ValueError, IndexError):
        h = -1
    if 6 <= h < 12:
        tags.append("早班")
    elif 18 <= h < 24:
        tags.append("晚班")
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        if t not in seen and len(out) < 3:
            seen.add(t)
            out.append(t)
    return out


# ---- Summary ---------------------------------------------------------------


def _build_summary(fl: list[dict], *, plan_kind: str | None = None,
                  search_type: str | None = None) -> dict:
    st = search_type or _SEARCH_TYPE_LABEL.get(plan_kind or "", "全量查询")
    if not fl:
        return {"totalCount": 0, "filteredCount": 0, "searchType": st,
                "depCity": "", "arrCity": "", "depDate": ""}
    first = fl[0]
    return {
        "totalCount": len(fl), "filteredCount": len(fl), "searchType": st,
        "depCity": _AIRPORT_TO_CITY.get(first.get("depAirportCode", ""), first.get("depAirportCode", "")),
        "arrCity": _AIRPORT_TO_CITY.get(first.get("arrAirportCode", ""), first.get("arrAirportCode", "")),
        "depDate": first.get("depDate", ""),
    }


__all__ = ["present_flight_result", "PLAN_KIND_DEFAULT"]
