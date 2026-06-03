"""FragmentLoader — 渐进式 SKILL 片段加载器.

按 scenario.progressive_skill.strategy 加载 skill 片段:
- ``none``: 不加载任何片段
- ``all``: 加载 skill 完整内容
- ``on_demand``: 按 current_state 加载
- ``explicit``: 开发者显式调用 ``load_fragment`` 加载

Budget 强制: 总 token 数超出 budget 时按 policy 处置
(``error`` 抛异常 / ``warn`` 仅日志 / ``truncate`` 丢弃末尾片段).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from openagent.skill_runtime.errors import (
    FragmentNotFoundError,
    SkillBudgetExceeded,
    SkillNotFoundError,
)
from openagent.skills.registry import Skill, SkillRegistry

logger = structlog.get_logger(__name__)

# 粗略 token 估算: 中英文混合 1 token ≈ 1.5 字符
_TOKEN_PER_CHAR_NUM = 2
_TOKEN_PER_CHAR_DEN = 3
_SEPARATOR = "\n\n---\n\n"

_STRATEGY_NONE = "none"
_STRATEGY_ALL = "all"
_STRATEGY_ON_DEMAND = "on_demand"
_STRATEGY_EXPLICIT = "explicit"

_POLICY_ERROR = "error"
_POLICY_WARN = "warn"
_POLICY_TRUNCATE = "truncate"


@dataclass
class FragmentLoadReport:
    """一次 fragment 加载的统计报告."""

    loaded: list[str] = field(default_factory=list)
    total_tokens: int = 0
    policy: str = _POLICY_ERROR
    dropped: list[str] = field(default_factory=list)


class FragmentLoader:
    """按 strategy + current_state 加载 skill 片段, 强制 budget."""

    def __init__(
        self,
        registry: SkillRegistry,
        budget: int = 4000,
        policy: str = _POLICY_ERROR,
    ) -> None:
        """初始化加载器.

        Args:
            registry: skill 注册中心, 用于按 name 查 skill.
            budget: token 预算上限.
            policy: budget 超限时处置 (error / warn / truncate).
        """
        if budget <= 0:
            raise ValueError(f"budget must be positive, got {budget}")
        if policy not in (_POLICY_ERROR, _POLICY_WARN, _POLICY_TRUNCATE):
            raise ValueError(
                f"policy must be one of error/warn/truncate, got {policy!r}"
            )
        self._registry = registry
        self._budget = budget
        self._policy = policy

    @property
    def budget(self) -> int:
        return self._budget

    @property
    def policy(self) -> str:
        return self._policy

    def load(
        self,
        scenario: Any,
        current_state: str,
    ) -> tuple[str, FragmentLoadReport]:
        """主入口 — 根据 scenario.progressive_skill.strategy 分发."""
        ps = scenario.progressive_skill
        strategy = ps.strategy
        if strategy == _STRATEGY_NONE:
            return "", FragmentLoadReport(policy=self._policy)
        if strategy == _STRATEGY_ALL:
            return self._load_all(scenario)
        if strategy in (_STRATEGY_ON_DEMAND, _STRATEGY_EXPLICIT):
            return self._load_on_demand(scenario, current_state)
        raise ValueError(
            f"Unknown progressive_skill strategy {strategy!r} "
            f"in scenario {getattr(scenario, 'name', '<unknown>')}"
        )

    def _load_all(self, scenario: Any) -> tuple[str, FragmentLoadReport]:
        """``all`` 策略: 加载 scenario.execution.skills 的所有 skill 全文."""
        report = FragmentLoadReport(policy=self._policy)
        texts: list[str] = []
        skill_names: list[str] = list(getattr(scenario.execution, "skills", []) or [])
        for name in skill_names:
            skill = self._require_skill(name)
            text = self._read_skill_main(skill)
            n = _estimate_tokens(text)
            texts.append(text)
            report.loaded.append(f"{name}#all")
            report.total_tokens += n
        return self._enforce_budget(texts, report, scenario_name=_scenario_name(scenario), current_state="*")

    def _load_on_demand(
        self, scenario: Any, current_state: str
    ) -> tuple[str, FragmentLoadReport]:
        """``on_demand`` / ``explicit`` 策略: initial + load_on_state 合并."""
        report = FragmentLoadReport(policy=self._policy)
        texts: list[str] = []
        ps = scenario.progressive_skill
        # 1. initial_skills (任何 state 都会加载)
        for init in ps.initial_skills or []:
            text, n = self._load_fragment(init["name"], init.get("mode", "summary"))
            texts.append(text)
            report.loaded.append(f"{init['name']}#{init.get('mode', 'summary')}")
            report.total_tokens += n
        # 2. load_on_state[current_state]
        for frag_id in ps.load_on_state.get(current_state, []) or []:
            skill_name, frag_name = self._parse_frag_id(frag_id)
            text, n = self._load_fragment(skill_name, frag_name)
            texts.append(text)
            report.loaded.append(frag_id)
            report.total_tokens += n
        return self._enforce_budget(
            texts, report,
            scenario_name=_scenario_name(scenario), current_state=current_state,
        )

    def _load_fragment(self, skill_name: str, frag_id: str) -> tuple[str, int]:
        """加载单个 skill:frag_id, 返回 (text, tokens)."""
        skill = self._require_skill(skill_name)
        skill_dir = self._skill_dir(skill)
        if skill_dir is None:
            raise FragmentNotFoundError(
                skill_name, frag_id, expected_path=None
            )
        frag_path = skill_dir / "fragments" / f"{frag_id}.md"
        if not frag_path.exists():
            raise FragmentNotFoundError(
                skill_name, frag_id, expected_path=str(frag_path)
            )
        text = frag_path.read_text(encoding="utf-8")
        return text, _estimate_tokens(text)

    def _enforce_budget(
        self,
        texts: list[str],
        report: FragmentLoadReport,
        *,
        scenario_name: str,
        current_state: str,
    ) -> tuple[str, FragmentLoadReport]:
        """检查 total_tokens 是否超 budget, 按 policy 处置."""
        if report.total_tokens <= self._budget:
            return _join(texts), report
        if self._policy == _POLICY_ERROR:
            raise SkillBudgetExceeded(report.total_tokens, self._budget, list(report.loaded))
        if self._policy == _POLICY_WARN:
            logger.warning(
                "skill_budget_exceeded",
                used=report.total_tokens, limit=self._budget,
                loaded=report.loaded, scenario=scenario_name, state=current_state,
            )
            return _join(texts), report
        # truncate: 从尾部丢弃片段, 直到 ≤ budget
        while texts and report.total_tokens > self._budget:
            dropped_text = texts.pop()
            report.total_tokens -= _estimate_tokens(dropped_text)
            report.dropped.append(report.loaded.pop() if report.loaded else "?")
        return _join(texts), report

    def _require_skill(self, skill_name: str) -> Skill:
        skill = self._registry.get(skill_name)
        if skill is None:
            raise SkillNotFoundError(skill_name)
        return skill

    @staticmethod
    def _skill_dir(skill: Skill) -> Path | None:
        if not skill.source:
            return None
        p = Path(skill.source)
        if p.is_file():
            return p.parent
        return p

    @staticmethod
    def _read_skill_main(skill: Skill) -> str:
        if skill.source:
            p = Path(skill.source)
            if p.is_file() and p.exists():
                return p.read_text(encoding="utf-8")
        if skill.prompt_template:
            return skill.prompt_template
        return f"## {skill.name}\n\n{skill.description}\n"

    @staticmethod
    def _parse_frag_id(frag_id: str) -> tuple[str, str]:
        if ":" not in frag_id:
            raise FragmentNotFoundError(
                skill_name=frag_id, fragment_id="<missing>"
            )
        skill_name, frag_name = frag_id.split(":", 1)
        if not skill_name or not frag_name:
            raise FragmentNotFoundError(
                skill_name=skill_name or "<empty>",
                fragment_id=frag_name or "<empty>",
            )
        return skill_name, frag_name


def _estimate_tokens(text: str) -> int:
    """粗略 token 估算: 1 token ≈ 1.5 字符 (中英文混合)."""
    return max(1, len(text) * _TOKEN_PER_CHAR_NUM // _TOKEN_PER_CHAR_DEN)


def _join(texts: list[str]) -> str:
    return _SEPARATOR.join(texts)


def _scenario_name(scenario: Any) -> str:
    return getattr(scenario, "name", "")


__all__ = ["FragmentLoader", "FragmentLoadReport"]
