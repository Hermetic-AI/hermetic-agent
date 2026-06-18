"""
Normalize user input for international flight search.

Input: JSON file with raw user plan
Output: JSON file with normalized plan ready for intShopping

Usage:
    python normalize_request.py plan.json
    python normalize_request.py plan.json --output normalized.json
"""
import json
import sys
import re
from datetime import datetime, timedelta

WEEKDAY_MAP = {
    "周一": 0, "周二": 1, "周三": 2, "周四": 3,
    "周五": 4, "周六": 5, "周日": 6,
    "星期一": 0, "星期二": 1, "星期三": 2, "星期四": 3,
    "星期五": 4, "星期六": 5, "星期日": 6,
}

CAB_CLASS_MAP = {
    "头等舱": "FIRST", "超级头等舱": "PREMIUM_FIRST",
    "商务舱": "BUSINESS", "超级商务舱": "PREMIUM_BUSINESS",
    "经济舱": "ECONOMY", "高级经济舱": "PREMIUM_ECONOMY",
}

PASSENGER_TYPE_MAP = {
    "成人": "ADT", "儿童": "CHD", "婴儿": "INF",
}

CITY_CODE_OVERRIDES = {
    "深圳": "SZX", "北京": "PEK", "上海": "PVG",
    "广州": "CAN", "香港": "HKG", "台北": "TPE",
    "东京": "NRT", "大阪": "KIX", "首尔": "ICN",
    "曼谷": "BKK", "新加坡": "SIN", "吉隆坡": "KUL",
    "伦敦": "LHR", "巴黎": "CDG", "法兰克福": "FRA",
    "阿姆斯特丹": "AMS", "悉尼": "SYD", "墨尔本": "MEL",
    "洛杉矶": "LAX", "纽约": "JFK", "旧金山": "SFO",
    "芝加哥": "ORD", "多伦多": "YYZ", "温哥华": "YVR",
    "迪拜": "DXB", "新德里": "DEL", "开罗": "CAI",
}


def normalize_date(raw: str, today: datetime | None = None) -> str:
    if not raw:
        return ""
    today = today or datetime.now()
    raw = raw.strip()

    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw

    if raw in ("今天", "今日"):
        return today.strftime("%Y-%m-%d")
    if raw in ("明天", "明日"):
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")
    if raw in ("后天"):
        return (today + timedelta(days=2)).strftime("%Y-%m-%d")
    if raw.startswith("下周"):
        wd = WEEKDAY_MAP.get(raw[2:], None)
        if wd is not None:
            days_ahead = (wd - today.weekday() + 7) % 7
            if days_ahead == 0:
                days_ahead = 7
            return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    m = re.match(r"(\d+)天后", raw)
    if m:
        return (today + timedelta(days=int(m.group(1)))).strftime("%Y-%m-%d")

    m = re.match(r"(\d{1,2})月(\d{1,2})[日号]", raw)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        year = today.year
        if month < today.month or (month == today.month and day < today.day):
            year += 1
        return f"{year:04d}-{month:02d}-{day:02d}"

    return raw


def normalize_cab_class(raw: str) -> str | None:
    if not raw:
        return None
    return CAB_CLASS_MAP.get(raw.strip())


def normalize_passenger_type(raw: str) -> str:
    if not raw:
        return "ADT"
    return PASSENGER_TYPE_MAP.get(raw.strip(), "ADT")


def normalize_city(raw: str) -> str:
    if not raw:
        return ""
    raw = raw.strip()
    if len(raw) == 3 and raw.isalpha():
        return raw.upper()
    return CITY_CODE_OVERRIDES.get(raw, raw)


def normalize_plan(plan: dict) -> dict:
    today = datetime.now()
    result = {
        "fromCity": normalize_city(plan.get("fromCity", "")),
        "toCity": normalize_city(plan.get("toCity", "")),
        "flyDate": normalize_date(plan.get("flyDate", ""), today),
        "returnDate": normalize_date(plan.get("returnDate", ""), today) if plan.get("returnDate") else None,
        "passengerType": normalize_passenger_type(plan.get("passengerType", "")),
        "cabClass": normalize_cab_class(plan.get("cabClass", "")),
        "stopQuantity": 0 if plan.get("directOnly") else (plan.get("stopQuantity", 0) if plan.get("stopQuantity") is not None else 0),
        "airIdList": plan.get("airIdList", []),
    }

    trip_list = [{
        "fromCity": result["fromCity"],
        "toCity": result["toCity"],
        "flyDate": result["flyDate"],
        "isCity": True
    }]
    if result["returnDate"]:
        trip_list.append({
            "fromCity": result["toCity"],
            "toCity": result["fromCity"],
            "flyDate": result["returnDate"],
            "isCity": True
        })
    result["tripList"] = trip_list

    errors = []
    if not result["fromCity"]:
        errors.append("缺少出发城市")
    if not result["toCity"]:
        errors.append("缺少到达城市")
    if not result["flyDate"]:
        errors.append("缺少出发日期")
    result["errors"] = errors

    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: python normalize_request.py <plan.json> [--output out.json]")
        sys.exit(1)
    with open(sys.argv[1], encoding="utf-8") as f:
        plan = json.load(f)
    result = normalize_plan(plan)
    out_path = None
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        if idx + 1 < len(sys.argv):
            out_path = sys.argv[idx + 1]
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(output)
    else:
        print(output)


if __name__ == "__main__":
    main()
