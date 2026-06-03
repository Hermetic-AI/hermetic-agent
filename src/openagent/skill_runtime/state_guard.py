"""StateGuard — 状态机守卫.

校验 AI 在当前状态 (state) 下:
1. 是否能调用某个工具 (can_call_tool)
2. 是否能转移到下一个状态 (can_transition)
3. 当前状态是什么 (get_state)

框架级工具 ask_user 永远允许 (不在 allowed_tools 时也允许).
"""

from __future__ import annotations

from openagent.skill_runtime.manifest import SkillManifest

_FRAMEWORK_TOOLS = frozenset({"ask_user"})


class StateGuard:
    """状态机守卫 — 校验 AI 是否能在当前状态调工具或转移状态."""

    def __init__(self, manifest: SkillManifest, current_state: str | None = None) -> None:
        """初始化守卫.

        Args:
            manifest: SkillManifest, 提供 states + transitions.
            current_state: 起始 state. 缺省取 manifest.initial_state.
        """
        self._manifest = manifest
        self._current_state = current_state or manifest.initial_state

    def get_state(self) -> str:
        """返回当前 state id."""
        return self._current_state

    def set_state(self, new_state: str) -> None:
        """强制设置当前 state (不做转移校验, 由调用方负责)."""
        self._current_state = new_state

    def can_call_tool(self, tool_name: str) -> tuple[bool, str]:
        """检查当前 state 是否允许调 ``tool_name``.

        Returns:
            ``(allowed, reason)``: allowed=True 时 reason 是 "ok";
            allowed=False 时 reason 给出"哪个 state 不允许 + 允许列表".
        """
        if tool_name in _FRAMEWORK_TOOLS:
            return True, f"{tool_name} is always allowed (framework-level tool)"
        if self._current_state not in self._manifest.states:
            return False, (
                f"State {self._current_state!r} not in manifest "
                f"states {sorted(self._manifest.states.keys())}"
            )
        state = self._manifest.states[self._current_state]
        if tool_name in state.allowed_tools:
            return True, "ok"
        return False, (
            f"State {self._current_state!r} 不允许调 {tool_name!r}。"
            f"允许的工具: {sorted(state.allowed_tools)}。"
        )

    def can_transition(self, new_state: str) -> bool:
        """检查 ``new_state`` 是否为当前 state 的合法下一状态."""
        allowed = self._manifest.transitions.get(self._current_state, set())
        return new_state in allowed

    def allowed_next_states(self) -> list[str]:
        """返回当前 state 所有可达的下一状态 (排序后)."""
        return sorted(self._manifest.transitions.get(self._current_state, set()))

    def assert_can_transition(self, new_state: str) -> None:
        """和 ``can_transition`` 一样, 但失败时抛 ``StateGuardViolation``."""
        from openagent.skill_runtime.errors import StateGuardViolation

        if not self.can_transition(new_state):
            allowed = self.allowed_next_states()
            raise StateGuardViolation(
                current_state=self._current_state,
                detail=(
                    f"Cannot transition to {new_state!r}. "
                    f"Allowed: {allowed}."
                ),
            )


__all__ = ["StateGuard"]
