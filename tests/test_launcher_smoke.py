"""Smoke tests for EngineLauncher — 5 most critical scenarios.

Keep this file tiny and dependency-free: it documents the 5 must-pass
behaviours (refuse / accept / opencode / claude / stop) and acts as a
fast gate before the comprehensive suite in ``test_launcher.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from openagent.providers.base import AgentConfig
from openagent.providers.launcher import (
    ClaudeCodeHandle,
    EngineHandle,
    EngineLauncher,
    LauncherError,
    LauncherRefusedRoot,
)


def test_smoke_refuse_root(tmp_path: Path) -> None:
    """Launching at '/' must raise LauncherRefusedRoot."""
    launcher = EngineLauncher(port_allocator=lambda: 4096, config_dir=str(tmp_path))
    agent = AgentConfig(name="x", base_url="http://x", sdk_type="opencode")

    with pytest.raises(LauncherRefusedRoot):
        launcher.launch(["/"], agent)


def test_smoke_accept_real_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A real project-relative workspace is accepted and handle is sane."""
    ws = tmp_path / "proj"
    ws.mkdir()

    monkeypatch.setattr("openagent.providers.launcher.Popen", lambda *a, **kw: MagicMock())

    launcher = EngineLauncher(port_allocator=lambda: 4097, config_dir=str(tmp_path / "c"))
    agent = AgentConfig(name="x", base_url="http://x", sdk_type="opencode")

    handle = launcher.launch([str(ws)], agent, {"tool_level": "standard", "network": "local"})

    assert handle.sdk_type == "opencode"
    assert handle.base_url == "http://127.0.0.1:4097"
    assert handle.cwd == str(ws.resolve())
    assert handle.proc is not None
    launcher.stop(handle)


def test_smoke_opencode_args_and_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """opencode launch wires --cwd into the subprocess AND writes config JSON."""
    ws = tmp_path / "proj"
    ws.mkdir()
    cfg_dir = tmp_path / "configs"
    cfg_dir.mkdir()

    captured: dict = {}

    def fake_popen(args, **kwargs):  # type: ignore[no-untyped-def]
        captured["args"] = args
        captured["kwargs"] = kwargs
        m = MagicMock()
        m.poll = MagicMock(return_value=None)
        return m

    monkeypatch.setattr("openagent.providers.launcher.Popen", fake_popen)

    launcher = EngineLauncher(port_allocator=lambda: 4098, config_dir=str(cfg_dir))
    agent = AgentConfig(name="y", base_url="http://y", sdk_type="opencode")
    launcher.launch(
        [str(ws)], agent, {"tool_level": "safe", "network": "off"}
    )

    # --cwd in args + Popen.cwd kwarg matches the resolved workspace
    assert "--cwd" in captured["args"]
    assert captured["kwargs"]["cwd"] == str(ws.resolve())

    # Config file written with safe-level permissions
    cfg_file = cfg_dir / "y.json"
    assert cfg_file.exists()
    cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert cfg["permission"]["edit"] == "deny"
    assert cfg["permission"]["bash"] == "deny"
    assert cfg["tools"]["Bash"] is False


def test_smoke_claude_code(tmp_path: Path) -> None:
    """claude_code returns a ClaudeCodeHandle and spawns no process."""
    ws = tmp_path / "proj"
    ws.mkdir()

    launcher = EngineLauncher(port_allocator=lambda: 4099, config_dir=str(tmp_path / "c"))
    agent = AgentConfig(name="z", base_url="/usr/bin/claude", sdk_type="claude_code")
    handle = launcher.launch([str(ws)], agent, {"tool_level": "standard"})

    assert isinstance(handle, ClaudeCodeHandle)
    assert handle.cli_path == "/usr/bin/claude"
    assert handle.proc is None
    assert handle.cwd == str(ws.resolve())


def test_smoke_stop_terminates(tmp_path: Path) -> None:
    """stop() terminates an alive proc, no-ops on a dead/none proc."""
    launcher = EngineLauncher(port_allocator=lambda: 4100, config_dir=str(tmp_path))

    # alive proc: terminate + wait
    alive = EngineHandle(sdk_type="opencode", base_url="x", cwd="x")
    alive.proc = MagicMock()
    alive.proc.poll = MagicMock(return_value=None)
    launcher.stop(alive)
    alive.proc.terminate.assert_called_once()
    alive.proc.wait.assert_called_once()

    # dead proc: no-op
    dead = EngineHandle(sdk_type="opencode", base_url="x", cwd="x")
    dead.proc = MagicMock()
    dead.proc.poll = MagicMock(return_value=0)
    launcher.stop(dead)
    dead.proc.terminate.assert_not_called()

    # no proc: no-op
    empty = EngineHandle(sdk_type="claude_code", base_url="x", cwd="x")
    assert empty.proc is None
    launcher.stop(empty)  # must not raise
