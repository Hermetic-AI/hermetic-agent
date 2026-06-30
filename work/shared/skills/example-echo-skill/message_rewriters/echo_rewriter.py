"""Echo MessageRewriter — 把 echo 卡的提交消息改写成自然语言.

基座 MessageRewriter 协议 (hermetic_agent.auip.rewriter) 的标准实现.
"""
from __future__ import annotations

from typing import Any

from hermetic_agent.auip.rewriter import MessageRewriter
from hermetic_agent.providers.streaming import StreamEvent


class EchoMessageRewriter:
    """基座 MessageRewriter 协议的标准实现 — 业务模板."""

    def tool_names(self) -> set[str]:
        return {"ask_user"}

    def rewrite(
        self,
        event: StreamEvent,
        context: dict[str, Any],
    ) -> StreamEvent | None:
        data = event.data or {}
        action_id = data.get("action_id", "")
        if action_id == "confirm":
            return StreamEvent.text(content="用户已确认 echo 结果, 继续对话.")
        if action_id == "cancel":
            return StreamEvent.text(content="用户已取消 echo, 回到 S01 状态.")
        return None


__all__ = ["EchoMessageRewriter"]
