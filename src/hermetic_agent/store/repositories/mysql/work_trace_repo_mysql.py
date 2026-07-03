"""MySQL WorkTrace Repository — Tortoise ORM implementation."""
from __future__ import annotations

from typing import Any

from hermetic_agent.store.dto.work_trace import (
    AppendTraceEventsRequest,
    MarkTraceStatusRequest,
    WorkTraceIndexItem,
    utc_iso,
)
from hermetic_agent.store.models._common import utcnow
from hermetic_agent.store.models.work_trace import TurnWorkTrace
from hermetic_agent.store.repositories.work_trace_repo import WorkTraceRepository


class MySQLWorkTraceRepository(WorkTraceRepository):
    """work_trace 的 MySQL 实现 (Tortoise ORM + asyncmy)."""

    def __init__(self) -> None:
        super().__init__()

    async def get_by_id(self, entity_id: str) -> TurnWorkTrace | None:
        return await TurnWorkTrace.get_or_none(turn_id=entity_id, is_deleted=False)

    async def list(
        self, *, limit: int = 50, offset: int = 0, **filters: Any,
    ) -> list[TurnWorkTrace]:
        qs = TurnWorkTrace.filter(is_deleted=False)
        if "session_id" in filters and filters["session_id"] is not None:
            qs = qs.filter(session_id=filters["session_id"])
        return await qs.order_by("-started_at").offset(offset).limit(limit)

    async def count(self, **filters: Any) -> int:
        qs = TurnWorkTrace.filter(is_deleted=False)
        if "session_id" in filters and filters["session_id"] is not None:
            qs = qs.filter(session_id=filters["session_id"])
        return await qs.count()

    async def create(self, model: TurnWorkTrace) -> TurnWorkTrace:
        await model.save()
        return model

    async def update(self, entity_id: str, **fields: Any) -> TurnWorkTrace | None:
        if not fields:
            return await self.get_by_id(entity_id)
        await TurnWorkTrace.filter(turn_id=entity_id).update(**fields)
        return await self.get_by_id(entity_id)

    async def soft_delete(self, entity_id: str) -> bool:
        rc = await TurnWorkTrace.filter(turn_id=entity_id, is_deleted=False).update(
            is_deleted=True, deleted_at=utcnow(),
        )
        return rc > 0

    async def hard_delete(self, entity_id: str) -> bool:
        rc = await TurnWorkTrace.filter(turn_id=entity_id).delete()
        return rc > 0

    async def append_events(self, req: AppendTraceEventsRequest) -> TurnWorkTrace:
        existing = await TurnWorkTrace.get_or_none(turn_id=req.turn_id, is_deleted=False)
        if existing is None:
            t = TurnWorkTrace(
                turn_id=req.turn_id,
                session_id=req.session_id,
                scenario=req.scenario,
                status=req.status or "running",
                started_at=utcnow(),
                summary=req.summary or {},
                events=[e.model_dump() for e in req.events],
            )
            await t.save()
            return t
        seen_seqs = {e["seq"] for e in (existing.events or [])}
        merged = list(existing.events or []) + [
            e.model_dump() for e in req.events if e.seq not in seen_seqs
        ]
        updates: dict[str, Any] = {"events": merged, "updated_at": utcnow()}
        if req.status and existing.status == "running":
            updates["status"] = req.status
        if req.summary:
            updates["summary"] = {**(existing.summary or {}), **req.summary}
        await TurnWorkTrace.filter(turn_id=req.turn_id).update(**updates)
        return await TurnWorkTrace.get(turn_id=req.turn_id)

    async def mark_status(
        self, turn_id: str, req: MarkTraceStatusRequest,
    ) -> TurnWorkTrace | None:
        updates: dict[str, Any] = {
            "status": req.status,
            "finished_at": req.finished_at or utcnow(),
            "updated_at": utcnow(),
        }
        if req.summary:
            existing = await TurnWorkTrace.get_or_none(turn_id=turn_id)
            if existing:
                updates["summary"] = {**(existing.summary or {}), **req.summary}
        rc = await TurnWorkTrace.filter(turn_id=turn_id, is_deleted=False).update(**updates)
        if rc == 0:
            return None
        return await TurnWorkTrace.get(turn_id=turn_id)

    async def get_by_turn(self, turn_id: str) -> TurnWorkTrace | None:
        return await TurnWorkTrace.get_or_none(turn_id=turn_id, is_deleted=False)

    async def list_by_session(
        self, session_id: str, *, limit: int = 20,
    ) -> list[WorkTraceIndexItem]:
        rows = await TurnWorkTrace.filter(
            session_id=session_id, is_deleted=False,
        ).order_by("-started_at").limit(limit)
        return [
            WorkTraceIndexItem(
                turn_id=str(r.turn_id),
                session_id=str(r.session_id),
                scenario=r.scenario,
                status=r.status,
                started_at=utc_iso(r.started_at),
                finished_at=utc_iso(r.finished_at),
                summary=r.summary or {},
            )
            for r in rows
        ]


__all__ = ["MySQLWorkTraceRepository"]
