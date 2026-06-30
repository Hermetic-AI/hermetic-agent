"""tests/test_auip_cards.py — Card 模型 + schema 校验 + CardType 自注册单元测试."""

from __future__ import annotations

from pathlib import Path

import pytest

from hermetic_agent.auip.cards import (
    BUILTIN_CARD_TYPES,
    BuiltinCardType,
    CARD_TYPES_SET,
    Card,
    is_valid_card_type,
    list_registered_card_types,
    register_card_type,
    reset_registered_card_types,
)
from hermetic_agent.auip.errors import CardSchemaInvalid


@pytest.fixture(autouse=True)
def _reset_registered_card_types() -> None:
    """每个用例前后清空 SKILL 注册, 避免污染."""
    reset_registered_card_types()
    yield
    reset_registered_card_types()


# ---------------------------------------------------------------------------
# CardType 自注册协议
# ---------------------------------------------------------------------------


def test_builtin_card_type_has_four_values() -> None:
    """基座内置 CardType 协议级 4 个: CHAT_FALLBACK / OD_INPUT / QUESTION / TODO_LIST."""
    assert len(BuiltinCardType) == 4
    assert BuiltinCardType.CHAT_FALLBACK.value == "CHAT_FALLBACK"
    assert BuiltinCardType.OD_INPUT.value == "OD_INPUT"
    assert BuiltinCardType.QUESTION.value == "QUESTION"
    assert BuiltinCardType.TODO_LIST.value == "TODO_LIST"
    assert BUILTIN_CARD_TYPES == frozenset(
        {"CHAT_FALLBACK", "OD_INPUT", "QUESTION", "TODO_LIST"}
    )


def test_card_types_set_includes_builtin_only_initially() -> None:
    """未注册任何 SKILL 时, CARD_TYPES_SET 只含内置 4 个."""
    assert "CHAT_FALLBACK" in CARD_TYPES_SET
    assert "OD_INPUT" in CARD_TYPES_SET
    assert "QUESTION" in CARD_TYPES_SET
    assert "TODO_LIST" in CARD_TYPES_SET
    assert "FLIGHT_LIST" not in CARD_TYPES_SET
    assert "ECHO_RESULT" not in CARD_TYPES_SET


def test_register_card_type_adds_to_valid_set() -> None:
    """register_card_type() 后, 该 CardType 立即生效."""
    register_card_type("FLIGHT_LIST")
    register_card_type("FLIGHT_RESULT")
    register_card_type("ECHO_RESULT")
    assert is_valid_card_type("FLIGHT_LIST")
    assert is_valid_card_type("FLIGHT_RESULT")
    assert is_valid_card_type("ECHO_RESULT")
    assert "FLIGHT_LIST" in CARD_TYPES_SET
    assert list_registered_card_types() >= {
        "FLIGHT_LIST", "FLIGHT_RESULT", "ECHO_RESULT",
    }


def test_register_card_type_builtin_name_raises() -> None:
    """注册跟内置冲突的名字 → ValueError."""
    with pytest.raises(ValueError, match="built-in"):
        register_card_type("CHAT_FALLBACK")


def test_register_card_type_duplicate_warns_only() -> None:
    """重复注册 (默认 replace=False) → 不报错, 仅 warning."""
    register_card_type("FLIGHT_LIST")
    register_card_type("FLIGHT_LIST")  # 第二次 → warning, 不抛
    assert "FLIGHT_LIST" in list_registered_card_types()


def test_register_card_type_replace_true_overrides() -> None:
    """replace=True 显式覆盖 (主要用于测试 reset 场景)."""
    register_card_type("X")
    register_card_type("X", replace=True)
    assert "X" in list_registered_card_types()


def test_unregister_card_type_removes() -> None:
    """unregister_card_type() 取消注册."""
    register_card_type("TEMP_CARD")
    assert is_valid_card_type("TEMP_CARD")
    from hermetic_agent.auip.cards import unregister_card_type
    unregister_card_type("TEMP_CARD")
    assert not is_valid_card_type("TEMP_CARD")


# ---------------------------------------------------------------------------
# Card.from_dict
# ---------------------------------------------------------------------------


def test_card_from_dict_minimal_required() -> None:
    """最小必填: card_type / schema_version / title."""
    card = Card.from_dict({
        "card_type": "CHAT_FALLBACK",
        "schema_version": "1.0",
        "title": "Test",
    })
    assert card.card_type == "CHAT_FALLBACK"
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


def test_card_from_dict_skill_registered_type_works() -> None:
    """业务 SKILL 注册过的 CardType, from_dict 接受."""
    register_card_type("FLIGHT_LIST")
    card = Card.from_dict({
        "card_type": "FLIGHT_LIST",
        "schema_version": "1.0",
        "title": "Choose",
        "options": [{"id": "f1", "label": "F1"}],
    })
    assert card.card_type == "FLIGHT_LIST"
    assert len(card.options) == 1


