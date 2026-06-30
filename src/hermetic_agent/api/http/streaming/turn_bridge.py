"""api/streaming/turn_bridge.py — auip.TurnEvent 翻译为 streaming.StreamEvent.

chat_controller (HITL 流) 与 turn_routes (/agent/turn/.../resume) 都需要
把 HITL 状态机产出的 ``TurnEvent`` 序列翻译为 SSE 协议, 避免在两处
重复实现映射表. 集中放这里.
"""
from __future__ import annotations

from hermetic_agent.auip import TurnEvent, TurnEventType
from hermetic_agent.providers.streaming import StreamEvent


def turn_event_to_sse(turn_evt: TurnEvent) -> StreamEvent:
    """把 auip.TurnEvent 翻译为 streaming.StreamEvent (复用现有 SSE 协议).

    Args:
        turn_evt: HITL 状态机产出的事件.

    Returns:
        对应的 ``StreamEvent`` (与 chat_controller / turn_routes 的 SSE
        协议对齐). 未知事件类型 fallback 为 ``StreamEvent.text(str(data))``.
    """
    t = turn_evt.type
    d = turn_evt.data or {}

    if t == TurnEventType.SESSION:
        return StreamEvent.session(session_id=d.get("session_id", ""))
    if t == TurnEventType.TEXT:
        return StreamEvent.text(content=d.get("text") or d.get("content", ""))
    if t == TurnEventType.REASONING:
        return StreamEvent.reasoning(content=d.get("content", ""))
    if t == TurnEventType.TOOL_USE:
        return StreamEvent.tool_use(
            tool_name=d.get("name", "unknown"),
            input_data=d.get("input", {}),
            id=d.get("id", ""),
        )
    if t == TurnEventType.TOOL_RESULT:
        return StreamEvent.tool_result(
            tool_name=d.get("name", "unknown"),
            output=d.get("output", ""),
            id=d.get("id", ""),
            is_error=d.get("is_error", False),
        )
    if t == TurnEventType.CARD:
        card = d.get("card", {})
        return StreamEvent.card(
            card_id=d.get("card_id", ""),
            card_type=card.get("card_type", "UNKNOWN"),
            card=card,
            correlation_id=d.get("correlation_id", ""),
        )
    if t == TurnEventType.STATE:
        return StreamEvent.state(state=d.get("state", ""), note=d.get("note", ""))
    if t == TurnEventType.SUSPEND:
        return StreamEvent.suspend(
            checkpoint_id=d.get("checkpoint_id", ""),
            card=d.get("card", {}),
            correlation_id=d.get("correlation_id", ""),
            input_schema=d.get("input_schema", {}),
            turn_id=turn_evt.turn_id,
        )
    if t == TurnEventType.RESUME:
        return StreamEvent.resume(checkpoint_id=d.get("checkpoint_id", ""))
    if t == TurnEventType.DONE:
        return StreamEvent.done(stop_reason=d.get("stop_reason", "end_turn"))
    if t == TurnEventType.ERROR:
        return StreamEvent.error(message=d.get("message", "unknown"), code=d.get("code", ""))

    # Fallback: 未知事件类型, 用 text 透传
    return StreamEvent(text=str(d))
