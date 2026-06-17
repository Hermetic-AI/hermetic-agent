#!/usr/bin/env python3
"""Check whether an MCP tool is reasonable for the current booking stage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_contracts() -> dict:
    root = Path(__file__).resolve().parent.parent
    return json.loads((root / "schemas" / "tool-contracts.json").read_text(encoding="utf-8"))


def check(tool: str, stage: str, contracts: dict | None = None) -> dict:
    contracts = contracts or load_contracts()
    entry = contracts["tools"].get(tool)
    if not entry:
        return {"allowed": None, "tool": tool, "stage": stage, "reason": "unknown tool"}
    stages = entry.get("stages", [])
    allowed = "*" in stages or stage in stages
    return {
        "allowed": allowed,
        "tool": tool,
        "stage": stage,
        "expectedStages": stages,
        "required": entry.get("required", []),
        "requiredOneOf": entry.get("requiredOneOf", []),
        "fixHint": None if allowed else f"current stage {stage} is not in allowed stages for {tool}"
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tool", required=True)
    parser.add_argument("--stage", required=True)
    args = parser.parse_args()
    result = check(args.tool, args.stage)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["allowed"] in (True, None) else 2


if __name__ == "__main__":
    raise SystemExit(main())
