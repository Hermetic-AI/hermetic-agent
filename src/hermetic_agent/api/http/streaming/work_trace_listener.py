"""WorkTraceListener — 单向 sink, 订阅 chat SSE, 写 turn_work_trace.

设计原则:
- 纯单向 sink, 不改 stream content, 不改 yield 顺序
- listener 抛错 → 隔离, 不影响 chat 流
- reducer 抛错 → 隔离, 跳过单个 event

调用模式 (chat_controller 注入位置):
    async for ev in stream_with_keepalive(card_rendered):
        listener.on_event(ev)
        yield ev
"""
from __future__ import annotations

import contextlib

import structlog

from hermetic_agent.auip.work_trace_reducer import (
    ReducerContext,
    ReducerState,
    reduce_event,
)
from hermetic_agent.providers.streaming import StreamEvent
from hermetic_agent.store.dto.work_trace import (
    AppendTraceEventsRequest,
    MarkTraceStatusRequest,
    TraceEventResponse,
)
from hermetic_agent.store.services.work_trace_service import WorkTraceService

logger = structlog.get_logger(__name__)


class WorkTraceListener:
    """chat 流单向 sink — 把每个 event 翻译成 TraceEvent 并 append."""

    def __init__(
        self,
        turn_id: str,
        session_id: str,
        scenario: str | None,
        service: WorkTraceService,
    ) -> None:
        self._turn_id = turn_id
        self._session_id = session_id
        self._scenario = scenario
        self._service = service
        self._state = ReducerState()
        self._pending: list[TraceEventResponse] = []
        self._finalized = False

    @property
    def state(self) -> ReducerState:
        return self._state

    def on_event(self, ev: StreamEvent) -> None:
        """同步接收 event, 转 TraceEvent, 暂存到 _pending.

        reducer 抛错 → log warning, 跳过 event, 不影响 caller.
        """
        try:
            ctx = ReducerContext(
                turn_id=self._turn_id,
                session_id=self._session_id,
                scenario=self._scenario,
                state=self._state,
            )
            new_events = reduce_event(ev, ctx, self._state)
            self._pending.extend(new_events)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "work_trace_reduce_failed",
                turn_id=self._turn_id,
                event_type=ev.type,
                error=str(e),
            )

    async def flush(self) -> None:
        """把 _pending 写进 store; 失败仅 log, 不抛."""
        if not self._pending:
            return
        batch = self._pending
        self._pending = []
        try:
            await self._service.append(AppendTraceEventsRequest(
                turn_id=self._turn_id,
                session_id=self._session_id,
                scenario=self._scenario,
                status="running",
                events=batch,
            ))
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "work_trace_flush_failed",
                turn_id=self._turn_id,
                event_count=len(batch),
                error=str(e),
            )

    async def mark_done(self) -> None:
        await self._finalize("done")

    async def mark_suspended(self) -> None:
        """HITL flow only: turn 等待用户输入, trace 落到 suspended 状态."""
        await self._finalize("suspended")

    async def mark_error(self, message: str) -> None:
        with contextlib.suppress(Exception):
            self.on_event(StreamEvent.error(message=message))
        await self._finalize("error")

    async def _finalize(self, status: str) -> None:
        if self._finalized:
            return
        self._finalized = True
        await self.flush()
        try:
            await self._service.mark_status(
                self._turn_id,
                MarkTraceStatusRequest(status=status),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "work_trace_finalize_failed",
                turn_id=self._turn_id,
                status=status,
                error=str(e),
            )


__all__ = ["WorkTraceListener"]
