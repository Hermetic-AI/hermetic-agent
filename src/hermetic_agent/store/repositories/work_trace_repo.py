"""WorkTraceRepository ABC."""
from __future__ import annotations

from abc import abstractmethod

from hermetic_agent.store.dto.work_trace import (
    AppendTraceEventsRequest,
    MarkTraceStatusRequest,
    WorkTraceIndexItem,
)
from hermetic_agent.store.models.work_trace import TurnWorkTrace
from hermetic_agent.store.repositories._base import Repository


class WorkTraceRepository(Repository[TurnWorkTrace]):
    """work_trace 仓储接口.

    关键方法 (业务级, 在基类 Repository 之外):
    - ``append_events(req)``: 追加一批 events; turn 不存在则自动 create
    - ``mark_status(turn_id, req)``: 更新 turn 终态
    - ``get_by_turn(turn_id)``: 拉完整 trace
    - ``list_by_session(session_id, limit)``: 列 session 下索引
    """

    @abstractmethod
    async def append_events(self, req: AppendTraceEventsRequest) -> TurnWorkTrace:
        """append 一批 events; 若 turn_id 不存在则自动 create (status=running)."""

    @abstractmethod
    async def mark_status(
        self, turn_id: str, req: MarkTraceStatusRequest
    ) -> TurnWorkTrace | None:
        """更新 turn 终态 + 写 finished_at + 累加 summary."""

    @abstractmethod
    async def get_by_turn(self, turn_id: str) -> TurnWorkTrace | None:
        """按 turn_id 拉完整 trace."""

    @abstractmethod
    async def list_by_session(
        self, session_id: str, *, limit: int = 20,
    ) -> list[WorkTraceIndexItem]:
        """按 session 列索引 (不含完整 events)."""


__all__ = ["WorkTraceRepository"]
