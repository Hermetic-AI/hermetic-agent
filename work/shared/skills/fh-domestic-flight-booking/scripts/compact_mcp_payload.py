#!/usr/bin/env python3
"""Compact fh-travel MCP payloads for progressive LLM disclosure."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

SUMMARY_KEYS = ["serialNumber", "resultSetId", "searchType", "roundTrip", "flightCount", "filteredCount", "notIncluded", "message"]

ALIASES = {
    "flightNo": ["flightNo", "outboundFlightNo", "flightNumber"],
    "returnFlightNo": ["returnFlightNo"],
    "airline": ["airlineName", "airline", "airlineCode", "airId"],
    "origin": ["depCityName", "origin", "departureCity", "fromCity"],
    "destination": ["arrCityName", "destination", "arrivalCity", "toCity"],
    "departTime": ["outboundDepDate", "departTime", "departureTime", "depTime"],
    "arriveTime": ["outboundArrDate", "arriveTime", "arrivalTime", "arrTime"],
    "returnDepartTime": ["returnDepDate"],
    "returnArriveTime": ["returnArrDate"],
    "durationMin": ["durationMin", "durationMinutes", "totalDuration"],
    "stopCount": ["stopCount", "transferCount"],
    "price": ["totalPrice", "lowestPrice", "price", "ticketPrice"],
    "cabin": ["lowestCabinName", "cabinName", "cabin", "cabinClass"],
    "meal": ["meal", "mealText", "requireMeal"],
    "baggage": ["baggage", "baggageText", "luggage"],
    "policy": ["policyCompliant", "policy", "policyText"],
    "cabId": ["cabId", "cabinId"]
}

LIST_KEYS = ["flightList", "flights", "items", "records", "list"]


def load(path: str | None) -> Any:
    text = sys.stdin.read() if not path or path == "-" else open(path, "r", encoding="utf-8").read()
    return json.loads(text)


def unwrap(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    if isinstance(value, dict):
        for key in ("data", "result", "payload", "content"):
            nested = value.get(key)
            if isinstance(nested, (dict, list, str)):
                unwrapped = unwrap(nested)
                if isinstance(unwrapped, (dict, list)):
                    return unwrapped
    return value


def find_list(value: Any) -> list[Any]:
    value = unwrap(value)
    if isinstance(value, list):
        return value
    if not isinstance(value, dict):
        return []
    for key in LIST_KEYS:
        item = value.get(key)
        if isinstance(item, list):
            return item
    for item in value.values():
        if isinstance(item, (dict, list)):
            found = find_list(item)
            if found:
                return found
    return []


def first(row: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def compact_row(row: Any, index: int) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {"index": index, "value": row}
    out: dict[str, Any] = {"index": index}
    for target, keys in ALIASES.items():
        value = first(row, keys)
        if value not in (None, "", [], {}):
            out[target] = value
    return out


def summarize(root: Any, rows: list[Any]) -> dict[str, Any]:
    root = unwrap(root)
    out: dict[str, Any] = {}
    if isinstance(root, dict):
        for key in SUMMARY_KEYS:
            value = root.get(key)
            if value not in (None, "", [], {}):
                out[key] = value
    prices = []
    for row in rows:
        if isinstance(row, dict):
            value = first(row, ALIASES["price"])
            if isinstance(value, (int, float)):
                prices.append(value)
    out.setdefault("flightCount", len(rows))
    if prices:
        out["lowestPrice"] = min(prices)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?")
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()
    payload = load(args.path)
    rows = find_list(payload)
    result = {
        "summary": summarize(payload, rows),
        "flights": [compact_row(row, i + 1) for i, row in enumerate(rows[: max(args.limit, 0)])],
        "omitted": max(len(rows) - max(args.limit, 0), 0)
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
