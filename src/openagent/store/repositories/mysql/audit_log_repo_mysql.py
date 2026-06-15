"""MySQL AuditLog Repository — Tortoise ORM 实现 (append-only)."""
from __future__ import annotations

from typing import Any

from openagent.store.models.audit_log import AuditLog
from openagent.store.repositories.audit_log_repo import AuditLogRepository


class MySQLAuditLogRepository(AuditLogRepository):
    """审计日志仓储 — Tortoise ORM (asyncmy) 实现 (append-only)."""

    async def get_by_id(self, entity_id: str) -> AuditLog | None:
        return await AuditLog.get_or_none(id=entity_id)

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[AuditLog]:
        qs = AuditLog.all()
        for k in ("actor_type", "actor_id", "action", "resource_type", "resource_id", "request_id"):
            if k in filters and filters[k] is not None:
                qs = qs.filter(**{k: filters[k]})
        return await qs.order_by("-created_at", "-id").offset(offset).limit(limit)

    async def count(
        self, *, include_deleted: bool = False, **filters: Any
    ) -> int:
        qs = AuditLog.all()
        for k in ("actor_type", "actor_id", "action", "resource_type", "resource_id"):
            if k in filters and filters[k] is not None:
                qs = qs.filter(**{k: filters[k]})
        return await qs.count()

    async def create(self, model: AuditLog) -> AuditLog:
        await model.save()
        return model

    async def update(self, entity_id: str, **fields: Any) -> AuditLog | None:
        raise NotImplementedError("AuditLog is append-only; update() not allowed")

    async def soft_delete(self, entity_id: str) -> bool:
        raise NotImplementedError("AuditLog is append-only; soft_delete() not allowed")

    async def hard_delete(self, entity_id: str) -> bool:
        raise NotImplementedError("AuditLog is append-only; hard_delete() not allowed")

    async def list_by_resource(
        self,
        resource_type: str,
        resource_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]:
        return await self.list(
            resource_type=resource_type,
            resource_id=resource_id,
            limit=limit,
            offset=offset,
        )

    async def list_by_actor(
        self,
        actor_type: str,
        actor_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]:
        return await self.list(
            actor_type=actor_type,
            actor_id=actor_id,
            limit=limit,
            offset=offset,
        )

    async def next_seq(self, resource_type: str, resource_id: str) -> int:
        """同资源下 +1 序号. 用 ``COALESCE(MAX(seq), 0) + 1`` 原子取."""
        from tortoise.functions import Coalesce, Max

        row = await AuditLog.filter(
            resource_type=resource_type, resource_id=resource_id,
        ).annotate(seq_max=Coalesce(Max("seq"), 0)).values("seq_max")
        if not row:
            return 1
        return int(row[0]["seq_max"]) + 1


__all__ = ["MySQLAuditLogRepository"]
