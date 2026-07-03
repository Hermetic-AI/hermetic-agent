"""Memory WorkTrace Repository — dict-backed implementation."""
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
from hermetic_agent.store.repositories.memory._base import MemoryRepository
from hermetic_agent.store.repositories.work_trace_repo import WorkTraceRepository


class MemoryWorkTraceRepository(MemoryRepository[TurnWorkTrace], WorkTraceRepository):
    """work_trace 的内存实现 — 继承 MemoryRepository 复用 CRUD 基类."""

    def __init__(self) -> None:
        super().__init__()

    async def create(self, model: TurnWorkTrace) -> TurnWorkTrace:
        """``TurnWorkTrace`` 用 ``turn_id`` (UUID) 作 PK; override 基类的 ``id`` 检查."""
        eid = getattr(model, "turn_id", None)
        if not eid:
            raise ValueError("TurnWorkTrace must have turn_id")
        self._store[str(eid)] = model
        return model

    async def append_events(self, req: AppendTraceEventsRequest) -> TurnWorkTrace:
        existing = await self.get_by_turn(req.turn_id)
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
            return await self.create(t)
        # append to existing (idempotent: dedup by seq)
        seen_seqs = {e["seq"] for e in (existing.events or [])}
        merged_events = list(existing.events or []) + [
            e.model_dump() for e in req.events if e.seq not in seen_seqs
        ]
        existing.events = merged_events
        if req.status and existing.status == "running":
            existing.status = req.status
        if req.summary:
            existing.summary = {**(existing.summary or {}), **req.summary}
        existing.updated_at = utcnow()
        return existing

    async def mark_status(
        self, turn_id: str, req: MarkTraceStatusRequest
    ) -> TurnWorkTrace | None:
        t = await self.get_by_turn(entity_id=turn_id)
        if t is None:
            return None
        t.status = req.status
        t.finished_at = req.finished_at or utcnow()
        if req.summary:
            t.summary = {**(t.summary or {}), **req.summary}
        t.updated_at = utcnow()
        return t

    async def get_by_id(self, entity_id: str) -> TurnWorkTrace | None:
        """PK 字段名 = ``turn_id``; override 基类按 ``id`` 找的逻辑."""
        target = str(entity_id) if entity_id is not None else entity_id
        for k, m in self._store.items():
            if str(k) == target and not getattr(m, "is_deleted", False):
                return m
        return None

    async def update(self, entity_id: str, **fields: Any) -> TurnWorkTrace | None:
        m = self._store.get(str(entity_id))
        if m is None or getattr(m, "is_deleted", False):
            return None
        for k, v in fields.items():
            setattr(m, k, v)
        if hasattr(m, "updated_at"):
            m.updated_at = utcnow()
        return m

    async def soft_delete(self, entity_id: str) -> bool:
        m = self._store.get(str(entity_id))
        if m is None or getattr(m, "is_deleted", False):
            return False
        m.is_deleted = True
        m.deleted_at = utcnow()
        if hasattr(m, "updated_at"):
            m.updated_at = utcnow()
        return True

    async def hard_delete(self, entity_id: str) -> bool:
        return self._store.pop(str(entity_id), None) is not None

    async def get_by_turn(self, entity_id: str) -> TurnWorkTrace | None:
        return await self.get_by_id(entity_id)

    async def list_by_session(
        self, session_id: str, *, limit: int = 20
    ) -> list[WorkTraceIndexItem]:
        target = str(session_id)
        items = [
            m for m in self._store.values()
            if str(m.session_id) == target and not m.is_deleted
        ]
        items.sort(key=lambda m: (m.started_at or m.created_at), reverse=True)
        return [
            WorkTraceIndexItem(
                turn_id=str(m.turn_id),
                session_id=str(m.session_id),
                scenario=m.scenario,
                status=m.status,
                started_at=utc_iso(m.started_at),
                finished_at=utc_iso(m.finished_at),
                summary=m.summary or {},
            )
            for m in items[:limit]
        ]

    async def list(self, *, limit: int = 50, offset: int = 0, **filters: Any) -> list[TurnWorkTrace]:
        items = [m for m in self._store.values() if not m.is_deleted]
        if "session_id" in filters:
            target = str(filters["session_id"])
            items = [m for m in items if str(m.session_id) == target]
        items.sort(key=lambda m: m.created_at, reverse=True)
        return items[offset:offset + limit]

    async def count(self, **filters: Any) -> int:
        items = [m for m in self._store.values() if not m.is_deleted]
        if "session_id" in filters:
            target = str(filters["session_id"])
            items = [m for m in items if str(m.session_id) == target]
        return len(items)


__all__ = ["MemoryWorkTraceRepository"]
