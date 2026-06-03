"""tests/test_auip_cards.py — Card 模型 + schema 校验单元测试."""

from __future__ import annotations

from pathlib import Path

import pytest

from openagent.auip.cards import CARD_TYPES_SET, Card, CardType
from openagent.auip.errors import CardSchemaInvalid


# ---------------------------------------------------------------------------
# CardType
# ---------------------------------------------------------------------------


def test_card_type_enum_values_unique() -> None:
    """CardType 11 个值互不重复."""
    assert len(CardType) == 11
    assert len(CARD_TYPES_SET) == 11


def test_card_type_includes_required_business_cards() -> None:
    """关键业务卡 (订票流程) 必须存在."""
    for ct in (
        "CHAT_FALLBACK", "OD_INPUT", "FLIGHT_LIST", "CABIN_LIST",
        "PASSENGER_FORM", "OAT_BINDING", "PRICE_VERIFY", "POLICY_DECISION",
        "ORDER_CONFIRM", "ORDER_SUCCESS", "CANNOT_ORDER",
    ):
        assert ct in CARD_TYPES_SET


# ---------------------------------------------------------------------------
# Card.from_dict
# ---------------------------------------------------------------------------


def test_card_from_dict_minimal_required() -> None:
    """最小必填: card_type / schema_version / title."""
    card = Card.from_dict({
        "card_type": "OD_INPUT",
        "schema_version": "1.0",
        "title": "Test",
    })
    assert card.card_type == CardType.OD_INPUT
    assert card.title == "Test"
    assert card.schema_version == "1.0"
    # 缺省值
    assert card.body == {}
    assert card.fields == []
    assert card.options == []
    assert card.actions == []
    assert card.metadata == {}
    assert card.dismissible is False
    # 自动生成 card_id
    assert card.card_id


def test_card_from_dict_missing_card_type_raises() -> None:
    """缺 card_type 抛 CardSchemaInvalid."""
    with pytest.raises(CardSchemaInvalid, match="card_type"):
        Card.from_dict({"schema_version": "1.0", "title": "T"})


def test_card_from_dict_missing_title_raises() -> None:
    """缺 title 抛 CardSchemaInvalid."""
    with pytest.raises(CardSchemaInvalid, match="title"):
        Card.from_dict({"card_type": "OD_INPUT", "schema_version": "1.0"})


def test_card_from_dict_missing_schema_version_raises() -> None:
    """缺 schema_version 抛 CardSchemaInvalid."""
    with pytest.raises(CardSchemaInvalid, match="schema_version"):
        Card.from_dict({"card_type": "OD_INPUT", "title": "T"})


def test_card_from_dict_unknown_card_type_raises() -> None:
    """未知 card_type 抛 CardSchemaInvalid, 提示合法值."""
    with pytest.raises(CardSchemaInvalid) as exc_info:
        Card.from_dict({
            "card_type": "BOGUS_CARD",
            "schema_version": "1.0",
            "title": "T",
        })
    msg = str(exc_info.value)
    assert "BOGUS_CARD" in msg
    assert "Valid" in msg
    assert "OD_INPUT" in msg  # 合法值列表
    # action 字段: 提示如何修
    assert exc_info.value.action


def test_card_from_dict_unknown_top_level_field_raises() -> None:
    """未知顶层字段抛 CardSchemaInvalid (白名单校验)."""
    with pytest.raises(CardSchemaInvalid, match="Unknown card field"):
        Card.from_dict({
            "card_type": "OD_INPUT",
            "schema_version": "1.0",
            "title": "T",
            "evil_field": "x",
        })


def test_card_from_dict_body_must_be_dict() -> None:
    """body 必须是 dict."""
    with pytest.raises(CardSchemaInvalid, match="body must be a dict"):
        Card.from_dict({
            "card_type": "OD_INPUT",
            "schema_version": "1.0",
            "title": "T",
            "body": "not a dict",
        })


def test_card_from_dict_options_must_be_list() -> None:
    """options 必须是 list."""
    with pytest.raises(CardSchemaInvalid, match="options must be a list"):
        Card.from_dict({
            "card_type": "FLIGHT_LIST",
            "schema_version": "1.0",
            "title": "T",
            "options": "not a list",
        })


