"""tests/test_auip_renderer_protocol.py — 验证 CardRenderer / MessageRewriter 协议 + Registry.

基座 ``hermetic_agent.auip.renderer`` / ``hermetic_agent.auip.rewriter`` 是 Phase 1
新增的协议, 业务 SKILL 通过它们注册. 协议行为要稳定.
"""
from __future__ import annotations

from typing import Any

from hermetic_agent.auip.cards import Card, CardType
from hermetic_agent.auip.events import TurnEvent, TurnEventType
from hermetic_agent.auip.renderer import (
    CardRendererRegistry,
    get_renderer_registry,
    reset_renderer_registry,
)
from hermetic_agent.auip.rewriter import (
    MessageRewriterRegistry,
    get_rewriter_registry,
    reset_rewriter_registry,
)
from hermetic_agent.providers.streaming import StreamEvent


# ---- Test helpers ----------------------------------------------------------


class _CountingRenderer:
    def __init__(self, tool_set: set[str], body_value: str = "rendered") -> None:
        self._tools = tool_set
        self._body = body_value
        self.render_count = 0

    def tool_names(self) -> set[str]:
        return self._tools

    def can_render(self, event: TurnEvent, context: dict[str, Any]) -> bool:
        return event.data.get("tool_name") in self._tools

    def render(self, event: TurnEvent, context: dict[str, Any]) -> Card | None:
        self.render_count += 1
        return Card(card_type=CardType.CHAT_FALLBACK, title="x", body={"value": self._body})


class _WildcardRenderer:
    def tool_names(self) -> set[str]:
        return set()  # wildcard

    def can_render(self, event: TurnEvent, context: dict[str, Any]) -> bool:
        return event.data.get("tool_name") == "wildcard_tool"

    def render(self, event: TurnEvent, context: dict[str, Any]) -> Card | None:
        return Card(card_type=CardType.CHAT_FALLBACK, title="wildcard", body={})


# ---- CardRenderer ----------------------------------------------------------


def test_card_registry_routes_by_tool_name() -> None:
    reset_renderer_registry()
    reg = get_renderer_registry()
    r = _CountingRenderer({"my_tool"})
    reg.register(r)
    event = TurnEvent(seq=0, turn_id="t1", type=TurnEventType.TOOL_RESULT,
                      data={"tool_name": "my_tool", "output": {"foo": 1}})
    card = reg.render(event, {})
    assert card is not None
    assert card.body == {"value": "rendered"}
    assert r.render_count == 1


def test_card_registry_no_match_returns_none() -> None:
    reset_renderer_registry()
    reg = get_renderer_registry()
    r = _CountingRenderer({"my_tool"})
    reg.register(r)
    event = TurnEvent(seq=0, turn_id="t1", type=TurnEventType.TOOL_RESULT,
                      data={"tool_name": "unknown_tool", "output": {}})
    card = reg.render(event, {})
    assert card is None
    assert r.render_count == 0


def test_card_registry_wildcard_fallback() -> None:
    reset_renderer_registry()
    reg = get_renderer_registry()
    reg.register(_WildcardRenderer())
    event = TurnEvent(seq=0, turn_id="t1", type=TurnEventType.TOOL_RESULT,
                      data={"tool_name": "wildcard_tool", "output": {}})
    card = reg.render(event, {})
    assert card is not None
    assert card.title == "wildcard"


def test_card_registry_replace_default() -> None:
    reset_renderer_registry()
    reg = get_renderer_registry()
    reg.register(_CountingRenderer({"x"}, body_value="first"))
    reg.register(_CountingRenderer({"x"}, body_value="second"))  # replace default
    event = TurnEvent(seq=0, turn_id="t1", type=TurnEventType.TOOL_RESULT,
                      data={"tool_name": "x", "output": {}})
    card = reg.render(event, {})
    assert card is not None
    assert card.body == {"value": "second"}


def test_card_registry_replace_false_raises() -> None:
    reset_renderer_registry()
    reg = get_renderer_registry()
    reg.register(_CountingRenderer({"x"}))
    try:
        reg.register(_CountingRenderer({"x"}), replace=False)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError on duplicate registration")


# ---- MessageRewriter -------------------------------------------------------


class _ConfirmRewriter:
    def tool_names(self) -> set[str]:
        return {"ask_user"}

    def rewrite(self, event: StreamEvent, context: dict[str, Any]) -> StreamEvent | None:
        if event.data.get("action_id") == "confirm":
            return StreamEvent.text(content="已确认")
        return None


def test_rewriter_registry_routes() -> None:
    reset_rewriter_registry()
    reg = get_rewriter_registry()
    reg.register(_ConfirmRewriter())
    event = StreamEvent(
        type="user_message",
        data={"tool_name": "ask_user", "action_id": "confirm"},
    )
    out = reg.rewrite(event, {})
    assert out is not None
    assert out.data.get("content") == "已确认"


def test_rewriter_registry_no_match_returns_none() -> None:
    reset_rewriter_registry()
    reg = get_rewriter_registry()
    reg.register(_ConfirmRewriter())
    event = StreamEvent(
        type="user_message",
        data={"tool_name": "ask_user", "action_id": "unknown"},
    )
    out = reg.rewrite(event, {})
    assert out is None
