"""Tests for EngineLauncher (L4 Providers)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from hermetic_agent.providers.base import AgentConfig
from hermetic_agent.providers.launcher import (
    ClaudeCodeHandle,
    EngineHandle,
    EngineLauncher,
    LauncherError,
    LauncherRefusedRoot,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace(tmp_path: Path) -> str:
    """A real, existing project-relative workspace directory."""
    d = tmp_path / "project"
    d.mkdir()
    return str(d)


@pytest.fixture
def config_dir(tmp_path: Path) -> str:
    """An isolated config dir used by the launcher to write opencode config."""
    d = tmp_path / "configs"
    d.mkdir()
    return str(d)


@pytest.fixture
def launcher(config_dir: str) -> EngineLauncher:
    """Launcher with deterministic port allocator + isolated config dir."""
    return EngineLauncher(port_allocator=lambda: 12345, config_dir=config_dir)


@pytest.fixture
def opencode_agent() -> AgentConfig:
    return AgentConfig(
        name="test-agent",
        base_url="http://127.0.0.1:4096",
        sdk_type="opencode",
    )


@pytest.fixture
def claude_agent() -> AgentConfig:
    return AgentConfig(
        name="claude-agent",
        base_url="/usr/local/bin/claude",
        sdk_type="claude_code",
    )


@pytest.fixture
def mock_popen(monkeypatch: pytest.MonkeyPatch):
    """Replace Popen with a MagicMock factory; return a dict for assertions."""
    captured: dict = {}

    def _factory(args, **kwargs):  # type: ignore[no-untyped-def]
        captured["args"] = args
        captured["kwargs"] = kwargs
        m = MagicMock()
        m.poll = MagicMock(return_value=None)
        return m

    monkeypatch.setattr("hermetic_agent.providers.launcher.Popen", _factory)
    return captured


# ---------------------------------------------------------------------------
# cwd refusal
# ---------------------------------------------------------------------------


class TestCwdRefusal:
    def test_refuses_root_cwd(
        self, launcher: EngineLauncher, opencode_agent: AgentConfig
    ) -> None:
        with pytest.raises(LauncherRefusedRoot) as exc:
            launcher.launch(["/"], opencode_agent)
        assert "/" in str(exc.value)

    def test_refuses_tilde_cwd(
        self, launcher: EngineLauncher, opencode_agent: AgentConfig
    ) -> None:
        with pytest.raises(LauncherRefusedRoot) as exc:
            launcher.launch(["~"], opencode_agent)
        assert "~" in str(exc.value)

    def test_refuses_empty_cwd(
        self, launcher: EngineLauncher, opencode_agent: AgentConfig
    ) -> None:
        with pytest.raises(LauncherRefusedRoot):
            launcher.launch([""], opencode_agent)

    def test_refuses_unresolved_placeholder(
        self, launcher: EngineLauncher, opencode_agent: AgentConfig
    ) -> None:
        with pytest.raises(LauncherError) as exc:
            launcher.launch(["${PROJECT_DIR}"], opencode_agent)
        assert "placeholder" in str(exc.value).lower()

    def test_refuses_nonexistent_workspace(
        self, launcher: EngineLauncher, opencode_agent: AgentConfig
    ) -> None:
        with pytest.raises(LauncherError) as exc:
            launcher.launch(["/this/path/__definitely_does_not_exist__"], opencode_agent)
        assert "does not exist" in str(exc.value).lower()

    def test_rejects_empty_workspace_dirs(
        self, launcher: EngineLauncher, opencode_agent: AgentConfig
    ) -> None:
        with pytest.raises(LauncherError) as exc:
            launcher.launch([], opencode_agent)
        assert "empty" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# opencode launch
# ---------------------------------------------------------------------------


class TestOpencodeLaunch:
    def test_uses_correct_cwd(
        self,
        launcher: EngineLauncher,
        opencode_agent: AgentConfig,
        workspace: str,
        mock_popen: dict,
    ) -> None:
        handle = launcher.launch([workspace], opencode_agent, {"tool_level": "standard"})

        assert isinstance(handle, EngineHandle)
        assert handle.sdk_type == "opencode"
        assert handle.proc is not None
        # Popen.cwd kwarg should be the resolved workspace
        assert mock_popen["kwargs"]["cwd"] == str(Path(workspace).resolve())
        # --cwd should appear in args list along with the resolved path
        assert "--cwd" in mock_popen["args"]
        assert str(Path(workspace).resolve()) in mock_popen["args"]
        # Port from allocator should be present
        assert "12345" in mock_popen["args"]
        # base_url reflects allocator
        assert handle.base_url == "http://127.0.0.1:12345"

    def test_config_renders_safe_level(
        self,
        launcher: EngineLauncher,
        opencode_agent: AgentConfig,
        workspace: str,
        config_dir: str,
        mock_popen: dict,
    ) -> None:
        launcher.launch(
            [workspace], opencode_agent, {"tool_level": "safe", "network": "off"}
        )

        cfg_path = Path(config_dir) / "test-agent.json"
        assert cfg_path.exists()
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert cfg["permission"]["edit"] == "deny"
        assert cfg["permission"]["bash"] == "deny"
        assert cfg["permission"]["webfetch"] == "deny"
        assert cfg["tools"]["Bash"] is False

    def test_config_renders_standard_level(
        self,
        launcher: EngineLauncher,
        opencode_agent: AgentConfig,
        workspace: str,
        config_dir: str,
        mock_popen: dict,
    ) -> None:
        launcher.launch(
            [workspace], opencode_agent, {"tool_level": "standard", "network": "any"}
        )

        cfg_path = Path(config_dir) / "test-agent.json"
        assert cfg_path.exists()
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert cfg["permission"]["edit"] == "allow"
        assert cfg["permission"]["bash"] == "ask"
        assert cfg["permission"]["webfetch"] == "allow"
        assert cfg["tools"]["Bash"] is True

    def test_config_renders_full_level(
        self,
        launcher: EngineLauncher,
        opencode_agent: AgentConfig,
        workspace: str,
        config_dir: str,
        mock_popen: dict,
    ) -> None:
        launcher.launch(
            [workspace], opencode_agent, {"tool_level": "full", "network": "any"}
        )

        cfg_path = Path(config_dir) / "test-agent.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert cfg["permission"]["edit"] == "allow"
        assert cfg["permission"]["bash"] == "ask"
        assert cfg["permission"]["webfetch"] == "allow"

    def test_config_renders_local_network(
        self,
        launcher: EngineLauncher,
        opencode_agent: AgentConfig,
        workspace: str,
        config_dir: str,
        mock_popen: dict,
    ) -> None:
        launcher.launch(
            [workspace], opencode_agent, {"tool_level": "standard", "network": "local"}
        )

        cfg = json.loads((Path(config_dir) / "test-agent.json").read_text())
        assert cfg["permission"]["webfetch"] == "ask"

    def test_config_defaults_when_security_empty(
        self,
        launcher: EngineLauncher,
        opencode_agent: AgentConfig,
        workspace: str,
        config_dir: str,
        mock_popen: dict,
    ) -> None:
        launcher.launch([workspace], opencode_agent)  # no security

        cfg = json.loads((Path(config_dir) / "test-agent.json").read_text())
        # defaults: standard + local
        assert cfg["permission"]["edit"] == "allow"
        assert cfg["permission"]["bash"] == "ask"
        assert cfg["permission"]["webfetch"] == "ask"

    def test_handle_effective_policy_is_propagated(
        self,
        launcher: EngineLauncher,
        opencode_agent: AgentConfig,
        workspace: str,
        mock_popen: dict,
    ) -> None:
        policy = {"tool_level": "safe", "network": "off", "max_turns": 5}
        handle = launcher.launch([workspace], opencode_agent, policy)
        assert handle.effective_policy == policy


# ---------------------------------------------------------------------------
# claude_code launch
# ---------------------------------------------------------------------------


class TestClaudeCodeLaunch:
    def test_returns_handle(
        self,
        launcher: EngineLauncher,
        claude_agent: AgentConfig,
        workspace: str,
    ) -> None:
        handle = launcher.launch([workspace], claude_agent, {"tool_level": "standard"})

        assert isinstance(handle, ClaudeCodeHandle)
        assert handle.sdk_type == "claude_code"
        assert handle.cwd == str(Path(workspace).resolve())
        assert handle.cli_path == "/usr/local/bin/claude"
        assert handle.proc is None
        assert handle.effective_policy == {"tool_level": "standard"}

    def test_falls_back_to_claude_default(
        self,
        launcher: EngineLauncher,
        workspace: str,
    ) -> None:
        agent = AgentConfig(name="x", base_url="", sdk_type="claude_code")
        handle = launcher.launch([workspace], agent, None)
        assert handle.cli_path == "claude"
        assert handle.base_url == "claude"

    def test_does_not_spawn_proc(
        self,
        launcher: EngineLauncher,
        claude_agent: AgentConfig,
        workspace: str,
        mock_popen: dict,
    ) -> None:
        # Even with Popen patched, claude_code must NOT call Popen
        launcher.launch([workspace], claude_agent, {"tool_level": "standard"})
        assert "args" not in mock_popen  # Popen factory never invoked


# ---------------------------------------------------------------------------
# Unknown SDK type
# ---------------------------------------------------------------------------


class TestUnknownSdk:
    def test_unknown_sdk_type_raises(
        self,
        launcher: EngineLauncher,
        opencode_agent: AgentConfig,
        workspace: str,
    ) -> None:
        # bypass the Literal type-check by reassigning the field
        opencode_agent.sdk_type = "totally_unknown_sdk"  # type: ignore[assignment]
        with pytest.raises(LauncherError) as exc:
            launcher.launch([workspace], opencode_agent)
        assert "Unknown sdk_type" in str(exc.value)


# ---------------------------------------------------------------------------
# stop()
# ---------------------------------------------------------------------------


class TestStop:
    def test_terminates_alive_proc(self, launcher: EngineLauncher) -> None:
        handle = EngineHandle(sdk_type="opencode", base_url="x", cwd="x")
        handle.proc = MagicMock()
        handle.proc.poll = MagicMock(return_value=None)  # alive

        launcher.stop(handle)

        handle.proc.terminate.assert_called_once()
        handle.proc.wait.assert_called_once()

    def test_skips_dead_proc(self, launcher: EngineLauncher) -> None:
        handle = EngineHandle(sdk_type="opencode", base_url="x", cwd="x")
        handle.proc = MagicMock()
        handle.proc.poll = MagicMock(return_value=0)  # already dead

        launcher.stop(handle)

        handle.proc.terminate.assert_not_called()
        handle.proc.wait.assert_not_called()

    def test_handles_no_proc(self, launcher: EngineLauncher) -> None:
        handle = EngineHandle(sdk_type="claude_code", base_url="x", cwd="x")
        assert handle.proc is None
        launcher.stop(handle)  # must not raise

    def test_kills_on_timeout(self, launcher: EngineLauncher) -> None:
        from subprocess import TimeoutExpired

        handle = EngineHandle(sdk_type="opencode", base_url="x", cwd="x")
        handle.proc = MagicMock()
        handle.proc.poll = MagicMock(return_value=None)
        handle.proc.wait = MagicMock(side_effect=TimeoutExpired(cmd="x", timeout=5))

        launcher.stop(handle)

        handle.proc.terminate.assert_called_once()
        handle.proc.kill.assert_called_once()


# ---------------------------------------------------------------------------
# Handle dataclasses
# ---------------------------------------------------------------------------


class TestHandleDataclasses:
    def test_engine_handle_defaults(self) -> None:
        h = EngineHandle(sdk_type="opencode", base_url="http://x", cwd="/x")
        assert h.proc is None
        assert h.cli_path is None
        assert h.effective_policy is None

    def test_claude_code_handle_inherits(self) -> None:
        h = ClaudeCodeHandle(sdk_type="claude_code", base_url="claude", cwd="/x")
        assert isinstance(h, EngineHandle)
        assert h.sdk_type == "claude_code"


# ---------------------------------------------------------------------------
# Forbidden cwd matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "forbidden",
    ["/", "~", "", "/root", "/home"],
)
def test_forbidden_cwd_matrix(
    forbidden: str, launcher: EngineLauncher, opencode_agent: AgentConfig
) -> None:
    """Slash variants and home-related paths are always rejected."""
    with pytest.raises((LauncherRefusedRoot, LauncherError)):
        launcher.launch([forbidden], opencode_agent)
