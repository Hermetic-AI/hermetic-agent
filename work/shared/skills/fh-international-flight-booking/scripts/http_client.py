"""
fh-international-flight-booking HTTP client wrapper.

Token injection: reads FLIGHT_API_KEY from environment (injected by Hub
at session start via sandbox admin /admin/env). All API calls go through
api_post() which auto-attaches the token header.

Usage (CLI, called by agent Bash tool):
    python3 http_client.py /air/international/intShopping body.json

    Body file can be:
      - A JSON file path (ends with .json)
      - A JSON string passed directly as second argument

Environment variables:
    FLIGHT_API_KEY    — auth token (required, injected by Hub)
    FH_TRAVEL_BASE_URL — API base URL (default: https://traveldev.feiheair.com/api)
"""
import os
import sys
import json
import requests

BASE_URL_ENV = "FH_TRAVEL_BASE_URL"
TOKEN_ENV = "FLIGHT_API_KEY"
DEFAULT_BASE = "https://traveldev.feiheair.com/api"
DEFAULT_TIMEOUT = 30.0

TIMEOUT_OVERRIDES = {
    "/air/international/intShopping": 60.0,
    "/air/international/waitSave": 45.0,
    "/air/international/saveOrder": 45.0,
    "/air/international/intPricing": 45.0,
}


def get_token() -> str:
    token = os.environ.get(TOKEN_ENV, "")
    if not token:
        print(json.dumps({
            "errorCode": "TOKEN_MISSING",
            "errorMsg": f"env var {TOKEN_ENV} not set, cannot auth. please restart session.",
            "data": None,
        }))
        sys.exit(1)
    return token


def get_base_url() -> str:
    return os.environ.get(BASE_URL_ENV, DEFAULT_BASE)


def build_headers(content_type: str = "application/json") -> dict:
    return {
        "Content-Type": content_type,
        "token": get_token(),
    }


def api_post(path: str, body: dict, timeout: float | None = None) -> dict:
    url = f"{get_base_url()}{path}"
    effective_timeout = timeout or TIMEOUT_OVERRIDES.get(path, DEFAULT_TIMEOUT)
    headers = build_headers()

    try:
        resp = requests.post(url, json=body, headers=headers, timeout=effective_timeout)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.Timeout:
        return {
            "errorCode": "FH_TIMEOUT",
            "errorMsg": f"API {path} timed out ({effective_timeout}s)",
            "data": None,
        }
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else 0
        text = e.response.text[:200] if e.response is not None else ""
        return {
            "errorCode": "FH_HTTP_ERROR",
            "errorMsg": f"HTTP {status}: {text}",
            "data": None,
        }
    except requests.exceptions.ConnectionError:
        return {
            "errorCode": "FH_UNREACHABLE",
            "errorMsg": f"network unreachable: {path}",
            "data": None,
        }
    except requests.exceptions.RequestException as e:
        return {
            "errorCode": "FH_REQUEST_ERROR",
            "errorMsg": str(e)[:200],
            "data": None,
        }

    if data.get("errorCode") and str(data["errorCode"]) != "0":
        return {
            "errorCode": data.get("errorCode", "UNKNOWN"),
            "errorMsg": data.get("errorMsg", "unknown biz error"),
            "data": None,
        }

    return data


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 http_client.py <path> <body_json_file_or_string>")
        sys.exit(1)
    path = sys.argv[1]
    body_arg = sys.argv[2]
    if os.path.isfile(body_arg):
        with open(body_arg, encoding="utf-8") as f:
            body = json.load(f)
    else:
        body = json.loads(body_arg)
    result = api_post(path, body)
    print(json.dumps(result, ensure_ascii=False, indent=2))
