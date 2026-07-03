"""AUIP Card — 协议级 UI 卡片数据模型.

设计文档 §3 L3 / §8.3. Card YAML 格式::

    card_type: <string>            # 见下方 CardType 分类
    schema_version: "1.0"
    title: "..."
    body: { ... }
    fields: [...]
    options: [...]
    actions: [...]
    metadata: { ... }
    dismissible: false

CardType 分类 (SKILL 自注册协议见 ``_card_type_registry.py``):

  内置 (Built-in, 协议级, 基座自带):
    - ``CHAT_FALLBACK`` — 兜底 chat 卡片
    - ``OD_INPUT`` — 通用"单轮输入表单" (SuspendableScheduler 默认, HITL 协议级)
    - ``QUESTION`` — 对应 opencode ask_user question 卡片
    - ``TODO_LIST`` — 对应 opencode ask_user todo 卡片

  SKILL 自注册 (业务级, SKILL 启动时 ``register_card_type(name)``):
    业务方按需扩展, 任何字符串都行, 建议大写下划线风格
    (例 ``FLIGHT_LIST`` / ``ECHO_RESULT`` / ``PRICE_VERIFY``).

兼容旧字段 ``decision_buttons`` 作为 ``actions`` 的别名 (P5 简化协议).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from hermetic_agent.auip._card_type_registry import (
    is_valid_card_type,
    list_registered_card_types,
    register_card_type,
    reset_registered_card_types,
    unregister_card_type,
)
from hermetic_agent.auip.errors import CardSchemaInvalid


class BuiltinCardType(str, Enum):
    """基座内置 CardType (协议级, 与具体业务无关)."""

    CHAT_FALLBACK = "CHAT_FALLBACK"
    OD_INPUT = "OD_INPUT"
    QUESTION = "QUESTION"
    TODO_LIST = "TODO_LIST"


BUILTIN_CARD_TYPES: frozenset[str] = frozenset(c.value for c in BuiltinCardType)
"""内置 CardType 字符串集合 (不可变)."""


# 向后兼容: CardType 是 BuiltinCardType 的别名.
# 老代码 ``from hermetic_agent.auip.cards import CardType`` 还能用,
# 但 CardType 现在只含内置 4 个. 业务 CardType 走 ``register_card_type()``.
CardType = BuiltinCardType


class _CardTypesSet:
    """动态 CardType 白名单视图 (built-in + 已注册).

    向后兼容: 旧代码 ``ct in CARD_TYPES_SET`` / ``sorted(CARD_TYPES_SET)``
    写法无需改 import, 行为等价于 ``set(BUILTIN | registered)``.
    实际是动态计算, 任何时候 ``register_card_type()`` 之后立即可见.
    """

    def __contains__(self, item: object) -> bool:
        return is_valid_card_type(str(item))

    def __iter__(self):
        return iter(BUILTIN_CARD_TYPES | frozenset(list_registered_card_types()))

    def __len__(self) -> int:
        return len(BUILTIN_CARD_TYPES) + len(list_registered_card_types())

    def __bool__(self) -> bool:
        return True

    def __repr__(self) -> str:
        return f"_CardTypesSet({sorted(self)!r})"


CARD_TYPES_SET: _CardTypesSet = _CardTypesSet()
"""CardType 动态白名单视图 (兼容旧 set 接口)."""


# 合法 fields / options / actions / metadata 顶层 key (白名单, 简化校验)
_VALID_CARD_KEYS = {
    "card_id", "card_type", "schema_version", "title",
    "body", "fields", "options", "actions", "decision_buttons",
    "metadata", "dismissible",
}


@dataclass
class Card:
    """一张 UI 卡片.

    Attributes:
        card_id: 唯一 id; 缺省由 from_dict 自动生成.
        card_type: 业务定义的 CardType 字符串 (内置 4 个 + SKILL 注册 N 个).
            运行时按 ``is_valid_card_type()`` 校验; 通过后原样保留.
        schema_version: schema 版本, 当前固定 ``"1.0"``.
        title: 卡片标题, 必填.
        body: 自由格式 dict, 由前端按 card_type 渲染.
        fields: 表单字段列表.
        options: 选项列表 (单选/多选).
        actions: 决策按钮列表; 兼容 ``decision_buttons`` 别名.
        metadata: 附加元数据 (state / skill / schema_id 等).
        dismissible: 用户能否关掉 (默认 False, 表示强制交互).
    """

    card_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    card_type: str = BuiltinCardType.CHAT_FALLBACK.value
    schema_version: str = "1.0"
    title: str = ""
    body: dict[str, Any] = field(default_factory=dict)
    fields: list[dict[str, Any]] = field(default_factory=list)
    options: list[dict[str, Any]] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    dismissible: bool = False

    def to_dict(self) -> dict[str, Any]:
        """序列化为 dict (SSE / DB)."""
        return {
            "card_id": self.card_id,
            "card_type": self.card_type,
            "schema_version": self.schema_version,
            "title": self.title,
            "body": self.body,
            "fields": self.fields,
            "options": self.options,
            "actions": self.actions,
            "metadata": self.metadata,
            "dismissible": self.dismissible,
        }

    @classmethod
    def from_yaml(cls, path: str | Path) -> Card:
        """从 YAML 文件加载.

        Raises:
            CardSchemaInvalid: YAML 缺失 / 字段缺失 / card_type 未知.
        """
        p = Path(path)
        try:
            raw = yaml.safe_load(p.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise CardSchemaInvalid(
                f"Failed to read card YAML {p!s}: {exc}",
                action=f"Check the YAML file at {p}",
            ) from exc
        if not isinstance(raw, dict):
            raise CardSchemaInvalid(
                f"Card YAML {p!s} top-level must be a mapping, "
                f"got {type(raw).__name__}",
            )
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Card:
        """从 dict 构造 Card, 含 schema 校验.

        Raises:
            CardSchemaInvalid: 缺必填字段 / card_type 不在白名单 /
                含未知顶层字段.
        """
        if not isinstance(d, dict):
            raise CardSchemaInvalid(
                f"Card dict must be a mapping, got {type(d).__name__}",
            )
        # 1. 未知字段白名单
        extra = set(d) - _VALID_CARD_KEYS
        if extra:
            raise CardSchemaInvalid(
                f"Unknown card field(s): {sorted(extra)}. "
                f"Valid: {sorted(_VALID_CARD_KEYS)}",
            )
        # 2. 必填字段
        for required in ("card_type", "schema_version", "title"):
            if required not in d:
                raise CardSchemaInvalid(
                    f"Missing required field: {required!r}",
                    action=f"Add {required!r} to card YAML",
                )
        # 3. card_type 白名单 (built-in + 已注册)
        ct = str(d["card_type"])
        if not is_valid_card_type(ct):
            raise CardSchemaInvalid(
                f"Unknown card_type: {ct!r}. "
                f"Built-in: {sorted(BUILTIN_CARD_TYPES)}. "
                f"Registered: {sorted(list_registered_card_types())}.",
                action=(
                    f"Either use a built-in card_type or have your SKILL call "
                    f"register_card_type({ct!r}) at startup."
                ),
            )
        # 4. 嵌套类型粗校验
        for key in ("body", "metadata"):
            if key in d and not isinstance(d[key], dict):
                raise CardSchemaInvalid(
                    f"card.{key} must be a dict, got {type(d[key]).__name__}",
                )
        for key in ("fields", "options", "actions", "decision_buttons"):
            if key in d and not isinstance(d[key], list):
                raise CardSchemaInvalid(
                    f"card.{key} must be a list, got {type(d[key]).__name__}",
                )
        # 5. actions 兼容 decision_buttons
        actions = d.get("actions")
        if not actions:
            actions = d.get("decision_buttons", [])
        return cls(
            card_id=d.get("card_id", str(uuid.uuid4())),
            card_type=ct,
            schema_version=str(d["schema_version"]),
            title=str(d["title"]),
            body=d.get("body", {}),
            fields=d.get("fields", []),
            options=d.get("options", []),
            actions=actions,
            metadata=d.get("metadata", {}),
            dismissible=bool(d.get("dismissible", False)),
        )


__all__ = [
    "BUILTIN_CARD_TYPES",
    "BuiltinCardType",
    "CARD_TYPES_SET",
    "Card",
    "CardType",
    "is_valid_card_type",
    "list_registered_card_types",
    "register_card_type",
    "reset_registered_card_types",
    "unregister_card_type",
]
