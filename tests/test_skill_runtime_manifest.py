"""tests/test_skill_runtime_manifest.py — SkillManifest 单元测试."""

from __future__ import annotations

from pathlib import Path

import pytest

from hermetic_agent.skills.runtime.errors import ManifestLoadError
from hermetic_agent.skills.runtime.manifest import SkillManifest, StateSpec


SAMPLE_YAML = """
name: book-flight
version: "1.2.0"
initial_state: S01
states:
  - id: S01
    description: 初始化
    allowed_tools: [ask_user, echo]
    timeout: 60
  - id: S02
    description: 询问城市日期
    allowed_tools: [ask_user, query_flight_basic]
    card: OD_INPUT
    timeout: 90
  - id: S05
    description: 航班选择
    allowed_tools: [ask_user, choose_flight]
    card: FLIGHT_LIST
transitions:
  S01: [S02, S05]
  S02: [S03, S04]
  S05: []
"""


def test_manifest_from_yaml(tmp_path: Path) -> None:
    p = tmp_path / "manifest.yaml"
    p.write_text(SAMPLE_YAML, encoding="utf-8")
    m = SkillManifest.from_yaml(p)
    assert m.name == "book-flight"
    assert m.version == "1.2.0"
    assert m.initial_state == "S01"
    assert set(m.states.keys()) == {"S01", "S02", "S05"}
    assert m.states["S01"].allowed_tools == ["ask_user", "echo"]
    assert m.states["S02"].card == "OD_INPUT"
    assert m.states["S02"].timeout == 90
    assert m.states["S05"].card == "FLIGHT_LIST"
    assert m.transitions["S01"] == {"S02", "S05"}
    assert m.transitions["S02"] == {"S03", "S04"}
    assert m.transitions["S05"] == set()


def test_manifest_from_yaml_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ManifestLoadError):
        SkillManifest.from_yaml(tmp_path / "no.yaml")


def test_manifest_from_yaml_invalid_top_level(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(ManifestLoadError):
        SkillManifest.from_yaml(p)


def test_manifest_from_yaml_invalid_yaml(tmp_path: Path) -> None:
    p = tmp_path / "broken.yaml"
    p.write_text("name: [unclosed\n", encoding="utf-8")
    with pytest.raises(ManifestLoadError):
        SkillManifest.from_yaml(p)


def test_manifest_from_yaml_missing_name(tmp_path: Path) -> None:
    p = tmp_path / "noname.yaml"
    p.write_text("version: '1.0.0'\nstates: []\n", encoding="utf-8")
    with pytest.raises(ManifestLoadError, match="name"):
        SkillManifest.from_yaml(p)


def test_manifest_from_yaml_initial_state_not_in_states(tmp_path: Path) -> None:
    p = tmp_path / "badinit.yaml"
    p.write_text(
        "name: x\ninitial_state: ZZ\nstates:\n  - id: S01\n    description: a\n",
        encoding="utf-8",
    )
    with pytest.raises(ManifestLoadError, match="initial_state"):
        SkillManifest.from_yaml(p)


def test_manifest_empty() -> None:
    m = SkillManifest.empty()
    assert m.name == "_empty"
    assert m.states == {}
    assert m.transitions == {}
    assert m.initial_state == "S01"
    assert m.state_ids() == []


def test_manifest_states_keys(tmp_path: Path) -> None:
    p = tmp_path / "manifest.yaml"
    p.write_text(SAMPLE_YAML, encoding="utf-8")
    m = SkillManifest.from_yaml(p)
    assert sorted(m.state_ids()) == ["S01", "S02", "S05"]


def test_manifest_to_yaml_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "manifest.yaml"
    p.write_text(SAMPLE_YAML, encoding="utf-8")
    m1 = SkillManifest.from_yaml(p)
    out = tmp_path / "out.yaml"
    m1.to_yaml(out)
    m2 = SkillManifest.from_yaml(out)
    assert m1.to_dict() == m2.to_dict()


def test_manifest_to_dict_shape() -> None:
    m = SkillManifest(
        name="t",
        states={"S01": StateSpec(description="init", allowed_tools=["ask_user"])},
        transitions={"S01": {"S02"}},
    )
    d = m.to_dict()
    assert d["name"] == "t"
    assert d["states"][0]["id"] == "S01"
    assert d["transitions"]["S01"] == ["S02"]


def test_manifest_from_dict() -> None:
    raw = {
        "name": "x",
        "initial_state": "A",
        "states": [
            {"id": "A", "description": "alpha"},
            {"id": "B", "description": "beta"},
        ],
        "transitions": {"A": ["B"]},
    }
    m = SkillManifest.from_dict(raw)
    assert m.states["A"].description == "alpha"
    assert m.transitions["A"] == {"B"}


def test_manifest_unknown_state_field(tmp_path: Path) -> None:
    p = tmp_path / "extra.yaml"
    p.write_text(
        "name: x\nstates:\n  - id: S01\n    description: a\n    bogus: 1\n",
        encoding="utf-8",
    )
    with pytest.raises(ManifestLoadError, match="unknown state field"):
        SkillManifest.from_yaml(p)


def test_manifest_transitions_must_be_list() -> None:
    raw = {
        "name": "x",
        "states": [{"id": "S01", "description": "a"}],
        "transitions": {"S01": 42},
    }
    with pytest.raises(ManifestLoadError, match="transitions"):
        SkillManifest.from_dict(raw)
