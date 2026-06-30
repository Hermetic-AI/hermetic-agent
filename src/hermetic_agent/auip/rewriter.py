"""auip/rewriter.py — MessageRewriter 协议.

基座定义的"通用协议", 业务 SKILL 实现并注册. 当 user 提交一张 card 时
(表单/选项/按钮), LLM 看不到 JSON, 业务 SKILL 注册的 Rewriter 把
JSON 改写成自然语言, 然后 LLM 才能继续对话. 详见
``docs/core-skill-boundary.md`` §4.4.

典型用法 (SKILL 侧):
    from hermetic_agent.auip.rewriter import MessageRewriter

    class MyBusinessMessageRewriter:
        def tool_names(self) -> set[str]:
            return {"ask_user"}

        def rewrite(self, event, context):
            data = event.data.get("content", {})
            if data.get("type") == "card_submission":
                choice = data.get("flightId", "未指定")
                return StreamEvent.text(content=f"我选择 {choice} 这班航班.")
            return None
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import structlog

from hermetic_agent.providers.streaming import StreamEvent

logger = structlog.get_logger(__name__)


@runtime_checkable
class MessageRewriter(Protocol):
    """把 card-submit 类的 user message 改写成自然语言.

    LLM 不知道 AUIP 协议. 业务 SKILL 注册 Rewriter, 在 LLM 看到 user message
    前把表单数据 'card_submission: {flightId: "..."}' 改写成
    '我选择 CA1234 这班航班.'. 这样 LLM 才能用自然语言继续对话.
    """

    def tool_names(self) -> set[str]:
        """声明本 Rewriter 关注的 tool name 集合.

        通常是 ``{"ask_user"}`` — card 提交是 ask_user tool 走的路径.
        也可以是其他 tool, 视具体业务而定.
        """
        ...

    def rewrite(
        self,
        event: StreamEvent,
        context: dict[str, Any],
    ) -> StreamEvent | None:
        """返回改写后的 event, 或 None 表示不处理 (透传)."""
        ...


class MessageRewriterRegistry:
    """MessageRewriter 注册表 — 同 CardRenderer, 详见 renderer.py."""

    def __init__(self) -> None:
        self._rewriters: dict[str, MessageRewriter] = {}
        self._wildcard_rewriters: list[MessageRewriter] = []

    def register(self, rewriter: MessageRewriter, *, replace: bool = True) -> None:
        names = rewriter.tool_names()
        if not names:
            self._wildcard_rewriters.append(rewriter)
            logger.info("message_rewriter_registered_wildcard")
            return
        for name in names:
            if name in self._rewriters and not replace:
                raise ValueError(
                    f"Rewriter for tool {name!r} already registered; "
                    "pass replace=True to override."
                )
            self._rewriters[name] = rewriter
            logger.info("message_rewriter_registered", tool_name=name)

    def unregister(self, rewriter: MessageRewriter) -> None:
        names = rewriter.tool_names()
        for name in names:
            if self._rewriters.get(name) is rewriter:
                del self._rewriters[name]
        if rewriter in self._wildcard_rewriters:
            self._wildcard_rewriters.remove(rewriter)

    def get(self, tool_name: str) -> MessageRewriter | None:
        return self._rewriters.get(tool_name)

    def iter_all(self) -> list[MessageRewriter]:
        return list(set(self._rewriters.values()) | set(self._wildcard_rewriters))

    def rewrite(
        self,
        event: StreamEvent,
        context: dict[str, Any],
    ) -> StreamEvent | None:
        """找到第一个匹配的 rewriter, 调用其 rewrite().

        路由顺序同 ``CardRendererRegistry.render``: tool_name 精确 → 兜底.
        返回 None 表示没人处理, 由 caller 决定透传.
        """
        tool_name = (event.data or {}).get("tool_name", "")
        if tool_name:
            rewriter = self._rewriters.get(tool_name)
            if rewriter is not None:
                return rewriter.rewrite(event, context)
        for rewriter in self._wildcard_rewriters:
            result = rewriter.rewrite(event, context)
            if result is not None:
                return result
        return None


_REGISTRY: MessageRewriterRegistry | None = None


def get_rewriter_registry() -> MessageRewriterRegistry:
    """获取全局 MessageRewriterRegistry 单例."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = MessageRewriterRegistry()
    return _REGISTRY


def reset_rewriter_registry() -> None:
    """重置 registry — 主要用于测试."""
    global _REGISTRY
    _REGISTRY = None


__all__ = [
    "MessageRewriter",
    "MessageRewriterRegistry",
    "get_rewriter_registry",
    "reset_rewriter_registry",
]
