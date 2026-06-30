"""example-echo-skill — 业务 SKILL 注册样板.

Hub 启动时扫描 SKILL 目录, 自动 import 各模块, 调本文件暴露的
``register_*()`` 把业务实现注入基座 Registry.

业务 SKILL 标准做法 (Phase 4 新规):
  1. 在本 ``__init__.py`` 顶层调 ``register_card_type()`` 把所有要用的
     CardType 字符串注册到基座白名单.
  2. 在 ``card_renderers/`` 实现 CardRenderer 子类.
  3. 在 ``message_rewriters/`` 实现 MessageRewriter 子类.
  4. 在本 ``__init__.py`` 暴露 ``register_renderers()`` /
     ``register_rewriters()`` 入口, 由 Hub 启动钩子调用.
"""
from __future__ import annotations

from hermetic_agent.auip import (
    CardRendererRegistry,
    MessageRewriterRegistry,
    register_card_type,
)

from .card_renderers.echo_renderer import ECHO_RESULT_CARD_TYPE, EchoCardRenderer
from .message_rewriters.echo_rewriter import EchoMessageRewriter

register_card_type(ECHO_RESULT_CARD_TYPE)


def register_renderers(registry: CardRendererRegistry) -> None:
    """Hub 启动时调用 — 把 EchoCardRenderer 注册到基座 Registry."""
    registry.register(EchoCardRenderer())


def register_rewriters(registry: MessageRewriterRegistry) -> None:
    """Hub 启动时调用 — 把 EchoMessageRewriter 注册到基座 Registry."""
    registry.register(EchoMessageRewriter())


__all__ = [
    "register_renderers",
    "register_rewriters",
]
