#!/usr/bin/env python3
"""Normalize and validate a domestic flight booking plan."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta
from typing import Any

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}$")

ENUMS = {
    "roundTripListMode": {"RECOMMENDED", "FREE"},
    "cabinClass": {"ECONOMY", "FULL_ECONOMY", "BUSINESS", "FIRST"},
    "departureDayPart": {"MORNING", "AFTERNOON", "EVENING"},
    "sortBy": {"PRICE", "ARRIVAL_TIME", "DURATION", "REFUND_FLEXIBILITY"},
}

DAY_PART_ALIASES = {
    "morning": "MORNING",
    "am": "MORNING",
    "afternoon": "AFTERNOON",
    "pm": "AFTERNOON",
    "evening": "EVENING",
    "night": "EVENING",
}

DATE_ALIASES = {
    "today": 0,
    "tomorrow": 1,
    "day after tomorrow": 2,
}


def load_json(path: str | None) -> dict[str, Any]:
    text = sys.stdin.read() if not path or path == "-" else open(path, "r", encoding="utf-8").read()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("plan must be a JSON object")
    return value


def blank(value: Any) -> bool:
    return value is None or value == ""


def normalize_date(value: Any, today: date) -> Any:
    if not isinstance(value, str) or not value.strip():
        return value
    raw = value.strip()
    lower = raw.lower()
    if DATE_RE.match(raw):
        return raw
    if lower in DATE_ALIASES:
        return (today + timedelta(days=DATE_ALIASES[lower])).isoformat()
    return raw


def normalize(plan: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    out = dict(plan)
    for key in ("departureDate", "returnDate"):
        out[key] = normalize_date(out.get(key), today)
    for key in ENUMS:
        value = out.get(key)
        if isinstance(value, str):
            mapped = DAY_PART_ALIASES.get(value.strip().lower())
            out[key] = mapped or value.strip().upper()
    return out


def validate(plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in ("sessionId", "departureCity", "arrivalCity", "departureDate"):
        if blank(plan.get(key)):
            errors.append(f"missing required field: {key}")
    for key in ("departureDate", "returnDate"):
        value = plan.get(key)
        if not blank(value) and not (isinstance(value, str) and DATE_RE.match(value)):
            errors.append(f"{key} must be yyyy-MM-dd")
    for key in ("depTimeStart", "depTimeEnd"):
        value = plan.get(key)
        if not blank(value) and not (isinstance(value, str) and TIME_RE.match(value)):
            errors.append(f"{key} must be HH:mm")
    for key, allowed in ENUMS.items():
        value = plan.get(key)
        if not blank(value) and value not in allowed:
            errors.append(f"{key} must be one of {sorted(allowed)}")
    if not blank(plan.get("departureDayPart")) and (not blank(plan.get("depTimeStart")) or not blank(plan.get("depTimeEnd"))):
        errors.append("use either departureDayPart or depTimeStart/depTimeEnd, not both")
    if plan.get("maxPrice") is not None and not isinstance(plan.get("maxPrice"), int):
        errors.append("maxPrice must be an integer")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?")
    parser.add_argument("--today", help="Override current date as yyyy-mm-dd for deterministic tests")
    args = parser.parse_args()
    today = date.fromisoformat(args.today) if args.today else date.today()
    plan = normalize(load_json(args.path), today=today)
    errors = validate(plan)
    print(json.dumps({"valid": not errors, "errors": errors, "plan": plan}, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
