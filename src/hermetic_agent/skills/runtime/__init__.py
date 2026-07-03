"""hermetic_agent.skills.runtime — skill 运行时框架.

业务上, ``hermetic_agent.skills/`` 拆成两层:
- 顶层 ``hermetic_agent.skills/``           — 业务领域 (Skill 实体, 注册表, frontmatter)
- 顶层 ``hermetic_agent.skills/runtime/``    — 运行时框架 (manifest, state_guard,
  fragments, prompt_builder)

子包内部互引都用绝对路径 ``hermetic_agent.skills.runtime.X`` (不跨包边界),
跟外部 import 风格统一.
"""
from hermetic_agent.skills.runtime.errors import (
    FragmentNotFoundError,
    ManifestLoadError,
    SkillBudgetExceeded,
    SkillNotFoundError,
    SkillRuntimeError,
    StateGuardViolation,
)
from hermetic_agent.skills.runtime.fragments import FragmentLoader, FragmentLoadReport
from hermetic_agent.skills.runtime.manifest import SkillManifest, StateSpec
from hermetic_agent.skills.runtime.prompt_builder import PromptBuilder
from hermetic_agent.skills.runtime.state_guard import StateGuard

__all__ = [
    "FragmentLoader", "FragmentLoadReport", "FragmentNotFoundError",
    "ManifestLoadError", "PromptBuilder", "SkillBudgetExceeded",
    "SkillManifest", "SkillNotFoundError", "SkillRuntimeError",
    "StateGuard", "StateSpec", "StateGuardViolation",
]
