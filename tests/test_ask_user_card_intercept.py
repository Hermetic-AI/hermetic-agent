"""tests/test_ask_user_card_intercept.py — single-mode AUIP ask_user→card flow.

P6/F2 改造后, ``chat_stream`` 在 single 模式下也会拦截 LLM 调
``ask_user`` 合成工具, 转成 ``card`` SSE 事件. 本测试覆盖:

1. ``_ask_user_to_card`` 转换 tool_use(ask_user) → card
2. ``_ask_user_to_card`` 校验 card_type 在白名单内
3. ``_ask_user_to_card`` 校验 card_type 在 CARD_TYPES_SET 内
4. ``_stream_with_ask_user_intercept`` 抑制 ask_user 的 tool_result
5. End-to-end: 模拟 bridge 迭代器, 走完整拦截流程
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

import pytest

from openagent.api.controllers.chat_controller import (
    _ask_user_to_card,
    _stream_with_ask_user_intercept,
)
from openagent.streaming import StreamEvent


# ---------------------------------------------------------------------------
# _ask_user_to_card 直接测试
# ---------------------------------------------------------------------------


def test_ask_user_to_card_passes_through_non_ask_user_events() -> None:
    """非 ask_user 的 tool_use 应原样返回."""
    event = StreamEvent.tool_use(tool_name="bash", input_data={"command": "ls"})
    out = _ask_user_to_card(event, allowed_card_types=None)
    assert out.type == "tool_use"
    assert out.data.get("tool_name") == "bash"


def test_ask_user_to_card_passes_through_text_event() -> None:
    """text 事件应原样返回."""
    event = StreamEvent.text(content="hello")
    out = _ask_user_to_card(event, allowed_card_types=None)
    assert out.type == "text"
    assert out.data.get("content") == "hello"


def test_ask_user_to_card_converts_flight_result() -> None:
    """ask_user(card_type=FLIGHT_RESULT) → card 事件."""
    event = StreamEvent.tool_use(
        tool_name="ask_user",
        input_data={
            "card_type": "FLIGHT_RESULT",
            "title": "机票已发送",
            "body": {
                "summary": {
                    "totalCount": 50,
                    "filteredCount": 10,
                    "searchType": "全量查询",
                    "depCity": "北京",
                    "arrCity": "上海",
                    "depDate": "2026-06-06",
                },
                "plans": [
                    {
                        "id": "fastest",
                        "title": "最快抵达",
                        "flights": [
                            {
                                "flightId": "CA1501-20260606-0900",
                                "flightNo": "CA1501",
                                "price": 550,
                            }
                        ],
                    }
                ],
            },
        },
    )
    out = _ask_user_to_card(event, allowed_card_types=None)
    assert out.type == "card"
    assert out.data["card_type"] == "FLIGHT_RESULT"
    # StreamEvent.card 把 card 主体放在 data['card'] 里
    assert out.data["card"]["title"] == "机票已发送"
    body = out.data["card"]["body"]
    assert body["summary"]["totalCount"] == 50
    assert body["plans"][0]["flights"][0]["flightNo"] == "CA1501"
    assert out.data["card_id"].startswith("card-")
    # 兼容: tool_use 用 'name' 而 backend 也可能用 'tool_name'
    assert "ask_user" not in out.data.get("tool_name", "")


def test_ask_user_to_card_rejects_unknown_card_type() -> None:
    """未知 card_type 应返回 error 事件 (CARD_TYPE_INVALID)."""
    event = StreamEvent.tool_use(
        tool_name="ask_user",
        input_data={"card_type": "FAKE_CARD_TYPE_NOT_IN_ENUM", "title": "x"},
    )
    out = _ask_user_to_card(event, allowed_card_types=None)
    assert out.type == "error"
    assert out.data.get("code") == "CARD_TYPE_INVALID"
    assert "FAKE_CARD_TYPE_NOT_IN_ENUM" in out.data.get("message", "")


def test_ask_user_to_card_enforces_scenario_whitelist() -> None:
    """scenario.a2ui.card_schemas 白名单外的 card_type 应返回 CARD_TYPE_NOT_ALLOWED."""
    event = StreamEvent.tool_use(
        tool_name="ask_user",
        input_data={"card_type": "FLIGHT_LIST", "title": "x"},
    )
    # 允许 FLIGHT_LIST
    out = _ask_user_to_card(event, allowed_card_types={"FLIGHT_LIST"})
    assert out.type == "card"
    # 拒绝 FLIGHT_RESULT
    event2 = StreamEvent.tool_use(
        tool_name="ask_user",
        input_data={"card_type": "FLIGHT_RESULT", "title": "x"},
    )
    out2 = _ask_user_to_card(event2, allowed_card_types={"FLIGHT_LIST"})
    assert out2.type == "error"
    assert out2.data.get("code") == "CARD_TYPE_NOT_ALLOWED"


def test_ask_user_to_card_uses_input_name_field() -> None:
    """OpenCode 的 tool_use event 用 'name' 字段, 框架要识别."""
    event = StreamEvent(
        type="tool_use",
        data={
            "name": "ask_user",  # 不是 tool_name
            "input": {
                "card_type": "CHAT_FALLBACK",
                "title": "请补充信息",
            },
        },
    )
    out = _ask_user_to_card(event, allowed_card_types=None)
    assert out.type == "card"
    assert out.data["card_type"] == "CHAT_FALLBACK"


def test_ask_user_to_card_accepts_prefixed_mcp_tool_name() -> None:
    """OpenCode MCP may expose local ask_user as ask_user_ask_user."""
    event = StreamEvent.tool_use(
        tool_name="ask_user_ask_user",
        input_data={
            "card_type": "OD_INPUT",
            "title": "查询国内机票",
            "fields": [{"label": "出发日期", "type": "date", "key": "departureDate"}],
        },
    )
    out = _ask_user_to_card(event, allowed_card_types=None)
    assert out.type == "card"
    assert out.data["card_type"] == "OD_INPUT"
    assert out.data["card"]["fields"][0]["key"] == "departureDate"


def test_ask_user_to_card_default_to_chat_fallback() -> None:
    """没传 card_type 时默认 CHAT_FALLBACK."""
    event = StreamEvent.tool_use(
        tool_name="ask_user",
        input_data={"title": "请补充"},
    )
    out = _ask_user_to_card(event, allowed_card_types=None)
    assert out.type == "card"
    assert out.data["card_type"] == "CHAT_FALLBACK"


# ---------------------------------------------------------------------------
# _stream_with_ask_user_intercept 集成测试
# ---------------------------------------------------------------------------


async def _aiter(events: list[StreamEvent]) -> AsyncIterator[StreamEvent]:
    for e in events:
        yield e


def test_intercept_stream_emits_card_and_suppresses_tool_result() -> None:
    """完整流程: text + tool_use(ask_user) + tool_result(ask_user) → text + card."""
    events = [
        StreamEvent.text(content="thinking..."),
        StreamEvent.tool_use(
            tool_name="ask_user",
            input_data={"card_type": "FLIGHT_RESULT", "title": "机票已发送", "body": {"plans": []}},
        ),
        StreamEvent.tool_result(tool_name="ask_user", output={"ack": True}),
        StreamEvent.text(content="done"),
    ]

    async def main() -> list[StreamEvent]:
        out = []
        async for evt in _stream_with_ask_user_intercept(_aiter(events), allowed_card_types=None):
            out.append(evt)
        return out

    result = asyncio.run(main())
    types = [e.type for e in result]
    assert types == ["text", "card", "text"], f"unexpected: {types}"
    # tool_result 已被抑制
    assert "tool_result" not in types
    # card 事件是 FLIGHT_RESULT
    assert result[1].data["card_type"] == "FLIGHT_RESULT"


def test_intercept_stream_passes_through_normal_tool_results() -> None:
    """非 ask_user 的 tool_result 不应被抑制."""
    events = [
        StreamEvent.tool_use(tool_name="bash", input_data={"command": "ls"}),
        StreamEvent.tool_result(tool_name="bash", output="file.txt"),
        StreamEvent.text(content="ok"),
    ]

    async def main() -> list[StreamEvent]:
        out = []
        async for evt in _stream_with_ask_user_intercept(_aiter(events), allowed_card_types=None):
            out.append(evt)
        return out

    result = asyncio.run(main())
    types = [e.type for e in result]
    assert types == ["tool_use", "tool_result", "text"]


def test_intercept_stream_handles_multiple_ask_user_calls() -> None:
    """连续两次 ask_user 都被转成 card, 两次 tool_result 都被抑制."""
    events = [
        StreamEvent.tool_use(
            tool_name="ask_user",
            input_data={"card_type": "FLIGHT_RESULT", "title": "A"},
        ),
        StreamEvent.tool_result(tool_name="ask_user", output={}),
        StreamEvent.tool_use(
            tool_name="ask_user",
            input_data={"card_type": "CANNOT_ORDER", "title": "B"},
        ),
        StreamEvent.tool_result(tool_name="ask_user", output={}),
    ]

    async def main() -> list[StreamEvent]:
        out = []
        async for evt in _stream_with_ask_user_intercept(_aiter(events), allowed_card_types=None):
            out.append(evt)
        return out

    result = asyncio.run(main())
    types = [e.type for e in result]
    assert types == ["card", "card"], f"unexpected: {types}"
    assert result[0].data["card_type"] == "FLIGHT_RESULT"
    assert result[1].data["card_type"] == "CANNOT_ORDER"


def test_intercept_stream_emits_error_for_invalid_card_type() -> None:
    """未授权的 card_type 走 error 事件 (不挂起, 不出 card)."""
    events = [
        StreamEvent.tool_use(
            tool_name="ask_user",
            input_data={"card_type": "FAKE_TYPE"},
        ),
        StreamEvent.text(content="after"),
    ]

    async def main() -> list[StreamEvent]:
        out = []
        async for evt in _stream_with_ask_user_intercept(
            _aiter(events), allowed_card_types=None,
        ):
            out.append(evt)
        return out

    result = asyncio.run(main())
    types = [e.type for e in result]
    assert types == ["error", "text"]
    assert result[0].data.get("code") == "CARD_TYPE_INVALID"
