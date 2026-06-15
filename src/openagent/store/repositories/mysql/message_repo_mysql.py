"""MySQL Message Repository — Tortoise ORM 实现."""
from __future__ import annotations

from typing import Any

from openagent.store.models.message import Message
from openagent.store.repositories.message_repo import MessageRepository


class MySQLMessageRepository(MessageRepository):
    """消息仓储 — Tortoise ORM (asyncmy) 实现."""

    async def get_by_id(self, entity_id: str) -> Message | None:
        return await Message.get_or_none(id=entity_id, is_deleted=False)

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[Message]:
        qs = Message.all()
        if not include_deleted:
            qs = qs.filter(is_deleted=False)
        for k in ("session_id", "turn_id", "role"):
            if k in filters and filters[k] is not None:
                qs = qs.filter(**{k: filters[k]})
        return await qs.order_by("created_at", "id").offset(offset).limit(limit)

    async def count(
        self, *, include_deleted: bool = False, **filters: Any
    ) -> int:
        qs = Message.all()
        if not include_deleted:
            qs = qs.filter(is_deleted=False)
        for k in ("session_id", "turn_id", "role"):
            if k in filters and filters[k] is not None:
                qs = qs.filter(**{k: filters[k]})
        return await qs.count()

    async def create(self, model: Message) -> Message:
        await model.save()
        return model

    async def update(self, entity_id: str, **fields: Any) -> Message | None:
        if not fields:
            return await self.get_by_id(entity_id)
        await Message.filter(id=entity_id).update(**fields)
        return await self.get_by_id(entity_id)

    async def soft_delete(self, entity_id: str) -> bool:
        from openagent.store.models._common import utcnow

        rc = await Message.filter(id=entity_id, is_deleted=False).update(
            is_deleted=True, deleted_at=utcnow(),
        )
        return rc > 0

    async def hard_delete(self, entity_id: str) -> bool:
        rc = await Message.filter(id=entity_id).delete()
        return rc > 0

    async def list_by_session(
        self,
        session_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> list[Message]:
        return await self.list(
            session_id=session_id, limit=limit, offset=offset, include_deleted=include_deleted,
        )

    async def list_by_turn(self, turn_id: str) -> list[Message]:
        return await Message.filter(turn_id=turn_id, is_deleted=False).order_by(
            "created_at", "id",
        ).limit(10)


__all__ = ["MySQLMessageRepository"]
