#!/usr/bin/env python3
"""Render compact flight options as a Markdown table."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

COLS = ["index", "flightNo", "airline", "departTime", "arriveTime", "durationMin", "stopCount", "price", "cabin"]


def load(path: str | None) -> dict[str, Any]:
    text = sys.stdin.read() if not path or path == "-" else open(path, "r", encoding="utf-8").read()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("compact payload must be an object")
    return value


def cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")


def render(data: dict[str, Any]) -> str:
    rows = data.get("flights") or []
    lines = [
        "| # | Flight | Airline | Depart | Arrive | Duration | Stops | Price | Cabin |",
        "|---|---|---|---|---|---:|---:|---:|---|",
    ]
    for row in rows:
        if not isinstance(row, dict):
            continue
        values = [cell(row.get(c)) for c in COLS]
        lines.append("| " + " | ".join(values) + " |")
    omitted = data.get("omitted")
    if isinstance(omitted, int) and omitted > 0:
        lines.append("")
        lines.append(f"Omitted {omitted} additional options. Ask to filter or show more.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?")
    args = parser.parse_args()
    print(render(load(args.path)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
