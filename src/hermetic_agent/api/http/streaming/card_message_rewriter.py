"""api/http/streaming/card_message_rewriter.py — 卡片提交消息重写.

前端卡片点击后发送的 message 格式为::

    用户已提交 <CARD_TYPE> 卡片：{"card_type":"...", "user_input":{...}, ...}

直接发给 LLM 会浪费 token + LLM 误解读 + 无法触发状态流转. 本模块
拦截这类消息, 提取关键信息重写为自然语言.

业务 CardRenderer / MessageRewriter 通过
``CardRendererRegistry`` / ``MessageRewriterRegistry`` 注册, 基座只做
协议级解析 + 路由. 详见 ``docs/core-skill-boundary.md`` §4.3 / §4.4.
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
    """卡片消息重写结果.

    Attributes:
        message: 重写后的消息文本 (若未改写, 等于原文).
        auto_cards: 路由过程中**额外**插入的卡片 (例如选了航班后自动弹出
            舱位选择卡). 由 caller 决定是否 emit.
    """

    message: str
    auto_cards: list[dict[str, Any]] = field(default_factory=list)


def rewrite_card_message(message: str) -> RewriteResult:
    """检测并重写卡片提交消息为自然语言.

    协议级解析 + 业务路由:
      1. ``CARD_SUBMIT_PATTERN`` 匹配 → 提取 ``card_type`` / ``user_input`` / ``action_id``
      2. 委托 ``MessageRewriterRegistry.rewrite()`` 给业务 SKILL 的 Rewriter
      3. 兜底: 业务 SKILL 未注册或未处理 → 透传原文

    Args:
        message: 原始用户消息文本.

    Returns:
        RewriteResult 包含重写后的消息和需要自动发送的卡片列表.
    """
    from hermetic_agent.auip.rewriter import get_rewriter_registry

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

    from hermetic_agent.providers.streaming import StreamEvent

    event = StreamEvent(
        type="user_message",
        data={
            "card_type": card_type,
            "action_id": action_id,
            "user_input": user_input,
            "raw_payload": payload,
        },
    )
    rewritten = get_rewriter_registry().rewrite(event, context={})
    if rewritten is not None:
        return RewriteResult(
            message=rewritten.data.get("content", message),
            auto_cards=rewritten.data.get("auto_cards") or [],
        )

    if action_id:
        return RewriteResult(
            message=f"用户已选择 {card_type} 卡片的 {action_id} 操作."
        )
    return RewriteResult(message=message)
