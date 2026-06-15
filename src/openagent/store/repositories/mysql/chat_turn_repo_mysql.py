"""MySQL ChatTurn Repository — Tortoise ORM 实现."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from openagent.store.models._common import utcnow
from openagent.store.models.chat_turn import ChatTurn
from openagent.store.repositories.chat_turn_repo import ChatTurnRepository


class MySQLChatTurnRepository(ChatTurnRepository):
    """单轮执行仓储 — Tortoise ORM (asyncmy) 实现."""

    async def get_by_id(self, entity_id: str) -> ChatTurn | None:
        return await ChatTurn.get_or_none(id=entity_id, is_deleted=False)

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[ChatTurn]:
        qs = ChatTurn.all()
        if not include_deleted:
            qs = qs.filter(is_deleted=False)
        for k in ("session_id", "status", "agent_name", "model"):
            if k in filters and filters[k] is not None:
                qs = qs.filter(**{k: filters[k]})
        return await qs.order_by("-created_at", "-id").offset(offset).limit(limit)

    async def count(
        self, *, include_deleted: bool = False, **filters: Any
    ) -> int:
        qs = ChatTurn.all()
        if not include_deleted:
            qs = qs.filter(is_deleted=False)
        for k in ("session_id", "status"):
            if k in filters and filters[k] is not None:
                qs = qs.filter(**{k: filters[k]})
        return await qs.count()

    async def create(self, model: ChatTurn) -> ChatTurn:
        await model.save()
        return model

    async def update(self, entity_id: str, **fields: Any) -> ChatTurn | None:
        if not fields:
            return await self.get_by_id(entity_id)
        await ChatTurn.filter(id=entity_id).update(**fields)
        return await self.get_by_id(entity_id)

    async def soft_delete(self, entity_id: str) -> bool:
        rc = await ChatTurn.filter(id=entity_id, is_deleted=False).update(
            is_deleted=True, deleted_at=utcnow(),
        )
        return rc > 0

    async def hard_delete(self, entity_id: str) -> bool:
        rc = await ChatTurn.filter(id=entity_id).delete()
        return rc > 0

    async def list_by_session(
        self,
        session_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
    ) -> list[ChatTurn]:
        return await self.list(
            session_id=session_id, status=status, limit=limit, offset=offset,
        )

    async def list_by_status(
        self,
        status: str,
        *,
        limit: int = 50,
        since: datetime | None = None,
    ) -> list[ChatTurn]:
        qs = ChatTurn.filter(status=status, is_deleted=False)
        if since is not None:
            qs = qs.filter(created_at__gte=since)
        return await qs.order_by("-created_at", "-id").limit(limit)

    async def mark_started(
        self, turn_id: str, when: datetime | None = None
    ) -> ChatTurn | None:
        ts = when or utcnow()
        rc = await ChatTurn.filter(id=turn_id, is_deleted=False).update(
            status="running", started_at=ts,
        )
        if rc == 0:
            return None
        return await self.get_by_id(turn_id)

    async def mark_finished(
        self,
        turn_id: str,
        status: str,
        *,
        finished_at: datetime | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> ChatTurn | None:
        ts = finished_at or utcnow()
        cur = await self.get_by_id(turn_id)
        duration_ms: int | None = None
        if cur and cur.started_at:
            duration_ms = int((ts - cur.started_at).total_seconds() * 1000)
        rc = await ChatTurn.filter(id=turn_id, is_deleted=False).update(
            status=status,
            finished_at=ts,
            duration_ms=duration_ms,
            error_code=error_code,
            error_message=error_message,
        )
        if rc == 0:
            return None
        return await self.get_by_id(turn_id)


__all__ = ["MySQLChatTurnRepository"]
