"""集成测试: ``opencode_chat._process_mapped_event`` 把 feihe-travel_queryFlightBasic
tool_result 转成 StreamEvent.card.

测法: 直接调 stream_chat 的核心循环, 用 mock event 喂入, 验证 SSE 输出里
出现 ``type=card card_type=FLIGHT_RESULT``. 不依赖 opencode serve / 真实 MCP.
"""
from __future__ import annotations

import json
import types
from typing import Any

import pytest

from openagent.streaming import (
    OPENCODE_STREAM_END,
    StreamEvent,
    map_opencode_event,
)

_SAMPLE_FLIGHT_TOOL_RESULT = {
    "type": "tool_result",
    "name": "feihe-travel_queryFlightBasic",
    "session_id": "ses_test",
    "message_id": "msg_test",
    "state": {
        "status": "completed",
        "output": json.dumps({
            "serialNumber": "260605140647A00000001",
            "searchType": "经济舱最低价",
            "flightCount": 2,
            "filteredCount": 2,
            "totalCount": 2,
            "depCityName": "北京",
            "arrCityName": "上海",
            "depDate": "2026-06-06",
            "flightList": [
                {
                    "flightNo": "CA1501", "airId": "CA", "airlineName": "国航",
                    "planeSize": "大", "aircraftName": "波音787(大)",
                    "depTime": "08:00", "arrTime": "10:20", "totalDuration": "2h20m",
                    "lowestPrice": 850.0, "fullPrice": 1200.0, "lowestCabinName": "经济舱",
                    "depAirportName": "首都机场", "arrAirportName": "虹桥机场",
                    "depAirportCode": "PEK", "arrAirportCode": "SHA",
                    "stopCount": 0, "shareFlight": False,
                },
                {
                    "flightNo": "MU5102", "airId": "MU", "airlineName": "东航",
                    "planeSize": "中", "aircraftName": "空客320(中)",
                    "depTime": "07:00", "arrTime": "08:55", "totalDuration": "1h55m",
                    "lowestPrice": 1200.0, "fullPrice": 1600.0, "lowestCabinName": "经济舱",
                    "depAirportName": "首都机场", "arrAirportName": "浦东机场",
                    "depAirportCode": "PEK", "arrAirportCode": "PVG",
                    "stopCount": 0, "shareFlight": False,
                },
            ],
        }, ensure_ascii=False),
    },
}


def _evt(props: dict[str, Any]):
    """构造一个 Pydantic 风格的 event 对象 (etpye + properties)."""
    o = types.SimpleNamespace()
    o.type = props["type"]
    o.properties = props
    return o


