"""Memory ChatTurn Repository."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from openagent.store.models._common import utcnow
from openagent.store.models.chat_turn import ChatTurn
from openagent.store.repositories.chat_turn_repo import ChatTurnRepository
from openagent.store.repositories.memory._base import MemoryRepository


class MemoryChatTurnRepository(MemoryRepository[ChatTurn], ChatTurnRepository):
    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[ChatTurn]:
        items = list(self._store.values())
        if not include_deleted:
            items = [s for s in items if not s.is_deleted]
        for k in ("session_id", "status", "agent_name", "model"):
            if k in filters and filters[k] is not None:
                items = [s for s in items if getattr(s, k) == filters[k]]
        items.sort(key=lambda s: (s.created_at, s.id), reverse=True)
        return items[offset : offset + limit]

    async def count(
        self, *, include_deleted: bool = False, **filters: Any
    ) -> int:
        items = list(self._store.values())
        if not include_deleted:
            items = [s for s in items if not s.is_deleted]
        for k in ("session_id", "status"):
            if k in filters and filters[k] is not None:
                items = [s for s in items if getattr(s, k) == filters[k]]
        return len(items)

    async def list_by_session(
        self,
        session_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
    ) -> list[ChatTurn]:
        return await self.list(
            session_id=session_id, status=status, limit=limit, offset=offset
        )

    async def list_by_status(
        self,
        status: str,
        *,
        limit: int = 50,
        since: datetime | None = None,
    ) -> list[ChatTurn]:
        return await self.list(status=status, limit=limit)

    async def mark_started(
        self, turn_id: str, when: datetime | None = None
    ) -> ChatTurn | None:
        t = await self.get_by_id(turn_id)
        if t is None:
            return None
        t.status = "running"
        t.started_at = when or utcnow()
        return t

    async def mark_finished(
        self,
        turn_id: str,
        status: str,
        *,
        finished_at: datetime | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> ChatTurn | None:
        t = await self.get_by_id(turn_id)
        if t is None:
            return None
        ts = finished_at or utcnow()
        t.status = status
        t.finished_at = ts
        if t.started_at:
            t.duration_ms = int((ts - t.started_at).total_seconds() * 1000)
        if error_code:
            t.error_code = error_code
        if error_message:
            t.error_message = error_message
        return t
