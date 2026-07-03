"""auip/renderer.py — CardRenderer 协议 + CardRendererRegistry.

基座定义的"通用协议", 业务 SKILL 实现并注册. Hub 看到 tool_result 事件
时, 按 tool_name 路由到匹配 Renderer. 详见 ``docs/core-skill-boundary.md`` §4.3.

设计动机:
  老方案 (``auip/flight_card.py`` 等) 把具体业务的 CardType 渲染逻辑直接
  写在基座. 一个新业务就需要碰基座代码. 这里把渲染能力下沉到 SKILL,
  基座只负责 "路由 + 调用" 这层薄壳.

典型用法 (SKILL 侧):

    # 1) 在 SKILL __init__.py 注册 CardType (启动时)
    from hermetic_agent.auip import register_card_type
    register_card_type("MY_BUSINESS_CARD")

    # 2) 实现 CardRenderer
    from hermetic_agent.auip.renderer import CardRenderer, CardRendererRegistry

    class MyBusinessCardRenderer:
        def tool_names(self) -> set[str]:
            return {"my_mcp_query_data"}

        def can_render(self, event, context):
            return bool(event.data.get("output"))

        def render(self, event, context):
            output = event.data.get("output")
            return Card(card_type="MY_BUSINESS_CARD", title="...", body={...})

    # 3) SKILL 启动时注册 (基座扫描 SKILL 包时自动调)
    def register_renderers(registry: CardRendererRegistry) -> None:
        registry.register(MyBusinessCardRenderer())
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import structlog

from hermetic_agent.auip.cards import Card
from hermetic_agent.auip.events import TurnEvent

logger = structlog.get_logger(__name__)


@runtime_checkable
class CardRenderer(Protocol):
    """业务 SKILL 实现的卡片渲染器协议.

    基座在 tool_result 事件发生时, 按 tool_name 路由到对应 Renderer.
    Renderer 决定:
      1. 自己能不能处理这个 tool_result (can_render)
      2. 怎么把 tool_result 数据转换成 Card (render)
    """

    def tool_names(self) -> set[str]:
        """声明本 Renderer 关注的 tool name 集合.

        基座用此做路由: 收到 tool_result 时, 找匹配 tool 的 Renderer.
        返回空集合意味着 "我是一个兜底 renderer, 任何 tool 都可以尝试",
        此时应保持极少的兜底逻辑, 不要吞掉具体业务 renderer 的活儿.
        """
        ...

    def can_render(self, event: TurnEvent, context: dict[str, Any]) -> bool:
        """快速判断: 这个事件我能渲染吗? (数据完整性 / 状态等)

        应当是 O(1) 检查, 不要在 can_render 里做全量数据解析.
        """
        ...

    def render(self, event: TurnEvent, context: dict[str, Any]) -> Card | None:
        """从 event.data + context 构造一张 Card. 失败返 None.

        event.data 是 TurnEvent.data, 通常含 ``tool_name`` / ``output`` /
        ``part_id`` 等键. context 透传上层 (session_id / scenario_name 等).
        """
        ...


class CardRendererRegistry:
    """CardRenderer 注册表 — 基座持有单例, SKILL 注册自己的实现.

    路由策略: ``tool_name`` 优先匹配, 失败后落到 ``*_default`` renderer.
    同一 tool_name 注册多个 renderer 时, **后者覆盖前者** (后注册赢).
    """

    def __init__(self) -> None:
        self._renderers: dict[str, CardRenderer] = {}
        self._wildcard_renderers: list[CardRenderer] = []

    def register(self, renderer: CardRenderer, *, replace: bool = True) -> None:
        """注册一个 renderer.

        Args:
            renderer: 实现了 ``CardRenderer`` 协议的对象.
            replace: True (默认) 覆盖同名 tool 的旧 renderer. False 时
                遇到重复 tool_name 抛 ``ValueError``.
        """
        names = renderer.tool_names()
        if not names:
            self._wildcard_renderers.append(renderer)
            logger.info("card_renderer_registered_wildcard")
            return
        for name in names:
            if name in self._renderers and not replace:
                raise ValueError(
                    f"Renderer for tool {name!r} already registered; "
                    "pass replace=True to override."
                )
            self._renderers[name] = renderer
            logger.info("card_renderer_registered", tool_name=name)

    def unregister(self, renderer: CardRenderer) -> None:
        names = renderer.tool_names()
        for name in names:
            if self._renderers.get(name) is renderer:
                del self._renderers[name]
        if renderer in self._wildcard_renderers:
            self._wildcard_renderers.remove(renderer)

    def get(self, tool_name: str) -> CardRenderer | None:
        """按 tool_name 找 renderer, 找不到返 None."""
        return self._renderers.get(tool_name)

    def iter_all(self) -> list[CardRenderer]:
        """列出所有已注册的 renderer (deduplicated)."""
        return list(set(self._renderers.values()) | set(self._wildcard_renderers))

    def render(
        self,
        event: TurnEvent,
        context: dict[str, Any],
    ) -> Card | None:
        """路由 + 渲染: 找到第一个能渲染的 renderer, 调用其 render().

        路由顺序:
          1. 精确匹配 ``event.data["tool_name"]`` 的 renderer
          2. 兜底: ``wildcard_renderers`` 中第一个 ``can_render`` 为 True 的

        Returns:
            ``Card`` 或 None (没 renderer 处理 / 全部 render 失败).
        """
        tool_name = (event.data or {}).get("tool_name", "")
        if tool_name:
            renderer = self._renderers.get(tool_name)
            if renderer is not None and renderer.can_render(event, context):
                return renderer.render(event, context)
        for renderer in self._wildcard_renderers:
            if renderer.can_render(event, context):
                return renderer.render(event, context)
        return None


_REGISTRY: CardRendererRegistry | None = None


def get_renderer_registry() -> CardRendererRegistry:
    """获取全局 CardRendererRegistry 单例.

    第一次调用时构造, 之后复用. SKILL 启动时通过 ``register_renderers()``
    把自己实现注册进去. 详见 ``docs/core-skill-boundary.md`` §4.3.
    """
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = CardRendererRegistry()
    return _REGISTRY


def reset_renderer_registry() -> None:
    """重置 registry — 主要用于测试."""
    global _REGISTRY
    _REGISTRY = None


__all__ = [
    "CardRenderer",
    "CardRendererRegistry",
    "get_renderer_registry",
    "reset_renderer_registry",
]
