"""
Render international flight options as AGUI v2 contentJson.

Input: compact JSON (from compact_intl_payload.py output) or raw intShopping response
Output: AGUI v2 contentJson JSON to stdout (for ask_user card body)

Usage:
    python render_intl_options.py compact.json
    python render_intl_options.py compact.json --limit 10
    python render_intl_options.py raw_result.json --raw
"""
import json
import sys


AIRCRAFT_TYPE_MAP = {
    "32N": "A320neo", "320": "A320", "321": "A321", "32A": "A319",
    "32Q": "A321neo", "319": "A319", "333": "A330-300", "332": "A330-200",
    "359": "A350-900", "35K": "A350-1000", "388": "A380",
    "738": "B737-800", "739": "B737-900", "7M8": "B737 MAX 8",
    "789": "B787-9", "78X": "B787-10", "77W": "B777-300ER",
    "772": "B777-200", "744": "B747-400",
}

CAB_CLASS_LABELS = {
    "Y": "经济舱", "W": "高级经济舱", "C": "商务舱", "F": "头等舱",
    "Y1": "经济舱", "W1": "高级经济舱",
}

MEAL_TRUE = {"S", "M", "L", "D", "B", "早餐", "午餐", "晚餐", "小食", "正餐", "含餐"}


def _time_part(value: str) -> str:
    if not value:
        return ""
    if " " in value:
        return value.split(" ", 1)[1][:5]
    return value[:5]


def _date_part(value: str) -> str:
    if not value:
        return ""
    return value.split(" ")[0]


def _aircraft_name(type_code: str, type_group: str = "") -> str:
    name = AIRCRAFT_TYPE_MAP.get(type_code, "")
    if not name and type_group:
        name = AIRCRAFT_TYPE_MAP.get(type_group, type_group)
    return name or type_code or ""


def _meal_bool(meal_val: str) -> bool:
    if not meal_val:
        return False
    return str(meal_val).strip() in MEAL_TRUE


def _arr_day_offset(dep_date: str, arr_date: str) -> int:
    if not dep_date or not arr_date:
        return 0
    try:
        from datetime import datetime
        d1 = datetime.strptime(_date_part(dep_date), "%Y-%m-%d")
        d2 = datetime.strptime(_date_part(arr_date), "%Y-%m-%d")
        return (d2 - d1).days
    except (ValueError, TypeError):
        return 0


