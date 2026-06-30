"""L3 AUIP (Agent-User Interaction Protocol) — 通用事件 + 卡片 + Renderer 协议.

基座只提供:
  - ``Card`` / ``BuiltinCardType`` / ``register_card_type()`` / ``CARD_TYPES_SET`` (cards.py)
  - ``TurnEvent`` / ``TurnEventType`` (events.py)
  - ``AUIPError`` 通用错误 (errors.py)
  - ``CardRenderer`` 协议 + ``CardRendererRegistry`` (renderer.py)
  - ``MessageRewriter`` 协议 + ``MessageRewriterRegistry`` (rewriter.py)
  - ``stream_intercept_card_renderers`` 工具结果 → 卡片拦截器
    (stream_interceptor.py)
  - ``compile_skill_md`` 通用 SKILL.md 编译器 (skill_compiler.py)
  - ``first_text`` / ``first_number`` / ``date_part`` 通用字段提取工具
    (_safe_extract.py)
  - opencode 桥接 helper (opencode_resolver.py)

业务 CardType / 业务卡片渲染 / 业务消息改写一律由 SKILL 层通过
``register_card_type()`` + ``CardRendererRegistry`` + ``MessageRewriterRegistry``
注册, 不入基座. 详见 ``docs/core-skill-boundary.md`` §4.
"""

from hermetic_agent.auip._card_type_registry import (
    is_valid_card_type,
    list_registered_card_types,
    register_card_type,
    reset_registered_card_types,
    unregister_card_type,
)
from hermetic_agent.auip._safe_extract import (
    INVALID_NUMBER_SENTINEL,
    date_part,
    first_number,
    first_text,
)
from hermetic_agent.auip.cards import (
    BUILTIN_CARD_TYPES,
    CARD_TYPES_SET,
    BuiltinCardType,
    Card,
    CardType,
)
from hermetic_agent.auip.errors import (
    AUIPError,
    CardSchemaInvalid,
    TurnAlreadyTerminated,
    TurnNotFound,
)
from hermetic_agent.auip.events import TurnEvent, TurnEventType, assert_seq_increasing
from hermetic_agent.auip.renderer import (
    CardRenderer,
    CardRendererRegistry,
    get_renderer_registry,
    reset_renderer_registry,
)
from hermetic_agent.auip.rewriter import (
    MessageRewriter,
    MessageRewriterRegistry,
    get_rewriter_registry,
    reset_rewriter_registry,
)
from hermetic_agent.auip.skill_compiler import compile_skill_md
from hermetic_agent.auip.stream_interceptor import stream_intercept_card_renderers

__all__ = [
    "AUIPError",
    "BUILTIN_CARD_TYPES",
    "BuiltinCardType",
    "CARD_TYPES_SET",
    "Card",
    "CardRenderer",
    "CardRendererRegistry",
    "CardSchemaInvalid",
    "CardType",
    "INVALID_NUMBER_SENTINEL",
    "MessageRewriter",
    "MessageRewriterRegistry",
    "TurnAlreadyTerminated",
    "TurnEvent",
    "TurnEventType",
    "TurnNotFound",
    "assert_seq_increasing",
    "compile_skill_md",
    "date_part",
    "first_number",
    "first_text",
    "get_renderer_registry",
    "get_rewriter_registry",
    "is_valid_card_type",
    "list_registered_card_types",
    "register_card_type",
    "reset_registered_card_types",
    "reset_renderer_registry",
    "reset_rewriter_registry",
    "stream_intercept_card_renderers",
    "unregister_card_type",
]
