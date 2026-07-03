"""WorkTraceService — 纯业务编排 (append / mark_status / 查询).

Reducer / Listener 直接调 ``append()``; Controller 调 ``get_response`` /
``list_by_session`` 给 API 出参.
"""
from __future__ import annotations

import structlog

from hermetic_agent.store.dto.work_trace import (
    AppendTraceEventsRequest,
    MarkTraceStatusRequest,
    TraceEventResponse,
    TurnWorkTraceResponse,
    WorkTraceIndexItem,
    utc_iso,
)
from hermetic_agent.store.models.work_trace import TurnWorkTrace
from hermetic_agent.store.repositories.work_trace_repo import WorkTraceRepository

logger = structlog.get_logger(__name__)


class WorkTraceService:
    """work_trace 业务编排 service.

    业务规则:
    - append: 调 repo; 若失败由 caller (listener) 处理
    - mark_status: 写终态
    - get_response / list_by_session: 转 DTO 出参
    """

    def __init__(self, repo: WorkTraceRepository) -> None:
        self._repo = repo

    async def append(self, req: AppendTraceEventsRequest) -> TurnWorkTrace:
        return await self._repo.append_events(req)

    async def mark_status(
        self, turn_id: str, req: MarkTraceStatusRequest,
    ) -> TurnWorkTrace | None:
        return await self._repo.mark_status(turn_id, req)

    async def get_response(self, turn_id: str) -> TurnWorkTraceResponse | None:
        t = await self._repo.get_by_turn(turn_id)
        if t is None:
            return None
        return self._to_response(t)

    async def list_by_session(
        self, session_id: str, *, limit: int = 20,
    ) -> list[WorkTraceIndexItem]:
        return await self._repo.list_by_session(session_id, limit=limit)

    @staticmethod
    def _to_response(t: TurnWorkTrace) -> TurnWorkTraceResponse:
        events_raw = t.events or []
        events: list[TraceEventResponse] = []
        for e in events_raw:
            try:
                events.append(TraceEventResponse(**e))
            except Exception:  # noqa: BLE001
                logger.warning("work_trace_event_invalid", turn_id=str(t.turn_id), raw=e)
        return TurnWorkTraceResponse(
            turn_id=str(t.turn_id),
            session_id=str(t.session_id),
            scenario=t.scenario,
            status=t.status,
            started_at=utc_iso(t.started_at),
            finished_at=utc_iso(t.finished_at),
            summary=t.summary or {},
            events=events,
        )


__all__ = ["WorkTraceService"]
