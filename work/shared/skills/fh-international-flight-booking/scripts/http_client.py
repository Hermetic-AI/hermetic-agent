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


def _autofill_required_fields(path: str, body: dict) -> dict:
    """Inject required body fields the upstream silently drops when missing.

    The fh-travel BFF returns ``TMS_1002 / 网络异常`` for some endpoints when
    the body is empty or a required productType discriminator is missing,
    instead of a proper 4xx. Patch known offenders here so weak LLMs that
    call these with ``{}`` still succeed.

    Currently:
      * ``/air/customer/getClientBasicData`` requires ``productType=INTERNATIONAL``
        for the international flow (default for this skill).
    """
    if path == "/air/customer/getClientBasicData":
        if not body or "productType" not in body:
            return {**body, "productType": "INTERNATIONAL"}
    return body


def api_post(path: str, body: dict, timeout: float | None = None) -> dict:
    url = f"{get_base_url()}{path}"
    body = _autofill_required_fields(path, body or {})
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


def _resolve_workspace_dir() -> str | None:
    """Pick a writable workspace dir visible to Hub for large-output spill.

    Priority:
      1. $FH_OUTPUT_DIR (explicit override)
      2. $WORKSPACE_PATH (Hub convention; set on Hub container)
      3. $WORKSPACE_CWD (opencode sandbox convention; set on sandbox container)
      4. None — caller will print inline JSON (and risk opencode stdout truncation)

    Must be RO bind-mount visible to Hub (`./work` -> `/app/work:ro`).
    Hub reads spilled files via openagent.auip.intl_flight_card._parse_output.
    """
    explicit = os.environ.get("FH_OUTPUT_DIR")
    if explicit:
        return explicit
    for var in ("WORKSPACE_PATH", "WORKSPACE_CWD"):
        ws = os.environ.get(var)
        if ws and os.path.isdir(ws):
            return ws
    return None


def _spill_and_marker(
    result: dict,
    workspace_dir: str,
    threshold_bytes: int = 8192,
    path: str = "",
) -> None:
    """If result is large, spill full JSON to workspace file + print small marker.

    Opencode sandbox truncates bash stdout by chopping head AND tail, leaving a
    middle slice that is not valid JSON. By emitting a tiny marker instead and
    saving the full payload to a file in the workspace (host bind-mounted to
    Hub's `/app/work`), the Hub can read the file end-to-end via
    `openagent.auip.intl_flight_card._parse_output`.

    For known high-volume paths (e.g. ``/air/domestic/getPlaneSendpki`` which
    returns a 12-person ``approveUserList``), shrink the response inline
    *before* the threshold check, so the LLM never sees the long tail.

    Marker shape (small, ~500 bytes):
      {
        "_hub_marker": "full_output_spilled",
        "_output_file": "<abs path>",
        "_size_bytes": 363916,
        "errorCode": "0",
        "errorMsg": "",
        "data": {
          "serialNumber": "...",
          "flightCount": 15,
          "cityList": [...],   // small reference fields inline
          "airwayList": [...]   // for Hub card assembly
        }
      }
    """
    if path == "/air/domestic/getPlaneSendpki":
        result = _shrink_get_plane_sendpki(result)
    elif path == "/air/customer/getPassengerAllAddress":
        result = _shrink_get_passenger_all_address(result)

    try:
        full_json = json.dumps(result, ensure_ascii=False)
    except (TypeError, ValueError):
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if len(full_json.encode("utf-8")) <= threshold_bytes:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    spill_dir = os.path.join(workspace_dir, ".opencode-tool-output")
    os.makedirs(spill_dir, exist_ok=True)
    import uuid
    fname = f"spill_{uuid.uuid4().hex[:12]}.json"
    fpath = os.path.join(spill_dir, fname)
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(full_json)

    inner = result.get("data") or {}
    marker = {
        "_hub_marker": "full_output_spilled",
        "_output_file": fpath,
        "_size_bytes": len(full_json.encode("utf-8")),
        "errorCode": str(result.get("errorCode", "0")),
        "errorMsg": result.get("errorMsg", "") or "",
        "data": {
            "serialNumber": inner.get("serialNumber", "") if isinstance(inner, dict) else "",
            "flightCount": len(inner.get("groupList", []))
            if isinstance(inner, dict) and isinstance(inner.get("groupList"), list)
            else 0,
            "cityList": inner.get("cityList", []) if isinstance(inner, dict) else [],
            "airwayList": inner.get("airwayList", []) if isinstance(inner, dict) else [],
        },
    }
    print(json.dumps(marker, ensure_ascii=False))


