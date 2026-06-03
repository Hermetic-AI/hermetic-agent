"""PromptBuilder — 拼装 system prompt.

把 6 段拼成一个完整 prompt:
1. 框架 base (框架注入的人格 / 行为约束)
2. Scenario.system_prompt (场景级系统提示)
3. A2UI 提示 (如果 scenario.a2ui.enabled)
4. Skill 片段 (按 progressive_skill 策略加载)
5. 当前 state 提示
6. 对话历史 (由 framework 处理, 此处仅追加)
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from openagent.skill_runtime.fragments import FragmentLoader


class PromptBuilder:
    """把 6 段拼装成最终 system prompt."""

    def __init__(
        self,
        fragment_loader: FragmentLoader,
        framework_base: str = "",
        aui_instructions: str = "",
    ) -> None:
        """初始化 builder.

        Args:
            fragment_loader: 已配置 budget + policy 的 FragmentLoader.
            framework_base: 框架级基础提示 (人格 / 行为约束).
            aui_instructions: A2UI 协议使用说明 (cards 渲染说明).
        """
        self._loader = fragment_loader
        self._framework_base = framework_base
        self._aui_instructions = aui_instructions

    def build(
        self,
        scenario: Any,
        current_state: str,
        messages: Iterable[Any] | None = None,
    ) -> str:
        """拼装完整 system prompt.

        Args:
            scenario: ScenarioConfig (或 duck-typed 对象, 需有
                .name / .execution.system_prompt / .progressive_skill /
                .a2ui.enabled 等属性).
            current_state: 当前 state id.
            messages: 对话历史 (ChatMessage 列表或可迭代对象, 默认为空).
                每条消息渲染为 ``[role] content`` 单行.

        Returns:
            拼好的 prompt 字符串.
        """
        parts: list[str] = []
        # 1. 框架 base
        if self._framework_base:
            parts.append(self._framework_base)
        # 2. Scenario 级 system_prompt
        scenario_prompt = self._scenario_prompt(scenario)
        if scenario_prompt:
            parts.append(scenario_prompt)
        # 3. A2UI 提示
        if self._aui_enabled(scenario) and self._aui_instructions:
            parts.append(self._aui_instructions)
        # 4. Skill 片段
        skill_text, report = self._loader.load(scenario, current_state)
        if skill_text:
            header = f"[Active skill fragments: {', '.join(report.loaded)}]"
            parts.append(f"{header}\n{skill_text}")
        # 5. 当前 state 提示
        parts.append(f"[Current state: {current_state}]")
        # 6. 对话历史
        history = self._render_messages(messages)
        if history:
            parts.append(history)
        return "\n\n".join(parts)

    @staticmethod
    def _scenario_prompt(scenario: Any) -> str:
        exec_ = getattr(scenario, "execution", None)
        if exec_ is None:
            return ""
        return str(getattr(exec_, "system_prompt", "") or "")

    @staticmethod
    def _aui_enabled(scenario: Any) -> bool:
        a2ui = getattr(scenario, "a2ui", None)
        if a2ui is None:
            return False
        return bool(getattr(a2ui, "enabled", False))

    @staticmethod
    def _render_messages(messages: Iterable[Any] | None) -> str:
        if not messages:
            return ""
        lines: list[str] = []
        for m in messages:
            role = getattr(m, "role", "?")
            content = getattr(m, "content", "")
            lines.append(f"[{role}] {content}")
        return "\n".join(lines)


__all__ = ["PromptBuilder"]
