"""ScenarioRegistry 单测 — load / register / get / list / reload."""

from __future__ import annotations

from pathlib import Path

import pytest

from openagent.scenarios.config import (
    ExecutionConfig,
    ProgressiveSkillConfig,
    RoutingConfig,
    ScenarioConfig,
    WorkspaceConfig,
)
from openagent.scenarios.errors import ScenarioNotFoundError
from openagent.scenarios.registry import ScenarioRegistry


def _make_scenario(tmp_path: Path, name: str, priority: int = 100) -> Path:
    """在 tmp_path 下写一个 *.scenario.yaml 并返回路径."""
    p = tmp_path / f"{name}.scenario.yaml"
    p.write_text(
        f"""
name: {name}
version: "1.0.0"
routing: {{priority: {priority}, trigger_keywords: ["{name}"]}}
execution: {{orchestration: single, skills: [], tools: []}}
workspace: {{workspace_dirs: ["{tmp_path.as_posix()}"]}}
progressive_skill: {{strategy: none}}
""",
        encoding="utf-8",
    )
    return p


def _make_cfg(name: str) -> ScenarioConfig:
    return ScenarioConfig(
        name=name,
        version="1.0.0",
        routing=RoutingConfig(),
        execution=ExecutionConfig(),
        workspace=WorkspaceConfig(workspace_dirs=["/tmp/proj"]),
        progressive_skill=ProgressiveSkillConfig(strategy="none"),
    )


# ----------------------------------------------------------------------
# load_from_paths
# ----------------------------------------------------------------------


def test_load_from_paths_recursive(tmp_path: Path):
    _make_scenario(tmp_path, "alpha")
    sub = tmp_path / "sub"
    sub.mkdir()
    _make_scenario(sub, "beta")

    reg = ScenarioRegistry()
    loaded = reg.load_from_paths(tmp_path)
    names = {c.name for c in loaded}
    assert "alpha" in names
    assert "beta" in names


def test_load_from_paths_missing_dir(caplog):
    reg = ScenarioRegistry()
    loaded = reg.load_from_paths("/nope/nonexistent")
    assert loaded == []


def test_load_from_paths_skips_invalid(tmp_path: Path):
    _make_scenario(tmp_path, "ok")
    bad = tmp_path / "broken.scenario.yaml"
    bad.write_text("name: bad\nversion: '9.9.9'\n", encoding="utf-8")  # 缺 routing
    reg = ScenarioRegistry()
    loaded = reg.load_from_paths(tmp_path)
    assert "ok" in {c.name for c in loaded}
    assert "bad" not in {c.name for c in loaded}


def test_load_from_paths_single_file(tmp_path: Path):
    p = _make_scenario(tmp_path, "solo")
    reg = ScenarioRegistry()
    loaded = reg.load_from_paths(p)
    assert [c.name for c in loaded] == ["solo"]


# ----------------------------------------------------------------------
# load_from_dict
# ----------------------------------------------------------------------


def test_load_from_dict_basic():
    reg = ScenarioRegistry()
    cfg = _make_cfg("dict_one")
    cfg_dict = cfg.model_dump(mode="json")
    # 默认 security.denied_commands=[] 会被校验拒, 这里补齐
    cfg_dict["security"]["denied_commands"] = ["rm -rf", "sudo", "dd"]
    loaded = reg.load_from_dict([cfg_dict])
    assert len(loaded) == 1
    assert loaded[0].name == "dict_one"


def test_load_from_dict_skips_invalid():
    reg = ScenarioRegistry()
    loaded = reg.load_from_dict([{"name": "Invalid-Name"}])
    assert loaded == []


# ----------------------------------------------------------------------
# register / unregister / get
# ----------------------------------------------------------------------


def test_register_override():
    reg = ScenarioRegistry()
    reg.register(_make_cfg("a"))
    reg.register(_make_cfg("a"), override=True)
    assert reg.get("a") is not None
    assert len(reg.list_all()) == 1


def test_register_no_override_keeps_original():
    reg = ScenarioRegistry()
    reg.register(_make_cfg("a"))
    original = reg.get("a")
    reg.register(_make_cfg("a"), override=False)
    assert reg.get("a") is original


def test_get_returns_none_for_missing():
    reg = ScenarioRegistry()
    assert reg.get("nope") is None


def test_get_or_raise_raises():
    reg = ScenarioRegistry()
    with pytest.raises(ScenarioNotFoundError):
        reg.get_or_raise("nope")


def test_unregister_returns_bool():
    reg = ScenarioRegistry()
    reg.register(_make_cfg("a"))
    assert reg.unregister("a") is True
    assert reg.unregister("a") is False


# ----------------------------------------------------------------------
# list
# ----------------------------------------------------------------------


def test_list_all_sorted():
    reg = ScenarioRegistry()
    reg.register(_make_cfg("z"))
    reg.register(_make_cfg("a"))
    reg.register(_make_cfg("m"))
    assert [c.name for c in reg.list_all()] == ["a", "m", "z"]


def test_list_enabled_filters_disabled():
    reg = ScenarioRegistry()
    enabled = _make_cfg("on")
    disabled = _make_cfg("off")
    disabled.enabled = False
    reg.register(enabled)
    reg.register(disabled)
    names = [c.name for c in reg.list_enabled()]
    assert names == ["on"]


def test_list_names_sorted():
    reg = ScenarioRegistry()
    reg.register(_make_cfg("b"))
    reg.register(_make_cfg("a"))
    assert reg.list_names() == ["a", "b"]


# ----------------------------------------------------------------------
# reload
# ----------------------------------------------------------------------


def test_reload_clears_and_reloads(tmp_path: Path):
    _make_scenario(tmp_path, "first")
    reg = ScenarioRegistry()
    reg.load_from_paths(tmp_path)
    assert "first" in reg.list_names()

    # 加新文件 + 改原文件 + reload
    _make_scenario(tmp_path, "second")
    reg.reload(tmp_path)
    names = set(reg.list_names())
    assert {"first", "second"}.issubset(names)


# ----------------------------------------------------------------------
# load_from_db (stub)
# ----------------------------------------------------------------------


def test_load_from_db_stub():
    reg = ScenarioRegistry()
    result = reg.load_from_db([{"name": "x", "version": "1.0.0"}])
    assert result == []
