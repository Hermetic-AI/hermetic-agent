"""api/streaming/ask_user.py — AUIP ask_user 合成工具 → card 拦截器.

LLM 调 ``ask_user`` 合成工具时, 框架需要把 ``tool_use(ask_user)`` 转成
``card`` SSE 事件发前端, 同时抑制对应的 ``tool_result`` (LLM 不需要看
自己工具的 "ack" 输出, card 本身就是 ack).

支持 card_type 白名单校验:
- 不在 ``CARD_TYPES_SET`` 里的 → 转 error 事件
- 不在 scenario ``allowed_card_types`` 里的 → 转 error 事件
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from hermetic_agent.auip.cards import CARD_TYPES_SET
from hermetic_agent.providers.streaming import StreamEvent

# ask_user 工具名. 框架会在 MCPRegistry 里注册这个名字的合成工具.
# 注意: OpenCode 实际生成的 tool 名是 "ask_user"; 历史出现过 "ask_user_ask_user"
# (因为 tool_call 时 LLM 会重复拼前缀), 两种都接受.
ASK_USER_TOOL_NAMES = {"ask_user", "ask_user_ask_user"}


def is_ask_user_tool(tool_name: Any) -> bool:
    """判断工具名是否属于 ask_user 合成工具 (兼容带前缀变体)."""
    return str(tool_name or "") in ASK_USER_TOOL_NAMES


def _enrich_empty_flight_result_body(
    card_type: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    """业务 body 增强 (例如空 body 兜底) 由 SKILL 通过 CardRendererRegistry 注入.

    基座不做任何业务 body 增强. 保留空函数仅做协议级 passthrough.
    """
    return body


def _ask_user_to_card(
    event: StreamEvent,
    *,
    allowed_card_types: set | None,
) -> StreamEvent:
    """把 tool_use(ask_user) 转成 card 事件. 其它事件原样返回.

    Args:
        event: 来自 bridge 的 StreamEvent.
        allowed_card_types: scenario.a2ui.card_schemas 白名单; None 表示
            不校验 (CARD_TYPES_SET 全部允许).

    Returns:
        转换后的 card 事件; 非 ask_user 事件原样返回, 非法 card_type 返回 error.
    """
    if event.type != "tool_use":
        return event
    data = event.data or {}
    tool_name = data.get("name") or data.get("tool_name")
    if not is_ask_user_tool(tool_name):
        return event

    inp = data.get("input") or {}
    card_type = str(inp.get("card_type") or "CHAT_FALLBACK")
    if card_type not in CARD_TYPES_SET:
        return StreamEvent.error(
            message=(
                f"LLM called ask_user with unknown card_type: {card_type!r}. "
                f"Valid: {sorted(CARD_TYPES_SET)}"
            ),
            code="CARD_TYPE_INVALID",
        )
    if allowed_card_types is not None and card_type not in allowed_card_types:
        return StreamEvent.error(
            message=(
                f"Current scenario does not allow card_type={card_type!r}; "
                f"whitelist: {sorted(allowed_card_types)}"
            ),
            code="CARD_TYPE_NOT_ALLOWED",
        )

    correlation_id = str(data.get("id") or inp.get("correlation_id") or "")
    card_id = str(inp.get("card_id") or f"card-{uuid4().hex[:8]}")
    body = inp.get("body")
    if body is None:
        body = {k: v for k, v in inp.items() if k not in {"card_type", "title"}}
    if not isinstance(body, dict):
        body = {}
    card_payload: dict = {
        "card_id": card_id,
        "card_type": card_type,
        "schema_version": str(inp.get("schema_version") or "1.0"),
        "title": str(inp.get("title") or ""),
        "body": body,
        "fields": inp.get("fields") or [],
        "options": inp.get("options") or [],
        "actions": inp.get("actions") or inp.get("decision_buttons") or [],
        "decision_buttons": inp.get("decision_buttons") or [],
        "metadata": inp.get("metadata") or {},
        "dismissible": bool(inp.get("dismissible", False)),
    }
    return StreamEvent.card(
        card_id=card_id,
        card_type=card_type,
        card=card_payload,
        correlation_id=correlation_id,
    )


async def stream_with_ask_user_intercept(
    iterator: AsyncIterator[StreamEvent],
    *,
    allowed_card_types: set | None,
) -> AsyncIterator[StreamEvent]:
    """Wrap bridge event iterator: convert ask_user tool_use to card, suppress tool_result.

    Yields:
        Transformed events. Suppresses ``tool_result(name=ask_user)`` —
        LLM does not need to see its own tool result because the card
        itself is the ack.
    """
    last_ask_user_id: str | None = None
    async for event in iterator:
        if event.type == "tool_use":
            data = event.data or {}
            tool_name = data.get("name") or data.get("tool_name")
            if is_ask_user_tool(tool_name):
                last_ask_user_id = str(data.get("id") or "")
                yield _ask_user_to_card(
                    event,
                    allowed_card_types=allowed_card_types,
                )
                continue
        if event.type == "tool_result" and last_ask_user_id is not None:
            data = event.data or {}
            tool_name = data.get("name") or data.get("tool_name")
            tool_id = str(data.get("id") or "")
            if is_ask_user_tool(tool_name) and (
                not last_ask_user_id or tool_id == last_ask_user_id
            ):
                last_ask_user_id = None
                continue
        yield event
