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
        """
        caller_skills = caller_skills or []
        caller_tools = caller_tools or []

        allowed_skills = set(scenario.execution.skills)
        allowed_tools = set(scenario.execution.tools)

        final_skills = [s for s in caller_skills if s in allowed_skills]
        final_tools = [t for t in caller_tools if t in allowed_tools]
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
