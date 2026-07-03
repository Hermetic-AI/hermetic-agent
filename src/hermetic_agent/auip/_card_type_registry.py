"""auip/_card_type_registry.py — CardType 自注册基础设施 (SKILL 业务级).

跟 ``auip/cards.py`` 拆分, 让 cards.py 控制在 L3 文件大小硬上限内.

设计:
  - 内置 CardType (协议级) 由 ``auip/cards.py`` 持有 BuiltinCardType enum.
  - 业务 CardType (SKILL 注册) 在本模块维护一个 set, 用线程锁保护并发安全.
  - 业务 SKILL 在自己 ``__init__.py`` 顶层调 ``register_card_type(name)``
    把本 SKILL 用到的 card_type 加进来.
  - ``auip/cards.py:CARD_TYPES_SET`` 是 builtin + registered 的动态并集.

CardType 自注册协议 (典型用法):

    # work/shared/skills/<your-skill>/__init__.py:
    from hermetic_agent.auip import register_card_type
    register_card_type("FLIGHT_LIST")
    register_card_type("FLIGHT_RESULT")

Hub 启动 / SKILL 加载时 import 这些 ``__init__``, 完成注册.
校验 (Card.from_dict / ask_user 拦截) 取 builtin + registered 的并集.
"""

from __future__ import annotations

import threading

import structlog

logger = structlog.get_logger(__name__)


_registered_card_types: set[str] = set()
_register_lock = threading.Lock()
"""SKILL 运行时注册的 CardType 集合 (可变, 业务级)."""


def register_card_type(name: str, *, replace: bool = False) -> None:
    """注册一个 CardType 字符串 (供 SKILL 启动时调用).

    Args:
        name: CardType 字符串. 建议大写 + 下划线, 跟内置风格一致
            (例 ``FLIGHT_LIST`` / ``ECHO_RESULT``).
        replace: 重复注册时是否覆盖. 默认 False — 业务方误重复注册
            会打 warning, 避免静默覆盖. 测试场景可设 True.

    Raises:
        ValueError: ``name`` 与内置 CardType 冲突.
    """
    from hermetic_agent.auip.cards import BUILTIN_CARD_TYPES

    if name in BUILTIN_CARD_TYPES:
        raise ValueError(
            f"CardType {name!r} is built-in; cannot register. "
            f"Built-in: {sorted(BUILTIN_CARD_TYPES)}"
        )
    with _register_lock:
        if name in _registered_card_types and not replace:
            logger.warning("card_type_already_registered", name=name)
            return
        _registered_card_types.add(name)
        logger.info("card_type_registered", name=name)


def unregister_card_type(name: str) -> None:
    """取消注册 (主要用于测试 / SKILL 热卸载)."""
    with _register_lock:
        _registered_card_types.discard(name)


def reset_registered_card_types() -> None:
    """清空所有 SKILL 注册 (仅用于测试)."""
    with _register_lock:
        _registered_card_types.clear()


def list_registered_card_types() -> set[str]:
    """列出当前已注册的业务 CardType (不含内置)."""
    with _register_lock:
        return set(_registered_card_types)


def is_valid_card_type(name: str) -> bool:
    """判断 name 是否为合法 CardType (built-in + 已注册)."""
    from hermetic_agent.auip.cards import BUILTIN_CARD_TYPES

    return name in BUILTIN_CARD_TYPES or name in _registered_card_types


__all__ = [
    "is_valid_card_type",
    "list_registered_card_types",
    "register_card_type",
    "reset_registered_card_types",
    "unregister_card_type",
]
