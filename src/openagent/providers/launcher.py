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

    # 历史硬编码的 forbidden cwd 集. 现在从 settings.launcher_forbidden_cwds 读.
    # 保留这个 frozenset 作为**兜底** (settings 不可用 / 单测场景).
    # 注意: os.path.expanduser("~") 已在 settings 装载时算成实际 HOME, 这里保持
    # 字面量避免对环境产生副作用.
    FORBIDDEN_CWDS_FALLBACK: frozenset[str] = frozenset({
        "/",
        "~",
        "",
    })

    def _forbidden_cwds(self) -> frozenset[str]:
        try:
            from openagent.config.settings import get_settings
            return frozenset(get_settings().launcher_forbidden_cwds)
        except Exception:  # pragma: no cover
            return self.FORBIDDEN_CWDS_FALLBACK

    # 向后兼容 (老代码 ``EngineLauncher.FORBIDDEN_CWDS`` 仍可用, 但仅作为
    # 兜底值, 真正校验走 ``_forbidden_cwds()``).
    FORBIDDEN_CWDS: frozenset[str] = FORBIDDEN_CWDS_FALLBACK

    def __init__(
        self,
        port_allocator: Callable[[], int] | None = None,
        config_dir: str | None = None,
    ) -> None:
        self._port_allocator = port_allocator or self._default_port_allocator
        if config_dir is not None:
            self._config_dir = Path(config_dir)
        else:
            try:
                from openagent.config.settings import get_settings
                self._config_dir = Path(get_settings().launcher_config_dir)
            except Exception:  # pragma: no cover
                self._config_dir = Path("work/cache/opencode-configs")

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
        forbidden = self._forbidden_cwds()
        # 同时检查展开 ~ 之后的绝对路径 (settings 里给的是字面量, 运行时也匹配)
        expanded = os.path.expanduser(cwd) if cwd else cwd
        if cwd in forbidden or expanded in forbidden:
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
        try:
            from openagent.config.settings import get_settings
            hostname = get_settings().launcher_opencode_hostname
        except Exception:  # pragma: no cover
            hostname = "127.0.0.1"
        proc = Popen(
            [
                "opencode", "serve",
                "--port", str(port),
                "--hostname", hostname,
                "--cwd", cwd,
                "--config", config_path,
            ],
            cwd=cwd,
            stdout=DEVNULL,
            stderr=PIPE,
        )
        return EngineHandle(
            sdk_type="opencode",
            base_url=f"http://{hostname}:{port}",
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
        """Map scenario security to an opencode config dict.

        tool_level / network 默认值从 settings 读
        (launcher_default_tool_level / launcher_default_network).
        """
        try:
            from openagent.config.settings import get_settings
            s = get_settings()
            default_tool_level = s.launcher_default_tool_level
            default_network = s.launcher_default_network
        except Exception:  # pragma: no cover
            default_tool_level = "standard"
            default_network = "local"
        tool_level = security.get("tool_level", default_tool_level)
        network = security.get("network", default_network)
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
                grace = 5.0
                try:
                    from openagent.config.settings import get_settings
                    grace = float(get_settings().launcher_stop_grace_seconds)
                except Exception:  # pragma: no cover
                    pass
                handle.proc.wait(timeout=grace)
            except TimeoutExpired:
                handle.proc.kill()


__all__ = [
    "LauncherError",
    "LauncherRefusedRoot",
    "EngineHandle",
    "ClaudeCodeHandle",
    "EngineLauncher",
]