def _shrink_get_plane_sendpki(result: dict) -> dict:
    """Strip high-volume fields LLM never uses after the decision is made.

    getPlaneSendpki returns ~5KB including 12 approvers and full flight/passenger
    details. After the LLM reads ``payType`` (online vs. bill-back) and
    ``violatePolicy`` it has all it needs to either:
      * submit online payment (needs ``orderBasicDataJson``), or
      * show approver names + tell the user to pay via the enterprise portal.

    Approver detail rows (``phone``/``email``/``sameDepId``) and ticket-level
    flight/passenger dumps waste ~3KB of context for zero decision value.
    """
    if not isinstance(result, dict) or str(result.get("errorCode", "0")) != "0":
        return result
    data = result.get("data")
    if not isinstance(data, dict):
        return result

    slim_data: dict = {
        "payType": data.get("payType"),
        "violatePolicy": data.get("violatePolicy"),
        "showViolatePolicy": data.get("showViolatePolicy"),
        "ticketTime": data.get("ticketTime", ""),
        "paymentKind": data.get("paymentKind", ""),
        "approvalTel": data.get("approvalTel", False),
        "approvalWx": data.get("approvalWx", False),
        "smsApproval": data.get("smsApproval", False),
        "diffCash": (data.get("diffcashData") or {}).get("diffCashOrder", 0)
        if isinstance(data.get("diffcashData"), dict)
        else 0,
        "approverCount": len(data.get("approveUserList") or []),
        "approvers": [
            {
                "id": u.get("id"),
                "name": u.get("name"),
                "depName": u.get("depName", ""),
            }
            for u in (data.get("approveUserList") or [])[:5]
            if isinstance(u, dict)
        ],
        "orderList": [],
        "orderBasicDataJson": data.get("orderBasicDataJson", ""),
    }

    for ol in data.get("orderList") or []:
        if not isinstance(ol, dict):
            continue
        slim_ol = {
            "orderId": ol.get("orderId"),
            "subOrderId": ol.get("subOrderId"),
            "recPrice": ol.get("recPrice"),
            "payPrice": ol.get("payPrice"),
            "publicExpense": ol.get("publicExpense"),
            "paymentKind": ol.get("paymentKind"),
            "ticketProductName": ol.get("ticketProductName", ""),
            "tgq": [
                {
                    "airId": t.get("airId"),
                    "fromCity": t.get("fromCity"),
                    "toCity": t.get("toCity"),
                    "cabin": t.get("cabin"),
                    "flyDate": t.get("flyDate"),
                    "refundRule": str(t.get("refundRule", ""))[:200],
                    "changeRule": str(t.get("changeRule", ""))[:200],
                }
                for t in (ol.get("orderPlaneTgqList") or [])[:3]
                if isinstance(t, dict)
            ],
        }
        slim_data["orderList"].append(slim_ol)

    return {**result, "data": slim_data}


def _shrink_get_passenger_all_address(result: dict) -> dict:
    """Strip unused historical addresses; keep only ``current`` one.

    Response shape:
      {"errorCode":"0", "data": {"dataList": [{current, address, ...}, ...]}}
    For LLM decision only the current address matters.
    """
    if not isinstance(result, dict) or str(result.get("errorCode", "0")) != "0":
        return result
    data = result.get("data")
    if not isinstance(data, dict):
        return result
    items = data.get("dataList") or []
    if not isinstance(items, list):
        return result
    current = next(
        (it for it in items if isinstance(it, dict) and it.get("current")),
        items[0] if items else None,
    )
    return {**result, "data": {"current": current or {}}}


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
    workspace = _resolve_workspace_dir()
    if workspace:
        _spill_and_marker(result, workspace, path=path)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
