"""Skill Runtime 异常层级 — L3 Skill Runtime Layer.

对应设计文档 §10 错误码 (SKILL_NOT_FOUND / FRAGMENT_NOT_FOUND /
SKILL_BUDGET_EXCEEDED), 所有异常带 ``action`` 字段.
"""


class SkillRuntimeError(Exception):
    """Skill Runtime 异常的基类."""

    def __init__(self, message: str, *, action: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.action = action or "Check skill runtime configuration"

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.message} | Action: {self.action}" if self.action else self.message


class SkillNotFoundError(SkillRuntimeError):
    def __init__(self, skill_name: str) -> None:
        super().__init__(
            f"Skill {skill_name!r} not found in registry",
            action="Register the skill or fix scenario.execution.skills.",
        )
        self.skill_name = skill_name


class FragmentNotFoundError(SkillRuntimeError):
    def __init__(self, skill_name: str, fragment_id: str, expected_path: str | None = None) -> None:
        path_hint = f" (expected at {expected_path})" if expected_path else ""
        super().__init__(
            f"Fragment {fragment_id!r} of skill {skill_name!r} not found{path_hint}",
            action="Create the fragment file or remove it from load_on_state.",
        )
        self.skill_name = skill_name
        self.fragment_id = fragment_id
        self.expected_path = expected_path


class SkillBudgetExceeded(SkillRuntimeError):  # noqa: N818 (domain name per spec §10)
    def __init__(self, used: int, limit: int, loaded: list[str] | None = None) -> None:
        super().__init__(
            f"Skill fragment budget exceeded: used={used} > limit={limit}. "
            f"Loaded: [{', '.join(loaded or [])}]",
            action="Reduce load_on_state entries or raise budget_tokens.",
        )
        self.used = used
        self.limit = limit
        self.loaded = loaded or []


class ManifestLoadError(SkillRuntimeError):
    def __init__(self, path: str, reason: str) -> None:
        super().__init__(
            f"Failed to load SkillManifest from {path!r}: {reason}",
            action="Check manifest YAML syntax and required fields.",
        )
        self.path = path
        self.reason = reason


class StateGuardViolation(SkillRuntimeError):  # noqa: N818 (domain name per spec §10)
    def __init__(self, current_state: str, detail: str) -> None:
        super().__init__(
            f"State guard violation at state {current_state!r}: {detail}",
            action="Update the manifest or change the current state.",
        )
        self.current_state = current_state
        self.detail = detail


__all__ = [
    "SkillRuntimeError",
    "SkillNotFoundError",
    "FragmentNotFoundError",
    "SkillBudgetExceeded",
    "ManifestLoadError",
    "StateGuardViolation",
]
