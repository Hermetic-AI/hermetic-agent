"""SkillManifest — 状态机清单数据模型.

描述一个 Skill 的状态机: states (含允许的工具 / 卡片 / 超时) +
transitions (允许的状态转移). YAML 格式可手工编写, 也可由 auip/
skill_compiler 从 SKILL.md 编译生成.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from openagent.skills.runtime.errors import ManifestLoadError

_VALID_TRANSITION_KEYS = {"from", "to"}
_VALID_STATE_KEYS = {"id", "description", "allowed_tools", "card", "timeout"}


@dataclass
class StateSpec:
    """单个状态的规格.

    Attributes:
        description: 状态描述, 用于 system prompt / 调试.
        allowed_tools: 当前状态允许 AI 调用的工具名列表.
            框架级工具 ask_user 永远允许, 不需要列在 allowed_tools.
        card: 该状态触发的默认 A2UI 卡片名, 可为 None.
        timeout: 该状态默认超时 (秒).
    """

    description: str = ""
    allowed_tools: list[str] = field(default_factory=list)
    card: str | None = None
    timeout: int = 300


@dataclass
class SkillManifest:
    """Skill 状态机清单.

    Attributes:
        name: 唯一名称 (kebab-case).
        version: 语义化版本 (X.Y.Z).
        initial_state: 起始状态, 必须在 states 里.
        states: 状态 id → StateSpec 映射.
        transitions: 状态 id → 可达状态集合 映射.
            例如: ``{"S01": {"S02", "S03"}}`` 表示 S01 可转到 S02/S03.
    """

    name: str
    version: str = "1.0.0"
    initial_state: str = "S01"
    states: dict[str, StateSpec] = field(default_factory=dict)
    transitions: dict[str, set[str]] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: Path) -> SkillManifest:
        """从 YAML 文件加载 manifest.

        YAML 格式示例::

            name: book-flight
            version: "1.0.0"
            initial_state: S01
            states:
              - id: S01
                description: 初始化
                allowed_tools: [ask_user]
                timeout: 60
              - id: S02
                description: 询问城市日期
                allowed_tools: [ask_user, query_flight_basic]
            transitions:
              S01: [S02, S05]
              S02: [S03, S04]

        Args:
            path: YAML 文件路径.

        Returns:
            解析得到的 ``SkillManifest`` 实例.

        Raises:
            ManifestLoadError: YAML 解析失败或字段缺失.
        """
        try:
            raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ManifestLoadError(str(path), f"YAML parse failed: {exc}") from exc
        if not isinstance(raw, dict):
            raise ManifestLoadError(
                str(path), f"top-level must be a mapping, got {type(raw).__name__}"
            )
        return cls.from_dict(raw, source=str(path))

    @classmethod
    def from_dict(
        cls, raw: dict[str, Any], *, source: str = "<dict>"
    ) -> SkillManifest:
        """从已解析的 dict 构造 manifest (供测试 / 编程式构造使用)."""
        try:
            states = _parse_states(raw.get("states", []))
            transitions = _parse_transitions(raw.get("transitions", {}))
        except ManifestLoadError:
            raise
        except (TypeError, ValueError) as exc:
            raise ManifestLoadError(source, f"invalid structure: {exc}") from exc
        name = raw.get("name")
        if not name:
            raise ManifestLoadError(source, "missing required field 'name'")
        initial = raw.get("initial_state", "S01")
        if states and initial not in states:
            raise ManifestLoadError(
                source,
                f"initial_state {initial!r} not in declared states "
                f"{sorted(states.keys())}",
            )
        return cls(
            name=str(name),
            version=str(raw.get("version", "1.0.0")),
            initial_state=str(initial),
            states=states,
            transitions=transitions,
        )

    def to_yaml(self, path: Path) -> None:
        """把 manifest 序列化回 YAML, 写到 ``path``."""
        payload = self.to_dict()
        Path(path).write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

    def to_dict(self) -> dict[str, Any]:
        """导出为 dict (供序列化 / 比较)."""
        return {
            "name": self.name,
            "version": self.version,
            "initial_state": self.initial_state,
            "states": [
                {
                    "id": sid,
                    "description": s.description,
                    "allowed_tools": list(s.allowed_tools),
                    **({"card": s.card} if s.card else {}),
                    "timeout": s.timeout,
                }
                for sid, s in self.states.items()
            ],
            "transitions": {
                src: sorted(dst) for src, dst in self.transitions.items()
            },
        }

    @classmethod
    def empty(cls) -> SkillManifest:
        """返回空 manifest, 用于无状态机的兜底场景."""
        return cls(name="_empty", states={}, transitions={})

    def state_ids(self) -> list[str]:
        """返回所有 state id 列表 (顺序不固定, 仅供调试)."""
        return list(self.states.keys())


def _parse_states(items: Any) -> dict[str, StateSpec]:
    if items is None:
        return {}
    if not isinstance(items, list):
        raise ManifestLoadError("<states>", "states must be a list")
    result: dict[str, StateSpec] = {}
    for entry in items:
        if not isinstance(entry, dict) or "id" not in entry:
            raise ManifestLoadError("<states>", f"each state needs 'id', got {entry!r}")
        extra = set(entry) - _VALID_STATE_KEYS
        if extra:
            raise ManifestLoadError(
                "<states>",
                f"unknown state field(s): {sorted(extra)}. "
                f"Valid: {sorted(_VALID_STATE_KEYS)}",
            )
        sid = str(entry["id"])
        spec = StateSpec(
            description=str(entry.get("description", "")),
            allowed_tools=list(entry.get("allowed_tools", [])),
            card=entry.get("card"),
            timeout=int(entry.get("timeout", 300)),
        )
        result[sid] = spec
    return result


def _parse_transitions(raw: Any) -> dict[str, set[str]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ManifestLoadError("<transitions>", "transitions must be a mapping")
    out: dict[str, set[str]] = {}
    for src, dst in raw.items():
        if isinstance(dst, (list, set)):
            out[str(src)] = {str(x) for x in dst}
        else:
            raise ManifestLoadError(
                "<transitions>", f"transitions[{src!r}] must be a list, got {type(dst).__name__}"
            )
    return out


__all__ = ["StateSpec", "SkillManifest"]
