"""
Stage guard: verify current state allows calling a specific API.

Usage:
    python stage_guard.py --stage FLIGHT_LISTED --api intRule
    python stage_guard.py --stage INIT --api intShopping

Exit 0 = allowed, Exit 1 = blocked (prints reason).
"""
import json
import sys
import os

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "schemas", "api-contracts.json")


def load_contracts() -> dict:
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)["api_contracts"]


def check(stage: str, api: str) -> tuple[bool, str]:
    contracts = load_contracts()
    if api not in contracts:
        return False, f"未知 API: {api}"
    contract = contracts[api]
    allowed = contract.get("allowed_stages", [])
    if stage not in allowed:
        return False, f"当前阶段 {stage} 不允许调用 {api}，允许阶段: {allowed}"
    return True, f"允许: 阶段 {stage} 可调用 {api}"


def main():
    stage = None
    api = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--stage":
            i += 1
            stage = args[i] if i < len(args) else None
        elif args[i] == "--api":
            i += 1
            api = args[i] if i < len(args) else None
        i += 1

    if not stage or not api:
        print("Usage: python stage_guard.py --stage <STAGE> --api <api_name>")
        sys.exit(2)

    allowed, reason = check(stage, api)
    print(reason)
    sys.exit(0 if allowed else 1)


if __name__ == "__main__":
    main()