def test_card_from_dict_missing_card_type_raises() -> None:
    """缺 card_type 抛 CardSchemaInvalid."""
    with pytest.raises(CardSchemaInvalid, match="card_type"):
        Card.from_dict({"schema_version": "1.0", "title": "T"})


def test_card_from_dict_missing_title_raises() -> None:
    """缺 title 抛 CardSchemaInvalid."""
    with pytest.raises(CardSchemaInvalid, match="title"):
        Card.from_dict({"card_type": "CHAT_FALLBACK", "schema_version": "1.0"})


def test_card_from_dict_missing_schema_version_raises() -> None:
    """缺 schema_version 抛 CardSchemaInvalid."""
    with pytest.raises(CardSchemaInvalid, match="schema_version"):
        Card.from_dict({"card_type": "CHAT_FALLBACK", "title": "T"})


def test_card_from_dict_unknown_card_type_raises() -> None:
    """未注册的业务 card_type 抛 CardSchemaInvalid + 提示 register_card_type."""
    with pytest.raises(CardSchemaInvalid) as exc_info:
        Card.from_dict({
            "card_type": "BOGUS_CARD",
            "schema_version": "1.0",
            "title": "T",
        })
    msg = str(exc_info.value)
    assert "BOGUS_CARD" in msg
    assert "register_card_type" in msg
    assert exc_info.value.action


def test_card_from_dict_unknown_top_level_field_raises() -> None:
    """未知顶层字段抛 CardSchemaInvalid (白名单校验)."""
    with pytest.raises(CardSchemaInvalid, match="Unknown card field"):
        Card.from_dict({
            "card_type": "CHAT_FALLBACK",
            "schema_version": "1.0",
            "title": "T",
            "evil_field": "x",
        })


def test_card_from_dict_body_must_be_dict() -> None:
    """body 必须是 dict."""
    with pytest.raises(CardSchemaInvalid, match="body must be a dict"):
        Card.from_dict({
            "card_type": "CHAT_FALLBACK",
            "schema_version": "1.0",
            "title": "T",
            "body": "not a dict",
        })


def test_card_from_dict_options_must_be_list() -> None:
    """options 必须是 list."""
    register_card_type("FLIGHT_LIST")
    with pytest.raises(CardSchemaInvalid, match="options must be a list"):
        Card.from_dict({
            "card_type": "FLIGHT_LIST",
            "schema_version": "1.0",
            "title": "T",
            "options": "not a list",
        })


def test_card_from_dict_actions_fallback_decision_buttons() -> None:
    """actions 为空时, decision_buttons 作为兜底 (P5 协议)."""
    register_card_type("POLICY_DECISION")
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
    register_card_type("POLICY_DECISION")
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
        "card_type": "CHAT_FALLBACK",
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
    register_card_type("FLIGHT_LIST")
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
        "card_type": "CHAT_FALLBACK",
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


def test_card_from_yaml_chat_fallback(tmp_path: Path) -> None:
    """从 YAML 加载 CHAT_FALLBACK card (内置)."""
    yaml_text = """
card_type: CHAT_FALLBACK
schema_version: "1.0"
title: "请告诉我出发地 / 目的地"
body:
  message: "为了查询数据, 我需要更多信息"
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
    p = tmp_path / "CHAT_FALLBACK.card.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    card = Card.from_yaml(p)
    assert card.card_type == "CHAT_FALLBACK"
    assert card.title == "请告诉我出发地 / 目的地"
    assert card.body == {"message": "为了查询数据, 我需要更多信息"}
    assert len(card.fields) == 1
    assert card.fields[0]["id"] == "origin"
    assert len(card.options) == 1
    assert card.metadata["state"] == "S02"


def test_card_from_yaml_skill_registered_type(tmp_path: Path) -> None:
    """YAML 含 SKILL 注册的 CardType (FLIGHT_LIST) — from_yaml 接受."""
    register_card_type("FLIGHT_LIST")
    yaml_text = """
card_type: FLIGHT_LIST
schema_version: "1.0"
title: "请选择"
options:
  - id: a
    label: A
  - id: b
    label: B
"""
    p = tmp_path / "FLIGHT_LIST.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    card = Card.from_yaml(p)
    assert card.card_type == "FLIGHT_LIST"
    assert len(card.options) == 2


def test_card_from_yaml_missing_file_raises(tmp_path: Path) -> None:
    """YAML 文件不存在抛 CardSchemaInvalid (含可读 action)."""
    p = tmp_path / "missing.yaml"
    with pytest.raises(CardSchemaInvalid):
        Card.from_yaml(p)
