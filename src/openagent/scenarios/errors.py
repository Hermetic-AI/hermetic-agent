"""Scenarios 异常层级 — L2 Scenario Orchestration Layer.

所有异常从 ScenarioError 派生; 带可行动信息 (action) 和 code 字段.
code 取自设计文档 §10 的 12 个错误码.
"""

from __future__ import annotations


class ScenarioError(Exception):
    """Scenario 异常的基类."""

    code: str = "SCENARIO_ERROR"

    def __init__(self, message: str, *, action: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.action = action or "Check scenario configuration"

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        if self.action:
            return f"{self.message} | Action: {self.action}"
        return self.message


class ScenarioLoadError(ScenarioError):
    code = "SCENARIO_VALIDATION_FAILED"


class ScenarioValidationError(ScenarioError):
    code = "SCENARIO_VALIDATION_FAILED"


class ScenarioResourceError(ScenarioError):
    code = "SCENARIO_RESOURCE_UNAVAILABLE"

    def __init__(
        self,
        message: str,
        missing: list[str] | None = None,
        *,
        action: str | None = None,
    ) -> None:
        super().__init__(message, action=action)
        self.missing = missing or []

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        base = super().__str__()
        if self.missing:
            return f"{base}\n  Missing ({len(self.missing)}):\n    - " + "\n    - ".join(self.missing)
        return base


class ScenarioNotFoundError(ScenarioError):
    code = "SCENARIO_NOT_FOUND"


class ScenarioDisabledError(ScenarioError):
    code = "SCENARIO_DISABLED"


class ScenarioInjectionError(ScenarioError):
    code = "SCENARIO_ERROR"


class PlaceholderUnresolvedError(ScenarioError):
    code = "YAML_PLACEHOLDER_UNRESOLVED"


class RoutingFailedError(ScenarioError):
    code = "SCENARIO_NOT_FOUND"


__all__ = [
    "ScenarioError",
    "ScenarioLoadError",
    "ScenarioValidationError",
    "ScenarioResourceError",
    "ScenarioNotFoundError",
    "ScenarioDisabledError",
    "ScenarioInjectionError",
    "PlaceholderUnresolvedError",
    "RoutingFailedError",
]
