"""AUIP TurnEvent — 统一事件流.

设计文档 §3 L3 / §12.3 SuspendableScheduler 产出的事件协议.
每个 turn 内事件 ``seq`` 严格递增; type 枚举覆盖完整对话流:
session → state → text / reasoning / tool_use / tool_result → card →
suspend → (wait) → resume → tool_result → done / error.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TurnEventType(str, Enum):
    """AUIP 事件类型枚举.

    字符串值用于跨进程 (SSE / Redis / DB) 序列化. 继承 ``str`` 让
    JSON 序列化直接产出可读字符串而非 ``"SESSION"`` 整数.
    """

    SESSION = "session"
    TEXT = "text"
    REASONING = "reasoning"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    CARD = "card"
    STATE = "state"
    SUSPEND = "suspend"
    RESUME = "resume"
    DONE = "done"
    ERROR = "error"


@dataclass
class TurnEvent:
    """一个 turn 内的事件.

    Attributes:
        seq: 严格递增序号, 0-based, 在同一 turn_id 内唯一.
        turn_id: 所属 turn 的 id.
        type: 事件类型.
        data: 事件负载 (type 决定结构; 见设计文档 §12.3).
        ts: Unix 时间戳, 缺省 ``time.time()`` (仅用于调试 / 排序).
    """

    seq: int
    turn_id: str
    type: TurnEventType
    data: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """序列化为 dict (供 SSE / DB 持久化)."""
        return {
            "seq": self.seq,
            "turn_id": self.turn_id,
            "type": self.type.value,
            "data": self.data,
            "ts": self.ts,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TurnEvent:
        """从 dict 反序列化.

        Raises:
            KeyError: 缺 ``seq`` / ``turn_id`` / ``type``.
            ValueError: ``type`` 不是合法枚举.
        """
        return cls(
            seq=d["seq"],
            turn_id=d["turn_id"],
            type=TurnEventType(d["type"]),
            data=d.get("data", {}),
            ts=d.get("ts", time.time()),
        )


def assert_seq_increasing(events: list[TurnEvent]) -> None:
    """断言一个 turn 的 events.seq 严格递增 (按列表顺序).

    Raises:
        ValueError: 任意相邻两事件 seq 顺序错误.
    """
    for prev, cur in zip(events, events[1:], strict=False):
        if cur.seq <= prev.seq:
            raise ValueError(
                f"TurnEvent.seq must be strictly increasing; "
                f"got {prev.seq} then {cur.seq}"
            )


__all__ = ["TurnEventType", "TurnEvent", "assert_seq_increasing"]
