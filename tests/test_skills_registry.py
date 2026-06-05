"""tests/test_skills_registry.py — SkillRegistry 单元测试 (P1-3 metadata_list)."""
from __future__ import annotations

import pytest

from openagent.skills.registry import Skill, SkillRegistry


def _skill(name: str, desc: str = "", version: str = "1.0.0") -> Skill:
    return Skill(name=name, description=desc, version=version)


@pytest.fixture
def registry() -> SkillRegistry:
    reg = SkillRegistry()
    reg.register(_skill("flight-query", "query flights via MCP endpoint"))
    reg.register(_skill("flight-booking", "ticket booking state machine (13 states)"))
    reg.register(_skill("cs-base", "customer service base"))
    return reg


# ----- metadata_list -------------------------------------------------------


def test_metadata_list_returns_header_and_items(registry: SkillRegistry) -> None:
    out = registry.metadata_list()
    assert "Available skills" in out
    assert "read_skill" in out  # header mentions the tool
    assert "- flight-query" in out
    assert "MCP" in out  # part of the Chinese desc — robust to encoding issues
    assert "- flight-booking" in out
    assert "- cs-base" in out


def test_metadata_list_filters_to_requested_names(registry: SkillRegistry) -> None:
    out = registry.metadata_list(["flight-query"])
    assert "- flight-query" in out
    assert "- flight-booking" not in out
    assert "- cs-base" not in out


def test_metadata_list_marks_missing_skill(registry: SkillRegistry) -> None:
    out = registry.metadata_list(["nonexistent"])
    assert "- nonexistent" in out
    assert "(not in registry)" in out


def test_metadata_list_empty_when_no_names(registry: SkillRegistry) -> None:
    """空 registry / None 参数 → 空字符串 (caller 可据此跳过注入)."""
    assert registry.metadata_list([]) == ""
    assert SkillRegistry().metadata_list() == ""


def test_metadata_list_includes_version(registry: SkillRegistry) -> None:
    reg = SkillRegistry()
    reg.register(_skill("x", "test", version="2.5.0"))
    out = reg.metadata_list()
    assert "v2.5.0" in out
