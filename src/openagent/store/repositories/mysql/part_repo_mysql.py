"""MySQL Part Repository — Tortoise ORM 实现."""
from __future__ import annotations

from typing import Any

from openagent.store.models.part import Part
from openagent.store.repositories.part_repo import PartRepository


class MySQLPartRepository(PartRepository):
    """消息分段仓储 — Tortoise ORM (asyncmy) 实现."""

    async def get_by_id(self, entity_id: str) -> Part | None:
        return await Part.get_or_none(id=entity_id, is_deleted=False)

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[Part]:
        qs = Part.all()
        if not include_deleted:
            qs = qs.filter(is_deleted=False)
        for k in ("message_id", "session_id", "part_type"):
            if k in filters and filters[k] is not None:
                qs = qs.filter(**{k: filters[k]})
        return await qs.order_by("created_at", "id").offset(offset).limit(limit)

    async def count(
        self, *, include_deleted: bool = False, **filters: Any
    ) -> int:
        qs = Part.all()
        if not include_deleted:
            qs = qs.filter(is_deleted=False)
        for k in ("message_id", "session_id", "part_type"):
            if k in filters and filters[k] is not None:
                qs = qs.filter(**{k: filters[k]})
        return await qs.count()

    async def create(self, model: Part) -> Part:
        await model.save()
        return model

    async def update(self, entity_id: str, **fields: Any) -> Part | None:
        if not fields:
            return await self.get_by_id(entity_id)
        await Part.filter(id=entity_id).update(**fields)
        return await self.get_by_id(entity_id)

    async def soft_delete(self, entity_id: str) -> bool:
        from openagent.store.models._common import utcnow

        rc = await Part.filter(id=entity_id, is_deleted=False).update(
            is_deleted=True, deleted_at=utcnow(),
        )
        return rc > 0

    async def hard_delete(self, entity_id: str) -> bool:
        rc = await Part.filter(id=entity_id).delete()
        return rc > 0

    async def list_by_message(
        self, message_id: str, *, include_deleted: bool = False
    ) -> list[Part]:
        qs = Part.filter(message_id=message_id)
        if not include_deleted:
            qs = qs.filter(is_deleted=False)
        return await qs.order_by("position", "id").limit(1000)

    async def list_by_session(
        self,
        session_id: str,
        *,
        limit: int = 200,
        offset: int = 0,
        part_type: str | None = None,
    ) -> list[Part]:
        return await self.list(
            session_id=session_id, part_type=part_type, limit=limit, offset=offset,
        )

    async def batch_create(self, parts: list[Part]) -> list[Part]:
        """批量 INSERT. Tortoise ``Model.bulk_create`` 一次往返."""
        if not parts:
            return []
        await Part.bulk_create(parts)
        return parts


__all__ = ["MySQLPartRepository"]
