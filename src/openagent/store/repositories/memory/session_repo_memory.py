"""Memory Session Repository."""

from __future__ import annotations

from typing import Any

from openagent.store.models.session import Session
from openagent.store.repositories.memory._base import MemoryRepository
from openagent.store.repositories.session_repo import SessionRepository


class MemorySessionRepository(MemoryRepository[Session], SessionRepository):
    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[Session]:
        items = list(self._store.values())
        if not include_deleted:
            items = [s for s in items if not s.is_deleted]
        for k in ("user_id", "agent_name", "scenario_id", "status", "model"):
            if k in filters and filters[k] is not None:
                items = [s for s in items if getattr(s, k) == filters[k]]
        items.sort(key=lambda s: (s.updated_at, s.id), reverse=True)
        return items[offset : offset + limit]

    async def count(
        self, *, include_deleted: bool = False, **filters: Any
    ) -> int:
        items = list(self._store.values())
        if not include_deleted:
            items = [s for s in items if not s.is_deleted]
        for k in ("user_id", "agent_name", "scenario_id", "status"):
            if k in filters and filters[k] is not None:
                items = [s for s in items if getattr(s, k) == filters[k]]
        return len(items)

    async def list_by_user(
        self,
        user_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> list[Session]:
        return await self.list(
            user_id=user_id, limit=limit, offset=offset, include_deleted=include_deleted
        )

    async def list_by_scenario(
        self, scenario_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[Session]:
        return await self.list(scenario_id=scenario_id, limit=limit, offset=offset)

    async def update_aggregates(
        self,
        session_id: str,
        *,
        message_count: int | None = None,
        cost_delta: float | None = None,
        tokens_input_delta: int | None = None,
        tokens_output_delta: int | None = None,
        tokens_reasoning_delta: int | None = None,
        tokens_cache_read_delta: int | None = None,
        tokens_cache_write_delta: int | None = None,
    ) -> Session | None:
        s = await self.get_by_id(session_id)
        if s is None:
            return None
        if message_count is not None:
            s.message_count = int(message_count)
        if cost_delta is not None:
            s.cost = s.cost + float(cost_delta)
        for attr, delta in (
            ("tokens_input", tokens_input_delta),
            ("tokens_output", tokens_output_delta),
            ("tokens_reasoning", tokens_reasoning_delta),
            ("tokens_cache_read", tokens_cache_read_delta),
            ("tokens_cache_write", tokens_cache_write_delta),
        ):
            if delta is not None:
                setattr(s, attr, getattr(s, attr) + int(delta))
        s.updated_at = s.updated_at  # type: ignore[assignment]
        return s
