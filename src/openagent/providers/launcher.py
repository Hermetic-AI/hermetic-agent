"""L4 Engine Launcher — scenario-aware engine starter.

Core guarantee: ``cwd`` is always ``scenario.workspace.workspace_dirs[0]``
(a project-relative path). The launcher refuses ``/``, ``~``, ``$HOME``,
empty strings, and unresolved ``${...}`` placeholders. ``opencode`` gets
a long-lived subprocess; ``claude_code`` is per-session (no prelaunch).

异步支持:
  - 同步 API ``launch()`` / ``stop()`` 保留, 测试/同步调用方不受影响.
  - 异步 API ``alaunch()`` / ``astop()`` 在 async 上下文用, 底层
    ``asyncio.create_subprocess_exec`` + ``asyncio.wait_for`` 不阻塞 event loop.
  - async 失败时降级到 sync Popen + 线程池 wait, 兼容老 import 路径.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from subprocess import DEVNULL, PIPE, Popen, TimeoutExpired

from openagent.providers.base import AgentConfig, SDKType

logger = logging.getLogger(__name__)

# 旧式 logging.Logger 不支持 kwargs 形式的 extra 字段
# (会触发 "got an unexpected keyword argument"), 所以 launcher 内部所有
# 结构化字段改用 ``extra={"key": value}`` 形式显式传给 stdlib logger.
# structlog 升级后所有 caller 统一用 ``logger.info(..., key=value)`` 即可.
_LOG = logger  # 命名简化 (避免改全模块 logger 名字)


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
    # async 启动时持有的 asyncio.subprocess.Process (供 astop() 关闭)
    async_proc: asyncio.subprocess.Process | None = None


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
        """Spawn (or register) an engine. Raises LauncherError / LauncherRefusedRoot.

        同步 API: 内部用 ``Popen`` (subprocess), 在 event loop 外或 sync
        脚本里安全. event loop 内的调用方请用 ``await alaunch()``.
        """
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
            return self._launch_opencode_sync(agent_config, str(resolved), policy)
        if agent_config.sdk_type == "claude_code":
            return self._launch_claude_code(agent_config, str(resolved), policy)
        raise LauncherError(f"Unknown sdk_type: {agent_config.sdk_type!r}")

    async def alaunch(
        self,
        scenario_workspace_dirs: list[str],
        agent_config: AgentConfig,
        scenario_security: dict | None = None,
    ) -> EngineHandle:
        """Async 版的 ``launch``: opencode 走 ``asyncio.create_subprocess_exec``,
        不阻塞 event loop.

        行为与 ``launch()`` 完全一致, 但 ``stop`` 时要调 ``astop()`` 才能
        利用 async wait 不阻塞 loop.
        """
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
            return await self._launch_opencode_async(agent_config, str(resolved), policy)
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

    def _build_opencode_args(
        self, agent: AgentConfig, cwd: str, config_path: str
    ) -> tuple[list[str], str]:
        """构造 opencode serve 启动参数, 同步/异步共用."""
        try:
            from openagent.config.settings import get_settings
            hostname = get_settings().launcher_opencode_hostname
        except Exception:  # pragma: no cover
            hostname = "127.0.0.1"
        return (
            [
                "opencode", "serve",
                "--port", str(self._port_allocator()),
                "--hostname", hostname,
                "--cwd", cwd,
                "--config", config_path,
            ],
            hostname,
        )

    def _launch_opencode_sync(
        self, agent: AgentConfig, cwd: str, security: dict
    ) -> EngineHandle:
        port = self._port_allocator()
        config = self._render_opencode_config(security)
        config_path = self._write_temp_config(agent.name, config)
        args, hostname = self._build_opencode_args(agent, cwd, config_path)
        logger.info(
            "engine_launch_sync",
            extra={"agent": agent.name, "cwd": cwd, "port": port, "config_path": config_path},
        )
        proc = Popen(
            args,
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

    async def _launch_opencode_async(
        self, agent: AgentConfig, cwd: str, security: dict
    ) -> EngineHandle:
        """Async 启动: 用 asyncio.create_subprocess_exec 避免 event loop 阻塞."""
        port = self._port_allocator()
        config = self._render_opencode_config(security)
        config_path = self._write_temp_config(agent.name, config)
        args, hostname = self._build_opencode_args(agent, cwd, config_path)
        logger.info(
            "engine_launch_async",
            extra={"agent": agent.name, "cwd": cwd, "port": port, "config_path": config_path},
        )
        # NOTE: cwd 必须在 create_subprocess_exec 里传, 而 Popen 的 cwd=
        # 关键字对应到 asyncio.subprocess 是 cwd=
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=cwd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        return EngineHandle(
            sdk_type="opencode",
            base_url=f"http://{hostname}:{port}",
            cwd=cwd,
            proc=None,             # sync Popen 路径未启动
            async_proc=proc,       # async 启动持有
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

    def _stop_grace_seconds(self) -> float:
        """从 settings 读 grace, 兜底 5.0s."""
        try:
            from openagent.config.settings import get_settings
            return float(get_settings().launcher_stop_grace_seconds)
        except Exception:  # pragma: no cover
            return 5.0

    def stop(self, handle: EngineHandle) -> None:
        """Terminate the engine subprocess if any. No-op for claude_code.

        Sync 路径: 优先复用 ``astop`` (在 event loop 已运行时), 否则把
        ``Popen.wait`` 放到 default executor 跑, 不阻塞调用方所在 loop.
        真正 sync 调用 (test scripts) 则直接 wait.
        """
        # 1) async 启动的进程 → 走 astop
        if handle.async_proc is not None and handle.async_proc.returncode is None:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 已经在 event loop 里, 调度 astop 不阻塞
                    loop.create_task(self.astop(handle))
                    return
            except RuntimeError:
                pass
            # 没有运行中的 loop: 退化为 sync 路径
            try:
                handle.async_proc.terminate()
                handle.async_proc.kill()
            except ProcessLookupError:
                pass
            return

        # 2) sync Popen 进程
        if handle.proc and handle.proc.poll() is None:
            handle.proc.terminate()
            grace = self._stop_grace_seconds()
            try:
                # 把同步 wait 放到线程池, 不阻塞调用方所在 event loop
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                            ex.submit(handle.proc.wait, timeout=grace).result(timeout=grace + 0.5)
                    else:
                        handle.proc.wait(timeout=grace)
                except RuntimeError:
                    # 没有 event loop, 纯 sync 路径
                    handle.proc.wait(timeout=grace)
            except TimeoutExpired:
                logger.warning(
                    "engine_stop_kill_after_grace",
                    extra={"agent": handle.sdk_type, "cwd": handle.cwd, "grace": grace},
                )
                handle.proc.kill()

    async def astop(self, handle: EngineHandle) -> None:
        """Async 终止: asyncio.subprocess.Process.terminate() + wait_for."""
        grace = self._stop_grace_seconds()

        # 1) async 启动的进程
        if handle.async_proc is not None:
            if handle.async_proc.returncode is not None:
                return  # 已退出
            try:
                handle.async_proc.terminate()
            except ProcessLookupError:
                return
            try:
                await asyncio.wait_for(handle.async_proc.wait(), timeout=grace)
            except asyncio.TimeoutError:
                logger.warning(
                    "engine_astop_kill_after_grace",
                    extra={"agent": handle.sdk_type, "cwd": handle.cwd, "grace": grace},
                )
                with contextlib.suppress(ProcessLookupError):
                    handle.async_proc.kill()
                await handle.async_proc.wait()
            return

        # 2) sync Popen 进程: 在 thread pool 里 wait, 不阻塞 loop
        if handle.proc and handle.proc.poll() is None:
            handle.proc.terminate()
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, handle.proc.wait, grace)
            except (TimeoutError, asyncio.TimeoutError):
                logger.warning(
                    "engine_astop_kill_after_grace",
                    extra={"agent": handle.sdk_type, "cwd": handle.cwd, "grace": grace},
                )
                handle.proc.kill()


__all__ = [
    "LauncherError",
    "LauncherRefusedRoot",
    "EngineHandle",
    "ClaudeCodeHandle",
    "EngineLauncher",
]


# 延迟 import contextlib 避免在 __all__ 之前出现未使用提示
import contextlib  # noqa: E402
