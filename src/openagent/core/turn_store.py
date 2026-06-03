"""core/turn_store.py — Turn 生命周期 + Checkpoint 持久化.

设计文档 §3 L3 (D7 整合). 生产用 Postgres (P7 阶段实现), P5 阶段
只交付 ``InMemoryTurnStore`` 供 ``SuspendableScheduler`` 测试.

存储对象:
- Turn: 一个 skill 的一次执行 (session 内可多次 turn)
- TurnEvent: 见 ``auip.events.TurnEvent``
- Checkpoint: suspend 时的完整状态快照, 供 resume 恢复
"""

from __future__ import annotations

import asyncio
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from openagent.auip.events import TurnEvent

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

# 合法 turn status 集合, 方便 type hints / 单元测试
TURN_STATUS_RUNNING = "running"
TURN_STATUS_SUSPENDED = "suspended"
TURN_STATUS_DONE = "done"
TURN_STATUS_ERROR = "error"
TURN_STATUSES = frozenset(
    {TURN_STATUS_RUNNING, TURN_STATUS_SUSPENDED, TURN_STATUS_DONE, TURN_STATUS_ERROR}
)


@dataclass
class Checkpoint:
    """Suspend 时写入的完整状态快照.

    Attributes:
        checkpoint_id: 唯一 id.
        turn_id: 所属 turn.
        state: suspend 时的 manifest state id (e.g. ``S02``).
        skill_ctx: skill 上下文 (current_state / 已收集的 OD/日期/航班 等).
        open_tool_calls: 未决的工具调用列表 (典型: ask_user 的 tool_use).
        messages_snapshot: 截至 suspend 的对话消息 (P5 仅取 [{role,content}]).
        last_event_seq: 截至 suspend 时的最大 seq; resume 后从 seq+1 续号.
        created_at: Unix 时间戳.
    """

    checkpoint_id: str
    turn_id: str
    state: str
    skill_ctx: dict[str, Any]
    open_tool_calls: list[dict[str, Any]]
    messages_snapshot: list[dict[str, Any]]
    last_event_seq: int
    created_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Abstract backend
# ---------------------------------------------------------------------------


class TurnStore(ABC):
    """Turn 生命周期 + Checkpoint 持久化抽象.

    命名: ``*Store`` 而非 ``*Repository`` (与既有 SessionRepository
    不冲突, P5 阶段允许并存; 后续 P7 可统一重命名).
    """

    @abstractmethod
    async def create_turn(
        self, session_id: str, skill_name: str, skill_version: str
    ) -> str:
        """创建一个新 turn, 返回 ``turn_id``."""
        ...

    @abstractmethod
    async def get_turn(self, turn_id: str) -> dict[str, Any] | None:
        """获取 turn 元数据; 不存在返回 ``None``."""
        ...

    @abstractmethod
    async def update_turn_status(
        self, turn_id: str, status: str, state: str | None = None
    ) -> None:
        """更新 turn 状态; 可选更新 ``state`` (suspend 时记录当前 state)."""
        ...

    @abstractmethod
    async def save_event(self, turn_id: str, event: TurnEvent) -> None:
        """追加一个事件到 turn 事件流."""
        ...

    @abstractmethod
    async def get_events(
        self, turn_id: str, after_seq: int = 0
    ) -> list[TurnEvent]:
        """返回 turn 事件列表, 可选只取 ``seq > after_seq`` 的部分."""
        ...

    @abstractmethod
    async def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        """写入 (或覆盖) 一个 checkpoint; 同一 turn 可有多个历史版本."""
        ...

    @abstractmethod
    async def get_latest_checkpoint(
        self, turn_id: str
    ) -> Checkpoint | None:
        """返回某 turn 的最新 checkpoint; 无则 ``None``."""
        ...


# ---------------------------------------------------------------------------
# In-memory implementation (P5)
# ---------------------------------------------------------------------------


class InMemoryTurnStore(TurnStore):
    """纯内存实现, 单进程; 进程退出即清空, 仅供测试 / 开发."""

    def __init__(self) -> None:
        self._turns: dict[str, dict[str, Any]] = {}
        self._events: dict[str, list[TurnEvent]] = {}
        self._checkpoints: dict[str, list[Checkpoint]] = {}
        self._lock = asyncio.Lock()

    async def create_turn(
        self, session_id: str, skill_name: str, skill_version: str
    ) -> str:
        """创建 turn, 返回 ``turn_id``."""
        turn_id = str(uuid.uuid4())
        async with self._lock:
            self._turns[turn_id] = {
                "turn_id": turn_id,
                "session_id": session_id,
                "skill_name": skill_name,
                "skill_version": skill_version,
                "status": TURN_STATUS_RUNNING,
                "state": None,
                "created_at": time.time(),
            }
            self._events[turn_id] = []
            self._checkpoints[turn_id] = []
        return turn_id

    async def get_turn(self, turn_id: str) -> dict[str, Any] | None:
        """读 turn 元数据; 浅拷贝避免外部修改."""
        meta = self._turns.get(turn_id)
        return dict(meta) if meta is not None else None

    async def update_turn_status(
        self, turn_id: str, status: str, state: str | None = None
    ) -> None:
        """更新 status (必要时 state). 未知 turn_id 静默忽略以保持幂等."""
        if status not in TURN_STATUSES:
            raise ValueError(
                f"Invalid turn status {status!r}; valid: {sorted(TURN_STATUSES)}"
            )
        meta = self._turns.get(turn_id)
        if meta is None:
            return
        meta["status"] = status
        if state is not None:
            meta["state"] = state

    async def save_event(self, turn_id: str, event: TurnEvent) -> None:
        """追加一个事件; 内部按 seq 排序保证 ``get_events`` 返回有序."""
        bucket = self._events.setdefault(turn_id, [])
        bucket.append(event)
        bucket.sort(key=lambda e: e.seq)

    async def get_events(
        self, turn_id: str, after_seq: int = 0
    ) -> list[TurnEvent]:
        """返回 turn 事件列表 (按 seq 升序)."""
        bucket = self._events.get(turn_id, [])
        if after_seq <= 0:
            return list(bucket)
        return [e for e in bucket if e.seq > after_seq]

    async def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        """追加一个 checkpoint (保留历史)."""
        bucket = self._checkpoints.setdefault(checkpoint.turn_id, [])
        bucket.append(checkpoint)

    async def get_latest_checkpoint(
        self, turn_id: str
    ) -> Checkpoint | None:
        """返回某 turn 最新 checkpoint."""
        bucket = self._checkpoints.get(turn_id, [])
        if not bucket:
            return None
        return max(bucket, key=lambda c: c.created_at)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def status_implies_terminal(status: str) -> bool:
    """判断 status 是否为终止态 (done / error)."""
    return status in (TURN_STATUS_DONE, TURN_STATUS_ERROR)


__all__ = [
    "Checkpoint",
    "InMemoryTurnStore",
    "TURN_STATUS_DONE",
    "TURN_STATUS_ERROR",
    "TURN_STATUS_RUNNING",
    "TURN_STATUS_SUSPENDED",
    "TURN_STATUSES",
    "TurnStore",
    "status_implies_terminal",
]
