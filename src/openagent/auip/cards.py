"""AUIP Card — 协议级 UI 卡片数据模型.

设计文档 §3 L3 / §8.3. Card YAML 格式::

    card_type: FLIGHT_LIST
    schema_version: "1.0"
    title: "请选择航班"
    body: { ... }
    fields: [...]
    options: [...]
    actions: [...]
    metadata: { ... }
    dismissible: false

兼容旧字段 ``decision_buttons`` 作为 ``actions`` 的别名 (P5 简化协议).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from openagent.auip.errors import CardSchemaInvalid


class CardType(str, Enum):
    """Card 类型枚举 (覆盖 P5 业务 + chat 兜底)."""

    CHAT_FALLBACK = "CHAT_FALLBACK"
    OD_INPUT = "OD_INPUT"
    FLIGHT_LIST = "FLIGHT_LIST"
    CABIN_LIST = "CABIN_LIST"
    PASSENGER_FORM = "PASSENGER_FORM"
    OAT_BINDING = "OAT_BINDING"
    PRICE_VERIFY = "PRICE_VERIFY"
    POLICY_DECISION = "POLICY_DECISION"
    ORDER_CONFIRM = "ORDER_CONFIRM"
    ORDER_SUCCESS = "ORDER_SUCCESS"
    CANNOT_ORDER = "CANNOT_ORDER"


CARD_TYPES_SET: set[str] = {c.value for c in CardType}
"""Card type 白名单, 用于 schema 校验 + ask_user tool 的 enum 字段."""

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
        card_type: 见 ``CardType``.
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
    card_type: CardType = CardType.CHAT_FALLBACK
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
            "card_type": self.card_type.value,
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
        # 3. card_type 白名单
        ct = d["card_type"]
        if ct not in CARD_TYPES_SET:
            raise CardSchemaInvalid(
                f"Unknown card_type: {ct!r}. Valid: {sorted(CARD_TYPES_SET)}",
                action=f"Set card_type to one of {sorted(CARD_TYPES_SET)}",
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
            card_type=CardType(d["card_type"]),
            schema_version=str(d["schema_version"]),
            title=str(d["title"]),
            body=d.get("body", {}),
            fields=d.get("fields", []),
            options=d.get("options", []),
            actions=actions,
            metadata=d.get("metadata", {}),
            dismissible=bool(d.get("dismissible", False)),
        )


__all__ = ["CardType", "CARD_TYPES_SET", "Card"]
