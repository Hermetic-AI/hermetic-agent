"""ScenarioInjector — 白名单过滤 + 注入系统提示词.

caller 提供的 skills/tools 必须和 scenario 自己的白名单取交集;
caller_system_prompt 追加在 scenario.execution.system_prompt 后面.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import structlog

from openagent.scenarios.config import ScenarioConfig

logger = structlog.get_logger(__name__)


class AuditLogger(Protocol):
    """审计日志接口 — 实现方可在构造时注入."""

    def log(self, event: str, **fields: Any) -> None: ...


class InMemoryAuditLogger:
    """默认内存审计, 用于测试 + 本地调试."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def log(self, event: str, **fields: Any) -> None:
        self.records.append({"event": event, **fields})


@dataclass
class InjectionResult:
    """注入结果.

    Attributes:
        final_skills: 交集 (scenario 白名单 ∩ caller 传入).
        final_tools:  交集.
        final_system_prompt: scenario 自己的 prompt + caller 追加的.
        rejected_skills: caller 传入但不在白名单中的 skill 名称.
        rejected_tools:  caller 传入但不在白名单中的 tool 名称.
    """

    final_skills: list[str] = field(default_factory=list)
    final_tools: list[str] = field(default_factory=list)
    final_system_prompt: str = ""
    rejected_skills: list[str] = field(default_factory=list)
    rejected_tools: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_skills": self.final_skills,
            "final_tools": self.final_tools,
            "final_system_prompt_len": len(self.final_system_prompt),
            "rejected_skills": self.rejected_skills,
            "rejected_tools": self.rejected_tools,
        }


class ScenarioInjector:
    """把 scenario 配置 + caller 传入的 skills/tools 合并成 InjectionResult."""

    def __init__(self, audit: AuditLogger | None = None) -> None:
        self._audit = audit or InMemoryAuditLogger()

    def inject(
        self,
        scenario: ScenarioConfig,
        user_message: str = "",
        caller_skills: list[str] | None = None,
        caller_tools: list[str] | None = None,
        caller_system_prompt: str = "",
    ) -> InjectionResult:
        """白名单过滤 + system_prompt 拼接.

        永远不抛错 — 被丢弃的项记录在 rejected_*, 由调用方审计/告警.

        skills / tools 解析规则 (caller vs scenario 谁说了算):
          - caller 没传 (None 或 ``[]``) → 用 scenario 自己的白名单全部
            (场景路由命中后, scenario.execution.skills 是这个场景**默认要用的**)
          - caller 传了 (非空 list) → 用 caller 的, 但**逐项**过 scenario 白名单
            (caller 可以限制范围, 但不能注入 scenario 没声明的 skill/tool)
          - ``rejected_*`` 记录 caller 传了但被白名单拒的项

        跟设计文档 (scenario-skill-walkthrough.md §5) 一致:
          "场景对话的 skill 列表**只来自 scenario 自己的 execution.skills 白名单**"
        """
        caller_skills = caller_skills or []
        caller_tools = caller_tools or []

        allowed_skills = set(scenario.execution.skills)
        allowed_tools = set(scenario.execution.tools)

        if not caller_skills:
            # caller 没传 → 用 scenario 自己的白名单 (场景路由命中的默认行为)
            final_skills = list(scenario.execution.skills)
        else:
            # caller 传了 → 取交集, caller 越权的被拒
            final_skills = [s for s in caller_skills if s in allowed_skills]

        if not caller_tools:
            final_tools = list(scenario.execution.tools)
        else:
            final_tools = [t for t in caller_tools if t in allowed_tools]

        # rejected 只看 caller 传了的 (空 caller 没东西可拒)
        rejected_skills = [s for s in caller_skills if s not in allowed_skills]
        rejected_tools = [t for t in caller_tools if t not in allowed_tools]

        parts: list[str] = []
        if scenario.execution.system_prompt:
            parts.append(scenario.execution.system_prompt)
        if caller_system_prompt:
            parts.append(caller_system_prompt)
        final_prompt = "\n\n".join(parts)

        result = InjectionResult(
            final_skills=final_skills,
            final_tools=final_tools,
            final_system_prompt=final_prompt,
            rejected_skills=rejected_skills,
            rejected_tools=rejected_tools,
        )

        self._audit.log(
            "scenario_inject",
            scenario=scenario.name,
            user_message_len=len(user_message),
            requested_skills=caller_skills,
            requested_tools=caller_tools,
            final_skills=final_skills,
            final_tools=final_tools,
            rejected_skills=rejected_skills,
            rejected_tools=rejected_tools,
        )
        logger.info(
            "scenario_inject_done",
            scenario=scenario.name,
            skills=len(final_skills),
            tools=len(final_tools),
            rejected_skills=len(rejected_skills),
            rejected_tools=len(rejected_tools),
        )

        return result


__all__ = ["ScenarioInjector", "InjectionResult", "AuditLogger", "InMemoryAuditLogger"]