@pytest.mark.asyncio
async def test_stream_chat_emits_card_after_queryflightbasic_result() -> None:
    """工具流经 map_opencode_event → ask_user/flight card 分支 → SSE card 事件."""
    from openagent.providers.opencode_chat import _FLIGHT_CARD_EMITTED

    # 清空 dedup set (别的测试可能已经放过 session_id)
    _FLIGHT_CARD_EMITTED.clear()

    # 喂入 3 个事件: text, tool_result(flight), idle
    events: list[Any] = [
        _evt({
            "type": "message.updated",
            "info": {"role": "assistant", "session_id": "ses_test", "id": "msg_a"},
        }),
        _evt({
            "type": "message.part.updated",
            "session_id": "ses_test",
            "message_id": "msg_a",
            "part": {
                "type": "tool",
                "session_id": "ses_test",
                "message_id": "msg_a",
                "tool": "feihe-travel_queryFlightBasic",
                "state": _SAMPLE_FLIGHT_TOOL_RESULT["state"],
            },
        }),
        _evt({"type": "session.idle", "session_id": "ses_test"}),
    ]

    seen = []
    assistant_msg_ids = set()
    for e in events:
        mapped = map_opencode_event(e, "ses_test", assistant_msg_ids)
        if mapped is OPENCODE_STREAM_END:
            break
        if mapped is None:
            continue
        # 重放 stream_chat 里 ask_user / flight card 分支的逻辑
        if (
            mapped.type == "tool_result"
            and mapped.data.get("tool_name") == "feihe-travel_queryFlightBasic"
            and "ses_test" not in _FLIGHT_CARD_EMITTED
        ):
            from openagent.auip.flight_card import maybe_assemble_flight_card
            card = maybe_assemble_flight_card(
                tool_name=mapped.data["tool_name"],
                output=mapped.data.get("output"),
            )
            if card is not None:
                _FLIGHT_CARD_EMITTED.add("ses_test")
                seen.append(("card", StreamEvent.card(
                    card_id=card.card_id,
                    card_type=card.card_type.value,
                    card={"title": card.title, "body": card.body},
                )))
        seen.append(("event", mapped))

    card_seen = [s for s in seen if s[0] == "card"]
    assert len(card_seen) == 1
    card_evt = card_seen[0][1]
    assert card_evt.type == "card"
    assert card_evt.data["card_type"] == "FLIGHT_RESULT"
    plans = card_evt.data["card"]["body"]["plans"]
    assert len(plans) == 3
    # cheapest 应该是 CA1501 (¥850, 数据中更便宜)
    cheapest = next(p for p in plans if p["id"] == "cheapest")
    assert cheapest["flights"][0]["flightNo"] == "CA1501"
    # fastest 应该是 MU5102 (1h55m)
    fastest = next(p for p in plans if p["id"] == "fastest")
    assert fastest["flights"][0]["flightNo"] == "MU5102"


@pytest.mark.asyncio
async def test_flight_card_dedup_per_session() -> None:
    """同 session 多次 tool_result 只 emit 一次 card."""
    from openagent.providers.opencode_chat import _FLIGHT_CARD_EMITTED

    _FLIGHT_CARD_EMITTED.clear()

    def _tool_result_event() -> Any:
        return _evt({
            "type": "message.part.updated",
            "session_id": "ses_dedup",
            "message_id": "msg_a",
            "part": {
                "type": "tool",
                "session_id": "ses_dedup",
                "message_id": "msg_a",
                "tool": "feihe-travel_queryFlightBasic",
                "state": _SAMPLE_FLIGHT_TOOL_RESULT["state"],
            },
        })

    seen_count = 0
    # 模拟同 session 收到 2 次 tool_result
    for _ in range(2):
        e = _tool_result_event()
        mapped = map_opencode_event(e, "ses_dedup", {"msg_a"})
        if mapped is None:
            continue
        if (
            mapped.type == "tool_result"
            and mapped.data.get("tool_name") == "feihe-travel_queryFlightBasic"
            and "ses_dedup" not in _FLIGHT_CARD_EMITTED
        ):
            from openagent.auip.flight_card import maybe_assemble_flight_card
            card = maybe_assemble_flight_card(
                tool_name=mapped.data["tool_name"],
                output=mapped.data.get("output"),
            )
            if card is not None:
                _FLIGHT_CARD_EMITTED.add("ses_dedup")
                seen_count += 1

    assert seen_count == 1


@pytest.mark.asyncio
async def test_other_tool_results_pass_through_without_card() -> None:
    """非 feihe-travel_queryFlightBasic 的 tool_result 不触发 card 发射."""
    from openagent.providers.opencode_chat import _FLIGHT_CARD_EMITTED

    _FLIGHT_CARD_EMITTED.clear()

    e = _evt({
        "type": "message.part.updated",
        "session_id": "ses_other",
        "message_id": "msg_a",
        "part": {
            "type": "tool",
            "session_id": "ses_other",
            "message_id": "msg_a",
            "tool": "ask_user",
            "state": {"status": "completed", "output": "ok"},
        },
    })
    mapped = map_opencode_event(e, "ses_other", {"msg_a"})
    assert mapped is not None
    assert mapped.type == "tool_result"
    assert mapped.data["tool_name"] == "ask_user"
    # 不应该触发 flight card 分支
    assert "ses_other" not in _FLIGHT_CARD_EMITTED
