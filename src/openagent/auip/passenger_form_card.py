"""auip/passenger_form_card.py — Auto-assemble PASSENGER_FORM card from findPassenger.

When the LLM calls ``/air/customer/findPassenger`` and the response is
incomplete (missing fields the international order requires), this module
yields a ``PASSENGER_FORM`` ``StreamEvent`` so the user fills the rest via a
real form (text / date / select), not by typing free-form text messages.

Why Hub-side, not LLM-side:
  * The fh-travel BFF silently accepts a findPassenger match and reports
    success, even if ``birthDay``/``nationality``/``expiryDate``/``certNamePinyin``
    are empty. The LLM then has to remember to ask for the missing fields
    via plain text, which is slow + error-prone.
  * Hub watches the same tool_result stream and can interject with a
    structured form before the LLM even notices.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from openagent.providers.streaming import StreamEvent


# Fields required for an international saveOrder. Anything not returned by
# findPassenger needs to be collected via this form.
REQUIRED_FIELDS: list[dict[str, Any]] = [
    {
        "id": "passengerName",
        "label": "乘机人姓名（中文）",
        "type": "text",
        "required": True,
        "placeholder": "如：刘酝泽",
    },
    {
        "id": "passengerNamePinyin",
        "label": "护照拼音名（如 LIU/YUNZE）",
        "type": "text",
        "required": True,
        "placeholder": "姓/名，UPPERCASE",
    },
    {
        "id": "certType",
        "label": "证件类型",
        "type": "select",
        "required": True,
        "default": "0",
        "options": [
            {"value": "0", "label": "护照"},
            {"value": "1", "label": "港澳通行证"},
            {"value": "2", "label": "台胞证"},
            {"value": "3", "label": "回乡证"},
            {"value": "4", "label": "台湾通行证"},
        ],
    },
    {
        "id": "certNo",
        "label": "证件号码",
        "type": "text",
        "required": True,
        "placeholder": "护照号 / 证件号",
    },
    {
        "id": "nationality",
        "label": "国籍",
        "type": "select",
        "required": True,
        "default": "CN",
        "options": [
            {"value": "CN", "label": "中国"},
            {"value": "HK", "label": "中国香港"},
            {"value": "MO", "label": "中国澳门"},
            {"value": "TW", "label": "中国台湾"},
            {"value": "US", "label": "美国"},
            {"value": "JP", "label": "日本"},
            {"value": "KR", "label": "韩国"},
            {"value": "SG", "label": "新加坡"},
            {"value": "MY", "label": "马来西亚"},
            {"value": "TH", "label": "泰国"},
            {"value": "GB", "label": "英国"},
            {"value": "FR", "label": "法国"},
            {"value": "DE", "label": "德国"},
            {"value": "CA", "label": "加拿大"},
            {"value": "AU", "label": "澳大利亚"},
            {"value": "OTHER", "label": "其它（请在备注中注明）"},
        ],
    },
    {
        "id": "birthDay",
        "label": "出生日期",
        "type": "date",
        "required": True,
    },
    {
        "id": "certExpiry",
        "label": "证件有效期",
        "type": "date",
        "required": True,
    },
    {
        "id": "phoneNumber",
        "label": "联系电话",
        "type": "text",
        "required": True,
        "placeholder": "如：13800138000",
    },
    {
        "id": "email",
        "label": "邮箱（可选，用于接收行程单）",
        "type": "text",
        "required": False,
        "placeholder": "name@example.com",
    },
]


def _parse_find_passenger_output(output: Any) -> dict[str, Any] | None:
    """Decode the ``tool_result`` of ``/air/customer/findPassenger`` to the
    first ``dataList[0]`` passenger record. Returns None on any error.
    """
    if isinstance(output, dict):
        data = output
    elif isinstance(output, str):
        text = output.strip()
        if (
            text.startswith("...output truncated...")
            or "Full output saved to:" in text[:200]
        ):
            brace_idx = text.find("{")
            if brace_idx < 0:
                return None
            text = text[brace_idx:]
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return None
    else:
        return None
    if str(data.get("errorCode", "0")) != "0":
        return None
    inner = data.get("data") or {}
    items = inner.get("dataList") if isinstance(inner, dict) else None
    if not items or not isinstance(items, list):
        return None
    first = items[0]
    return first if isinstance(first, dict) else None


def _is_field_missing(passenger: dict[str, Any], field_id: str) -> bool:
    """``True`` if the form field should be exposed (not pre-filled)."""
    if field_id == "passengerName":
        return not (passenger.get("passengerName") or passenger.get("certName"))
    if field_id == "passengerNamePinyin":
        return not passenger.get("certNamePinyin")
    if field_id == "certType":
        return not passenger.get("certType")
    if field_id == "certNo":
        return not passenger.get("certNo")
    if field_id == "nationality":
        return not (passenger.get("nationality") or passenger.get("nationalityName"))
    if field_id == "birthDay":
        return not passenger.get("birthDay")
    if field_id == "certExpiry":
        return not passenger.get("expiryDate")
    if field_id == "phoneNumber":
        tel_list = passenger.get("telList") or []
        return not tel_list
    if field_id == "email":
        return not passenger.get("email")
    return True


def _prefill(passenger: dict[str, Any], field_id: str) -> Any:
    if field_id == "passengerName":
        return passenger.get("passengerName") or passenger.get("certName")
    if field_id == "passengerNamePinyin":
        return passenger.get("certNamePinyin")
    if field_id == "certType":
        return _cert_type_to_code(passenger.get("certType"))
    if field_id == "certNo":
        return passenger.get("certNo")
    if field_id == "nationality":
        return passenger.get("nationality")
    if field_id == "birthDay":
        bd = passenger.get("birthDay")
        if bd and "T" in str(bd):
            return str(bd).split("T", 1)[0]
        return bd
    if field_id == "certExpiry":
        ed = passenger.get("expiryDate")
        if ed and "T" in str(ed):
            return str(ed).split("T", 1)[0]
        return ed
    if field_id == "phoneNumber":
        tel_list = passenger.get("telList") or []
        if tel_list and isinstance(tel_list[0], dict):
            return tel_list[0].get("tel")
        return None
    if field_id == "email":
        return passenger.get("email")
    return None


_CERT_CODE_MAP = {
    "身份证": "0",  # 身份证 is not in the international flow, but keep for safety
    "护照": "0",
    "港澳通行证": "1",
    "台胞证": "2",
    "回乡证": "3",
    "台湾通行证": "4",
    "护照/其他": "0",
}


def _cert_type_to_code(cert_type: str | None) -> str:
    if not cert_type:
        return "0"
    return _CERT_CODE_MAP.get(cert_type, cert_type if cert_type in {"0", "1", "2", "3", "4"} else "0")


def maybe_assemble_passenger_form_card(
    output: Any,
    session_id: str = "",
) -> StreamEvent | None:
    """Return a ``StreamEvent.card(PASSENGER_FORM)`` for the first matching
    passenger if at least one REQUIRED field is missing. Otherwise None.

    Optional fields (e.g. email) are not counted as "missing" — they are
    surfaced in the form only if they're already pre-filled (so the user can
    edit/correct) or are explicitly required.
    """
    passenger = _parse_find_passenger_output(output)
    if passenger is None:
        return None

    required_missing = [
        f for f in REQUIRED_FIELDS
        if f.get("required") and _is_field_missing(passenger, f["id"])
    ]
    if not required_missing:
        return None

    fields: list[dict[str, Any]] = []
    for f in REQUIRED_FIELDS:
        # Always include REQUIRED fields that are missing.
        is_required = bool(f.get("required"))
        is_missing = _is_field_missing(passenger, f["id"])
        if is_required and is_missing:
            f_copy = dict(f)
            prefill = _prefill(passenger, f["id"])
            if prefill not in (None, ""):
                f_copy["default"] = prefill
            fields.append(f_copy)
        # Optional fields are shown only if they have a pre-filled value
        # (so the user can edit/correct), not for the sake of asking.

    if not fields:
        return None

    passenger_name = (
        passenger.get("passengerName")
        or passenger.get("certName")
        or "乘机人"
    )
    card_id = f"card-pf-{uuid.uuid4().hex[:8]}"
    return StreamEvent.card(
        card_id=card_id,
        card_type="PASSENGER_FORM",
        card={
            "card_id": card_id,
            "card_type": "PASSENGER_FORM",
            "schema_version": "1.0",
            "title": f"补全乘机人信息 - {passenger_name}",
            "body": {
                "message": "系统已自动匹配乘机人档案，请补充以下信息后继续下单。",
            },
            "fields": fields,
            "options": [],
            "actions": [],
            "decision_buttons": [],
            "metadata": {
                "passengerId": passenger.get("id"),
                "userID": passenger.get("userID"),
                "depId": passenger.get("depId"),
                "userCode": passenger.get("userCode"),
            },
            "dismissible": False,
        },
    )


__all__ = ["maybe_assemble_passenger_form_card", "REQUIRED_FIELDS"]