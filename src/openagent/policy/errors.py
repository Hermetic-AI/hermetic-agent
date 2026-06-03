"""Policy 异常层级 — L5 Infrastructure Layer.

所有 Policy 相关的异常都从 PolicyError 派生；带可行动信息（action）字段，
方便上层（API/MCP）转成 HTTP 响应时直接放到 detail 里。
"""

from __future__ import annotations


class PolicyError(Exception):
    """Policy 异常的基类.

    通用场景: 配置错、状态不一致、内部 bug.
    """

    def __init__(self, message: str, *, action: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.action = action or "Check policy configuration"

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        if self.action:
            return f"{self.message} | Action: {self.action}"
        return self.message


class PolicyViolation(PolicyError):  # noqa: N818 - "Violation" suffix is allowed per AGENTS.md
    """通用策略违规.

    子类 PathNotAllowed / CommandNotAllowed / NetworkNotAllowed / BudgetExceeded
    都是具体的违规类型。
    """


class PathNotAllowed(PolicyViolation):
    """路径不被当前 policy 允许."""

    def __init__(
        self,
        path: str,
        workspace_dirs: list[str] | None = None,
        *,
        action: str | None = None,
    ) -> None:
        ws = workspace_dirs or []
        msg = f"Path {path!r} is not allowed by current policy"
        if ws:
            msg += f". workspace_dirs={ws}"
        default_action = (
            f"Set workspace_dirs to include the path's parent, "
            f"or remove the access from scenario config. "
            f"Allowed workspaces: {ws or '[]'}."
        )
        super().__init__(msg, action=action or default_action)
        self.path = path
        self.workspace_dirs = ws


class CommandNotAllowed(PolicyViolation):
    """命令不被当前 policy 允许."""

    def __init__(
        self,
        command: str,
        denied_reason: str = "blocked",
        *,
        action: str | None = None,
    ) -> None:
        msg = f"Command {command!r} is not allowed: {denied_reason}"
        default_action = (
            "Remove the command, or add it to allowed_commands in scenario security config."
        )
        super().__init__(msg, action=action or default_action)
        self.command = command
        self.denied_reason = denied_reason


class NetworkNotAllowed(PolicyViolation):
    """网络请求不被当前 policy 允许."""

    def __init__(
        self,
        url: str,
        network_level: str = "off",
        *,
        action: str | None = None,
    ) -> None:
        msg = f"Network request to {url!r} is not allowed (network={network_level})"
        default_action = (
            f"network={network_level} blocks this URL. "
            f"Use 'local' for private IPs, or 'any' for unrestricted access. "
            f"Change in scenario.security.network."
        )
        super().__init__(msg, action=action or default_action)
        self.url = url
        self.network_level = network_level


class BudgetExceeded(PolicyViolation):
    """turn / budget 超过限制."""

    def __init__(
        self,
        kind: str,
        used: float | int,
        limit: float | int,
        *,
        action: str | None = None,
    ) -> None:
        msg = f"Policy budget exceeded: {kind} used={used} > limit={limit}"
        default_action = (
            f"Raise the {kind} limit in scenario.security, "
            f"or reduce the work (fewer turns, lower cost)."
        )
        super().__init__(msg, action=action or default_action)
        self.kind = kind
        self.used = used
        self.limit = limit


__all__ = [
    "PolicyError",
    "PolicyViolation",
    "PathNotAllowed",
    "CommandNotAllowed",
    "NetworkNotAllowed",
    "BudgetExceeded",
]
