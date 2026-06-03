"""Policy Engine 门面 — L5 Infrastructure Layer.

提供:
  - EffectivePolicy dataclass: 一次 chat 的最终生效策略
  - merge(config, request_override): 合并 scenario 配置 + 客户端 override
  - PolicyEngine: 统一入口, 校验 path / command / url 并写审计
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from openagent.policy.audit import AuditLogger
from openagent.policy.command_check import is_command_allowed
from openagent.policy.errors import (
    BudgetExceeded,
    CommandNotAllowed,
    NetworkNotAllowed,
    PathNotAllowed,
)
from openagent.policy.network_check import is_url_allowed
from openagent.policy.path_check import check_path, is_blocked

# 严格度排序: 数字越大越宽松
_TOOL_LEVEL_RANK: dict[str, int] = {"safe": 0, "standard": 1, "full": 2}
_NETWORK_RANK: dict[str, int] = {"off": 0, "local": 1, "any": 2}
_INTERSECT_FIELDS = frozenset({"workspace_dirs", "deny_dirs"})


@dataclass
class EffectivePolicy:
    """一次 chat 的最终生效策略 (immutable-by-convention)."""

    tool_level: Literal["safe", "standard", "full"] = "standard"
    workspace_dirs: list[str] = field(default_factory=list)
    readonly_dirs: list[str] = field(default_factory=list)
    deny_dirs: list[str] = field(default_factory=list)
    deny_path_patterns: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    denied_tools: list[str] = field(default_factory=list)
    allowed_commands: list[str] = field(default_factory=list)
    denied_commands: list[str] = field(default_factory=list)
    network: Literal["off", "local", "any"] = "local"
    max_turns: int = 30
    max_budget_usd: float = 5.0
    require_approval_for_writes: bool = True


def merge(
    config: EffectivePolicy,
    request_override: dict[str, Any] | None = None,
) -> EffectivePolicy:
    """把 request_override 叠加到 config 上.

    规则:
      - tool_level / network: 只能收紧不能放松 (override rank <= base rank).
      - workspace_dirs / deny_dirs: 取交集 (override 必须是 config 的子集).
      - 其他字段: override 提供则直接覆盖.
    """
    if not request_override:
        return replace(config)

    # 1) start with a copy of config
    out = replace(
        config,
        workspace_dirs=list(config.workspace_dirs),
        readonly_dirs=list(config.readonly_dirs),
        deny_dirs=list(config.deny_dirs),
        deny_path_patterns=list(config.deny_path_patterns),
        allowed_tools=list(config.allowed_tools),
        denied_tools=list(config.denied_tools),
        allowed_commands=list(config.allowed_commands),
        denied_commands=list(config.denied_commands),
    )

    for key, value in request_override.items():
        if not hasattr(out, key):
            continue  # 未知字段直接忽略
        if key == "tool_level":
            if _TOOL_LEVEL_RANK.get(value, 1) <= _TOOL_LEVEL_RANK.get(
                out.tool_level, 1
            ):
                out.tool_level = value  # type: ignore[assignment]
        elif key == "network":
            if _NETWORK_RANK.get(value, 0) <= _NETWORK_RANK.get(out.network, 0):
                out.network = value  # type: ignore[assignment]
        elif key in _INTERSECT_FIELDS:
            current = getattr(out, key)
            if isinstance(value, list):
                inter = [v for v in value if v in current]
                if inter:
                    setattr(out, key, inter)
        else:
            setattr(
                out,
                key,
                copy.copy(value) if isinstance(value, list) else value,
            )
    return out


class PolicyEngine:
    """统一的 policy 校验入口."""

    def __init__(
        self,
        policy: EffectivePolicy,
        audit: AuditLogger | None = None,
    ) -> None:
        self._policy = policy
        self._audit = audit

    @property
    def policy(self) -> EffectivePolicy:
        return self._policy

    def with_override(self, request_override: dict[str, Any] | None) -> PolicyEngine:
        """生成一个新的 PolicyEngine, 内部 policy 已 merge 过."""
        return PolicyEngine(policy=merge(self._policy, request_override), audit=self._audit)

    def _record(
        self,
        actor: str,
        action: str,
        target: str,
        result: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        if self._audit is None:
            return
        self._audit.record(actor, action, target, result, context)

    def check_path(self, path: str, *, actor: str = "agent") -> bool:
        """检查 path 是否被允许; 不允许时抛 PathNotAllowed."""
        allowed, reason = check_path(
            self._policy.workspace_dirs, self._policy.deny_dirs, path
        )
        if allowed:
            self._record(actor, "path_check", path, "allowed")
            return True
        self._record(
            actor, "path_check", path, "denied",
            {"reason": reason, "tool_level": self._policy.tool_level},
        )
        action = (
            "path matches BLOCKED_PATTERNS; cannot be whitelisted"
            if is_blocked(path) else None
        )
        raise PathNotAllowed(path, self._policy.workspace_dirs, action=action)

    def check_command(self, command: str, *, actor: str = "agent") -> bool:
        """检查 shell 命令是否被允许; 不允许时抛 CommandNotAllowed."""
        allowed, reason = is_command_allowed(
            command,
            self._policy.allowed_commands,
            self._policy.denied_commands,
            tool_level=self._policy.tool_level,
        )
        if allowed:
            self._record(actor, "command_check", command, "allowed")
            return True
        self._record(
            actor, "command_check", command, "denied",
            {"reason": reason, "tool_level": self._policy.tool_level},
        )
        raise CommandNotAllowed(command, denied_reason=reason)

    def check_url(self, url: str, *, actor: str = "agent") -> bool:
        """检查 URL 是否被网络策略允许; 不允许时抛 NetworkNotAllowed."""
        allowed, reason = is_url_allowed(url, self._policy.network)
        if allowed:
            self._record(actor, "network_check", url, "allowed")
            return True
        self._record(
            actor, "network_check", url, "denied",
            {"reason": reason, "network": self._policy.network},
        )
        raise NetworkNotAllowed(url, self._policy.network)

    def check_turn(self, used_turns: int) -> bool:
        """校验 turn 计数; 超出抛 BudgetExceeded."""
        if used_turns > self._policy.max_turns:
            raise BudgetExceeded("turns", used_turns, self._policy.max_turns)
        return True

    def check_budget(self, used_usd: float) -> bool:
        """校验 USD 预算; 超出抛 BudgetExceeded."""
        if used_usd > self._policy.max_budget_usd:
            raise BudgetExceeded("budget_usd", used_usd, self._policy.max_budget_usd)
        return True


__all__ = ["EffectivePolicy", "merge", "PolicyEngine"]
