"""auip/stream_interceptor.py — 基座 L3 层: 工具结果 → 卡片渲染拦截.

Phase 2 重构: 修复 L4→L3 import 违规.

老方案在 ``providers/opencode/chat.py`` (L4) 直接 import
``auip.events.TurnEvent`` (L3) + ``auip.renderer.get_renderer_registry`` (L3),
违反 5 层依赖规则 (L4 只能 import L5).

新方案: 本模块 (L3) 提供 ``stream_intercept_card_renderers()``, 在 L1/L2
拿到 L4 的原始 StreamEvent 流之后, 对本模块做一次 post-processing:
  - ``tool_result`` 事件 → 调 CardRendererRegistry → 产 Card 事件
  - 其他事件透传

调用方 (chat_controller, L1) 在 bridge.chat() 返回的 async iterator 外
再套一层本拦截器即可. L4 不再需要知道 AUIP 的存在.

详见 ``docs/core-skill-boundary.md`` §4.3.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import structlog

from hermetic_agent.auip.events import TurnEvent, TurnEventType
from hermetic_agent.auip.renderer import get_renderer_registry
from hermetic_agent.providers.streaming import StreamEvent

logger = structlog.get_logger(__name__)


async def stream_intercept_card_renderers(
    iterator: AsyncIterator[StreamEvent],
    *,
    session_id: str = "",
    last_bash_command: str = "",
) -> AsyncIterator[StreamEvent]:
    """包装 StreamEvent 迭代器: tool_result → Card 事件 (通过 CardRendererRegistry).

    路由逻辑:
      1. ``tool_result`` 事件到达
      2. 构造 TurnEvent, 调 ``get_renderer_registry().render()``
      3. 如果业务 SKILL 注册的 CardRenderer 返回 Card, 转为 card 事件 yield
      4. 否则透传原始事件

    Args:
        iterator: 来自 bridge 的原始 StreamEvent 流 (L4→L1).
        session_id: 当前会话 id (打日志用).
        last_bash_command: 最近一次 bash 命令 (传给 CardRenderer context).

    Yields:
        可能含 card 事件的 StreamEvent 流.
    """
    last_bash: str = last_bash_command
    async for event in iterator:
        if event.type == "tool_use" and event.data:
            cmd = event.data.get("input", {})
            if isinstance(cmd, dict) and cmd.get("command"):
                last_bash = cmd.get("command", "")

        if event.type != "tool_result":
            yield event
            continue

        # 业务 SKILL 注册的 CardRenderer 接管.
        turn_event = TurnEvent(
            seq=0,
            turn_id=session_id,
            type=TurnEventType.TOOL_RESULT,
            data=dict(event.data or {}),
        )
        context: dict[str, Any] = {
            "session_id": session_id,
            "last_bash_command": last_bash,
        }
        card = get_renderer_registry().render(turn_event, context)
        if card is not None:
            logger.info(
                "skill_card_emitted",
                session_id=session_id,
                card_id=card.card_id,
                card_type=card.card_type,
            )
            yield StreamEvent.card(
                card_id=card.card_id,
                card_type=card.card_type,
                card={"title": card.title, "body": card.body},
            )
            continue
        yield event


__all__ = ["stream_intercept_card_renderers"]