def build_flight_list(
    compact: dict,
    city_map: dict,
    airway_map: dict,
    limit: int,
) -> list[dict]:
    groups = compact.get("groupList", [])[:limit]
    flights = []

    for idx, group in enumerate(groups):
        trips = group.get("tripList", [])
        if not trips:
            continue
        trip = trips[0]
        flight_list = trip.get("flightList", [])
        if not flight_list:
            continue

        fl = flight_list[0]
        flight_id = fl.get("flightId", "")
        air_id = flight_id[:2].upper() if len(flight_id) >= 2 else ""
        airline_name = airway_map.get(air_id, air_id)

        fly_date = fl.get("flyDate", "")
        arr_date = fl.get("arrDate", "")
        dep_date = _date_part(fly_date)
        dep_time = _time_part(fly_date)
        arr_time = _time_part(arr_date)
        arr_date_only = _date_part(arr_date)
        duration_min = fl.get("duration", 0) or 0

        air_line = trip.get("airLine", "")
        dep_code = air_line[:3] if len(air_line) >= 6 else ""
        arr_code = air_line[3:6] if len(air_line) >= 6 else ""
        dep_city = city_map.get(dep_code, dep_code)
        arr_city = city_map.get(arr_code, arr_code)

        from_port = (fl.get("fromPort") or "").strip()
        to_port = (fl.get("toPort") or "").strip()
        stops = fl.get("stopList", [])
        stop_count = len(stops) if isinstance(stops, list) else 0

        lowest_price = 0
        lowest_cab = "经济舱"
        prices = group.get("priceList", [])
        if prices:
            p = prices[0]
            lowest_price = p.get("totalPrice", 0) or p.get("price", 0) or 0
            trip_prices = p.get("tripList", [])
            if trip_prices:
                cab_class = trip_prices[0].get("cabClass", "Y")
                lowest_cab = CAB_CLASS_LABELS.get(cab_class, "经济舱")

        leg = {
            "direction": "OUTBOUND",
            "flightNo": flight_id,
            "airlineName": airline_name,
            "depDate": dep_date,
            "depTime": dep_time,
            "arrTime": arr_time,
            "arrDate": arr_date_only,
            "depAirportName": "",
            "depTerminal": from_port,
            "arrAirportName": "",
            "arrTerminal": to_port,
            "duration": duration_min,
            "aircraftName": _aircraft_name(fl.get("type", ""), fl.get("typeGroup", "")),
            "meal": _meal_bool(fl.get("meal", "")),
            "shareFlight": False,
            "shareId": "",
            "stops": [],
            "arrDayOffset": _arr_day_offset(dep_date, arr_date),
        }

        flights.append({
            "depCityName": dep_city,
            "arrCityName": arr_city,
            "depDate": dep_date,
            "depTime": dep_time,
            "arrDate": arr_date_only,
            "arrTime": arr_time,
            "lowestPrice": lowest_price,
            "lowestCabinName": lowest_cab,
            "totalPrice": lowest_price,
            "totalDuration": duration_min,
            "durationMin": duration_min,
            "stopCount": stop_count,
            "transferCount": 0,
            "transferCities": [],
            "airlineName": airline_name,
            "flightNo": flight_id,
            "airId": air_id,
            "tripType": "OW",
            "serialNo": idx + 1,
            "flightId": flight_id,
            "legs": [leg],
            "depAirportName": "",
            "depTerminal": from_port,
            "arrAirportName": "",
            "arrTerminal": to_port,
            "shareFlight": False,
            "shareId": "",
            "arrDayOffset": _arr_day_offset(dep_date, arr_date),
        })

    return flights


def render_agui_content(compact: dict, limit: int = 10) -> dict:
    city_list = compact.get("cityList", [])
    airway_list = compact.get("airwayList", [])
    city_map = {
        c.get("cityCode", ""): c.get("cityName", "") or c.get("airPortName", "")
        for c in city_list
    }
    airway_map = {
        a.get("companyNo", ""): a.get("companyName", "")
        for a in airway_list
    }

    total = compact.get("groupCount", len(compact.get("groupList", [])))
    flight_list = build_flight_list(compact, city_map, airway_map, limit)
    filtered = len(flight_list)

    data_str = f"共查询到{total}个航班组合"
    if filtered < total:
        data_str += f"，展示前{filtered}条"

    return {
        "schemaVersion": "2",
        "dataList": [
            {
                "basicType": "AIR_DOMESTIC_FLIGHT_LIST",
                "dataStr": data_str,
                "dataJson": {
                    "serialNumber": compact.get("serialNumber", ""),
                    "totalCount": total,
                    "filteredCount": filtered,
                    "flightList": flight_list,
                },
                "linkUrl": "",
            }
        ],
        "thinkingSteps": ["已按您的行程条件查询国际航班并整理列表"],
    }


def main():
    limit = 10
    is_raw = True
    file_path = None
    json_str = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--limit":
            i += 1
            limit = int(args[i])
        elif args[i] == "--raw":
            is_raw = True
        elif args[i] == "--compact":
            is_raw = False
        elif args[i].startswith("{"):
            json_str = args[i]
        elif not args[i].startswith("-"):
            file_path = args[i]
        i += 1

    if json_str:
        data = json.loads(json_str)
    elif file_path:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
    elif not sys.stdin.isatty():
        data = json.load(sys.stdin)
    else:
        print("Usage: python render_intl_options.py [file.json | '<json>'] [--limit N] [--raw|--compact]")
        print("       or pipe JSON via stdin: echo '{...}' | python render_intl_options.py")
        sys.exit(1)

    if is_raw:
        compact = data.get("data", data)
    else:
        compact = data

    result = render_agui_content(compact, limit)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
