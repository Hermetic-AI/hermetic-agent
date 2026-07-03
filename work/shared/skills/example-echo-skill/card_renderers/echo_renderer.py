"""Echo CardRenderer — 把 echo 工具的 tool_result 转成 ECHO_RESULT 卡片.

基座 CardRenderer 协议 (hermetic_agent.auip.renderer) 的标准实现.
业务 SKILL 应当按此模板写自己的 Renderer: 实现 tool_names() / can_render() /
render() 三个方法, 然后在 ``__init__.py`` 的 ``register_renderers()`` 注册.

新 SKILL 自注册模式 (Phase 4 引入):
  ECHO_RESULT 是业务 CardType, 在 ``__init__.py`` 通过 ``register_card_type()``
  注册到基座白名单. 此处用字符串字面量引用, 不再走基座 ``CardType`` 枚举.
"""
from __future__ import annotations

import uuid
from typing import Any

from hermetic_agent.auip._safe_extract import first_text
from hermetic_agent.auip.cards import Card
from hermetic_agent.auip.events import TurnEvent
from hermetic_agent.auip.renderer import CardRenderer

ECHO_RESULT_CARD_TYPE = "ECHO_RESULT"
"""本 SKILL 注册的 CardType 字符串 (在 __init__.py 完成 register_card_type)."""


class EchoCardRenderer:
    """基座 CardRenderer 协议的标准实现 — 业务模板."""

    def tool_names(self) -> set[str]:
        return {"echo", "mcp.echo_echo", "mcp.echo__echo"}

    def can_render(self, event: TurnEvent, context: dict[str, Any]) -> bool:
        data = event.data or {}
        if data.get("tool_name") not in self.tool_names():
            return False
        output = data.get("output")
        return isinstance(output, (str, dict))

    def render(self, event: TurnEvent, context: dict[str, Any]) -> Card | None:
        data = event.data or {}
        output = data.get("output")
        echoed: str = ""
        if isinstance(output, str):
            echoed = output.strip()
        elif isinstance(output, dict):
            echoed = first_text(
                output.get("echoed"),
                output.get("text"),
                output.get("result"),
            )
        if not echoed:
            return None
        return Card(
            card_id=f"card-echo-{uuid.uuid4().hex[:8]}",
            card_type=ECHO_RESULT_CARD_TYPE,
            title="Echo Result",
            body={
                "echoed": echoed,
                "length": len(echoed),
                "summary": f"已 echo: {echoed[:60]}{'...' if len(echoed) > 60 else ''}",
            },
            actions=[
                {"id": "confirm", "label": "确认"},
                {"id": "cancel", "label": "取消"},
            ],
            metadata={"skill": "example-echo-skill"},
        )


__all__ = ["ECHO_RESULT_CARD_TYPE", "EchoCardRenderer"]