def test_card_from_dict_actions_fallback_decision_buttons() -> None:
    """actions 为空时, decision_buttons 作为兜底 (P5 协议)."""
    card = Card.from_dict({
        "card_type": "POLICY_DECISION",
        "schema_version": "1.0",
        "title": "policy",
        "decision_buttons": [
            {"id": "pay", "label": "Pay"},
            {"id": "abort", "label": "Abort"},
        ],
    })
    assert len(card.actions) == 2
    assert card.actions[0]["id"] == "pay"


def test_card_from_dict_actions_takes_priority_over_decision_buttons() -> None:
    """actions 存在时, decision_buttons 被忽略 (P5 协议)."""
    card = Card.from_dict({
        "card_type": "POLICY_DECISION",
        "schema_version": "1.0",
        "title": "policy",
        "actions": [{"id": "primary", "label": "A"}],
        "decision_buttons": [{"id": "fallback", "label": "B"}],
    })
    assert len(card.actions) == 1
    assert card.actions[0]["id"] == "primary"


def test_card_from_dict_preserves_card_id() -> None:
    """显式给 card_id 时保留."""
    card = Card.from_dict({
        "card_id": "my-id",
        "card_type": "OD_INPUT",
        "schema_version": "1.0",
        "title": "T",
    })
    assert card.card_id == "my-id"


def test_card_from_dict_top_level_not_dict_raises() -> None:
    """顶层非 dict 抛 CardSchemaInvalid."""
    with pytest.raises(CardSchemaInvalid, match="must be a mapping"):
        Card.from_dict("not a dict")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Card.to_dict roundtrip
# ---------------------------------------------------------------------------


def test_card_to_dict_roundtrip() -> None:
    """to_dict 包含全部字段, 反序列化后字段一致."""
    card = Card.from_dict({
        "card_id": "c-1",
        "card_type": "FLIGHT_LIST",
        "schema_version": "1.0",
        "title": "Choose",
        "body": {"message": "m"},
        "options": [{"id": "f1", "label": "F1"}],
        "actions": [{"id": "select", "label": "OK"}],
        "metadata": {"state": "S05"},
        "dismissible": True,
    })
    d = card.to_dict()
    assert d["card_id"] == "c-1"
    assert d["card_type"] == "FLIGHT_LIST"
    assert d["schema_version"] == "1.0"
    assert d["title"] == "Choose"
    assert d["body"] == {"message": "m"}
    assert d["options"] == [{"id": "f1", "label": "F1"}]
    assert d["actions"] == [{"id": "select", "label": "OK"}]
    assert d["metadata"] == {"state": "S05"}
    assert d["dismissible"] is True


def test_card_to_dict_serialization_via_from_dict() -> None:
    """to_dict → from_dict 互逆."""
    card = Card.from_dict({
        "card_type": "OD_INPUT",
        "schema_version": "1.0",
        "title": "T",
        "body": {"k": "v"},
    })
    d = card.to_dict()
    card2 = Card.from_dict(d)
    assert card2.card_id == card.card_id
    assert card2.card_type == card.card_type
    assert card2.title == card.title
    assert card2.body == card.body


# ---------------------------------------------------------------------------
# Card.from_yaml
# ---------------------------------------------------------------------------


def test_card_from_yaml_od_input(tmp_path: Path) -> None:
    """从 YAML 加载 OD_INPUT card."""
    yaml = """
card_type: OD_INPUT
schema_version: "1.0"
title: "请告诉我出发地 / 目的地"
body:
  message: "为了查询航班, 我需要知道城市和日期"
fields:
  - id: origin
    label: "出发地"
    type: text
options:
  - id: pek
    label: "北京 PEK"
metadata:
  state: S02
  skill: book-flight
"""
    p = tmp_path / "OD_INPUT.card.yaml"
    p.write_text(yaml, encoding="utf-8")
    card = Card.from_yaml(p)
    assert card.card_type == CardType.OD_INPUT
    assert card.title == "请告诉我出发地 / 目的地"
    assert card.body == {"message": "为了查询航班, 我需要知道城市和日期"}
    assert len(card.fields) == 1
    assert card.fields[0]["id"] == "origin"
    assert len(card.options) == 1
    assert card.metadata["state"] == "S02"


def test_card_from_yaml_missing_file_raises(tmp_path: Path) -> None:
    """YAML 文件不存在抛 CardSchemaInvalid (含可读 action)."""
    p = tmp_path / "missing.yaml"
    with pytest.raises(CardSchemaInvalid):
        Card.from_yaml(p)
