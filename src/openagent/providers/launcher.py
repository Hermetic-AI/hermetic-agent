"""L4 Engine Launcher — scenario-aware engine starter.

Core guarantee: ``cwd`` is always ``scenario.workspace.workspace_dirs[0]``
(a project-relative path). The launcher refuses ``/``, ``~``, ``$HOME``,
empty strings, and unresolved ``${...}`` placeholders. ``opencode`` gets
a long-lived subprocess; ``claude_code`` is per-session (no prelaunch).
"""

from __future__ import annotations

import json
import os
import socket
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from subprocess import DEVNULL, PIPE, Popen, TimeoutExpired

from openagent.providers.base import AgentConfig, SDKType


class LauncherError(Exception):
    """Engine launcher failure (base class)."""


class LauncherRefusedRoot(LauncherError):  # noqa: N818 — spec-mandated name
    """``cwd`` is a forbidden root / home / empty path."""


@dataclass
class EngineHandle:
    """Generic engine handle returned by :meth:`EngineLauncher.launch`."""

    sdk_type: SDKType
    base_url: str
    cwd: str
    proc: Popen | None = None
    cli_path: str | None = None
    effective_policy: dict | None = None


@dataclass
class ClaudeCodeHandle(EngineHandle):
    """claude_code handle: no long-lived process, per-session subprocesses."""


class EngineLauncher:
    """Scenario-aware engine launcher. Refuses unsafe cwds; dispatches by SDK."""

    FORBIDDEN_CWDS: frozenset[str] = frozenset({
        "/",
        "~",
        os.path.expanduser("~"),
        os.path.expanduser("~/"),
        "",
    })

    def __init__(
        self,
        port_allocator: Callable[[], int] | None = None,
        config_dir: str | None = None,
    ) -> None:
        self._port_allocator = port_allocator or self._default_port_allocator
        self._config_dir = (
            Path(config_dir) if config_dir else Path("work/cache/opencode-configs")
        )

    def launch(
        self,
        scenario_workspace_dirs: list[str],
        agent_config: AgentConfig,
        scenario_security: dict | None = None,
    ) -> EngineHandle:
        """Spawn (or register) an engine. Raises LauncherError / LauncherRefusedRoot."""
        if not scenario_workspace_dirs:
            raise LauncherError(
                "scenario_workspace_dirs is empty. "
                "Set scenario.workspace.workspace_dirs to a non-empty list."
            )
        cwd = scenario_workspace_dirs[0]
        self._validate_cwd(cwd)
        resolved = Path(cwd).resolve()
        if not resolved.exists():
            raise LauncherError(
                f"Workspace {cwd!r} does not exist (resolved: {resolved}). "
                f"Create the directory or fix scenario.workspace.workspace_dirs[0]."
            )
        policy = scenario_security or {}
        if agent_config.sdk_type == "opencode":
            return self._launch_opencode(agent_config, str(resolved), policy)
        if agent_config.sdk_type == "claude_code":
            return self._launch_claude_code(agent_config, str(resolved), policy)
        raise LauncherError(f"Unknown sdk_type: {agent_config.sdk_type!r}")

    def _validate_cwd(self, cwd: str) -> None:
        if cwd in self.FORBIDDEN_CWDS:
            raise LauncherRefusedRoot(
                f"cwd {cwd!r} is forbidden. Engine MUST start in a project-relative "
                f"path. Set scenario.workspace.workspace_dirs[0] to a real project path."
            )
        if "${" in cwd and "}" in cwd:
            raise LauncherError(
                f"cwd {cwd!r} contains unresolved placeholder. "
                f"Run resolve_placeholders() before calling launch()."
            )

    def _launch_opencode(
        self, agent: AgentConfig, cwd: str, security: dict
    ) -> EngineHandle:
        port = self._port_allocator()
        config = self._render_opencode_config(security)
        config_path = self._write_temp_config(agent.name, config)
        proc = Popen(
            [
                "opencode", "serve",
                "--port", str(port),
                "--hostname", "127.0.0.1",
                "--cwd", cwd,
                "--config", config_path,
            ],
            cwd=cwd,
            stdout=DEVNULL,
            stderr=PIPE,
        )
        return EngineHandle(
            sdk_type="opencode",
            base_url=f"http://127.0.0.1:{port}",
            cwd=cwd,
            proc=proc,
            effective_policy=security,
        )

    def _launch_claude_code(
        self, agent: AgentConfig, cwd: str, security: dict
    ) -> ClaudeCodeHandle:
        cli_path = agent.base_url or "claude"
        return ClaudeCodeHandle(
            sdk_type="claude_code",
            base_url=cli_path,
            cwd=cwd,
            cli_path=cli_path,
            effective_policy=security,
        )

    def _render_opencode_config(self, security: dict) -> dict:
        """Map scenario security to an opencode config dict."""
        tool_level = security.get("tool_level", "standard")
        network = security.get("network", "local")
        return {
            "permission": {
                "edit": "deny" if tool_level == "safe" else "allow",
                "bash": "deny" if tool_level == "safe" else "ask",
                "webfetch": (
                    "deny" if network == "off"
                    else "allow" if network == "any"
                    else "ask"
                ),
            },
            "tools": {"Bash": tool_level != "safe"},
        }

    def _default_port_allocator(self) -> int:
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]
        finally:
            s.close()

    def _write_temp_config(self, agent_name: str, config: dict) -> str:
        self._config_dir.mkdir(parents=True, exist_ok=True)
        config_path = self._config_dir / f"{agent_name}.json"
        config_path.write_text(
            json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return str(config_path)

    def stop(self, handle: EngineHandle) -> None:
        """Terminate the engine subprocess if any. No-op for claude_code."""
        if handle.proc and handle.proc.poll() is None:
            handle.proc.terminate()
            try:
                handle.proc.wait(timeout=5)
            except TimeoutExpired:
                handle.proc.kill()


__all__ = [
    "LauncherError",
    "LauncherRefusedRoot",
    "EngineHandle",
    "ClaudeCodeHandle",
    "EngineLauncher",
]
