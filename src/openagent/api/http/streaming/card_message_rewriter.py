"""api/http/streaming/card_message_rewriter.py — 卡片提交消息重写。

前端卡片点击后发送的 message 格式为：
    用户已提交 FLIGHT_RESULT 卡片：{"card_type":"FLIGHT_RESULT",...,"user_input":{...}}

这种 JSON 文本直接发给 LLM 会：
1. 浪费 token（大段 JSON）
2. LLM 可能误解或重复输出 JSON
3. 无法正确触发状态流转

本模块拦截这类消息，提取关键信息，重写为自然语言，让 LLM 能正确理解用户意图。
同时提取需要自动生成的卡片（如舱位选择），供 controller 在 LLM 响应前发送。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

CARD_SUBMIT_PATTERN = re.compile(
    r"^用户已提交\s+(\w+)\s+卡片[：:]\s*(\{.+\})$",
    re.DOTALL,
)


@dataclass
class RewriteResult:
    """卡片消息重写结果。"""
    message: str
    auto_cards: list[dict[str, Any]] = field(default_factory=list)


def rewrite_card_message(message: str) -> RewriteResult:
    """检测并重写卡片提交消息为自然语言。

    Args:
        message: 原始用户消息文本。

    Returns:
        RewriteResult 包含重写后的消息和需要自动发送的卡片列表。
    """
    match = CARD_SUBMIT_PATTERN.match(message)
    if not match:
        return RewriteResult(message=message)

    card_type = match.group(1)
    json_str = match.group(2)

    try:
        payload = json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        logger.warning("card_message_parse_failed", card_type=card_type)
        return RewriteResult(message=message)

    user_input = payload.get("user_input") or {}
    action_id = payload.get("action_id", "")

    if card_type == "FLIGHT_RESULT" and action_id == "select_flight":
        return _format_flight_selection(user_input)

    if card_type == "CABIN_LIST" and action_id == "select_cabin":
        msg = _format_cabin_selection(user_input)
        return RewriteResult(message=msg)

    if card_type == "ORDER_CONFIRM" and action_id == "GO_PAY":
        return RewriteResult(message="确认订单，准备支付")

    msg = _format_generic_selection(card_type, user_input, action_id)
    return RewriteResult(message=msg)


def _format_flight_selection(user_input: dict[str, Any]) -> RewriteResult:
    flight = user_input.get("selectedFlight") or {}
    if not isinstance(flight, dict):
        flight = {}

    dep_city = flight.get("depCityName", "")
    arr_city = flight.get("arrCityName", "")
    dep_date = flight.get("depDate", "")
    dep_time = flight.get("depTime", "")
    airline = flight.get("airlineName", "")
    flight_no = flight.get("flightNo", "")
    price = flight.get("lowestPrice") or flight.get("totalPrice") or 0
    group_id = flight.get("groupId", "")
    price_id = flight.get("priceId", "")
    price_options = flight.get("priceOptions") or []

    if dep_date:
        date_match = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(dep_date))
        if date_match:
            dep_date = f"{date_match.group(2)}月{date_match.group(3)}日"

    parts = ["我选择航班："]
    if dep_date:
        parts.append(f"{dep_date}")
    if dep_city and arr_city:
        parts.append(f"从{dep_city}到{arr_city}")
    if airline:
        parts.append(airline)
    if flight_no:
        parts.append(flight_no)
    if dep_time:
        parts.append(f"{dep_time}出发")
    if price:
        parts.append(f"¥{int(price)}")

    result = " ".join(parts)

    if group_id or price_id:
        meta_parts = []
        if group_id:
            meta_parts.append(f"groupId={group_id}")
        if price_id:
            meta_parts.append(f"priceId={price_id}")
        result += f"\n[选择参数: {', '.join(meta_parts)}]"

    auto_cards: list[dict[str, Any]] = []
    if isinstance(price_options, list) and price_options:
        options_lines = ["\n可选舱位/价格方案："]
        for i, opt in enumerate(price_options[:5]):
            if not isinstance(opt, dict):
                continue
            cab = opt.get("cabClass", "经济舱")
            total = opt.get("totalPrice", 0)
            refund = "可退" if opt.get("refund") else "不可退"
            change = "可改" if opt.get("change") else "不可改"
            pid = opt.get("priceId", "")
            options_lines.append(
                f"  {i+1}. {cab} ¥{int(total)} ({refund}/{change}) priceId={pid}"
            )
        result += "\n".join(options_lines)
        result += "\n请帮我选择方案并继续下一步。"
        cabin_card = _build_cabin_selection_card(
            dep_city=dep_city,
            arr_city=arr_city,
            flight_no=flight_no,
            price_options=price_options,
        )
        if cabin_card:
            auto_cards.append(cabin_card)

    return RewriteResult(message=result, auto_cards=auto_cards)


def _build_cabin_selection_card(
    dep_city: str,
    arr_city: str,
    flight_no: str,
    price_options: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """从 priceOptions 构建舱位选择卡片。"""
    if not price_options:
        return None

    lines = [f"已选航班 {flight_no}（{dep_city}→{arr_city}），请选择舱位方案：\n"]
    for i, opt in enumerate(price_options[:5]):
        if not isinstance(opt, dict):
            continue
        cab = opt.get("cabClass", "经济舱")
        total = opt.get("totalPrice", 0)
        refund = "可退" if opt.get("refund") else "不可退"
        change = "可改" if opt.get("change") else "不可改"
        lines.append(f"{i+1}. {cab} ¥{int(total)}（{refund}/{change}）")

    content_text = "\n".join(lines)

    import uuid
    card_id = f"card-{uuid.uuid4().hex[:8]}"
    return {
        "card_id": card_id,
        "card_type": "FLIGHT_RESULT",
        "schema_version": "1.0",
        "title": f"舱位选择 - {flight_no}",
        "body": {
            "contentJson": {
                "schemaVersion": "2",
                "dataList": [
                    {
                        "basicType": "PLAIN_TEXT",
                        "dataStr": content_text,
                        "dataJson": None,
                        "linkUrl": "",
                    }
                ],
            }
        },
        "fields": [],
        "options": [],
        "actions": [],
        "decision_buttons": [],
        "metadata": {},
        "dismissible": False,
    }


def _format_cabin_selection(user_input: dict[str, Any]) -> str:
    cabin = user_input.get("selectedCabin") or {}
    if not isinstance(cabin, dict):
        cabin = {}

    cabin_name = cabin.get("cabinName") or cabin.get("cab") or "舱位"
    price = cabin.get("totalPrice") or cabin.get("price") or 0

    parts = [f"选择{cabin_name}"]
    if price:
        parts.append(f"¥{int(price)}")

    return " ".join(parts)


def _format_generic_selection(
    card_type: str,
    user_input: dict[str, Any],
    action_id: str,
) -> str:
    if not user_input:
        return f"用户提交了{card_type}卡片"

    items = []
    for key, value in user_input.items():
        if key.startswith("_"):
            continue
        if isinstance(value, dict):
            continue
        if isinstance(value, list):
            value = "、".join(str(v) for v in value if not isinstance(v, dict))
        items.append(f"{key}={value}")

    if items:
        return f"用户选择了：{', '.join(items)}"
    return f"用户提交了{card_type}卡片"


__all__ = ["rewrite_card_message", "RewriteResult"]
