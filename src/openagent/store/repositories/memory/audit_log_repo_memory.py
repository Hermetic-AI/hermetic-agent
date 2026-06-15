"""Memory AuditLog Repository (append-only)."""

from __future__ import annotations

from typing import Any

from openagent.store.models.audit_log import AuditLog
from openagent.store.repositories.audit_log_repo import AuditLogRepository


class MemoryAuditLogRepository(AuditLogRepository):
    """内存版审计日志(append-only, 不支持 update / delete)."""

    def __init__(self) -> None:
        self._store: dict[str, AuditLog] = {}

    async def get_by_id(self, entity_id: str) -> AuditLog | None:
        return self._store.get(entity_id)

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[AuditLog]:
        items = list(self._store.values())
        for k in ("actor_type", "actor_id", "action", "resource_type", "resource_id", "request_id"):
            if k in filters and filters[k] is not None:
                items = [s for s in items if getattr(s, k) == filters[k]]
        items.sort(key=lambda s: (s.created_at, s.id), reverse=True)
        return items[offset : offset + limit]

    async def count(
        self, *, include_deleted: bool = False, **filters: Any
    ) -> int:
        items = list(self._store.values())
        for k in ("actor_type", "action", "resource_type"):
            if k in filters and filters[k] is not None:
                items = [s for s in items if getattr(s, k) == filters[k]]
        return len(items)

    async def create(self, model: AuditLog) -> AuditLog:
        self._store[model.id] = model
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
            resource_type=resource_type, resource_id=resource_id, limit=limit, offset=offset
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
            actor_type=actor_type, actor_id=actor_id, limit=limit, offset=offset
        )

    async def next_seq(self, resource_type: str, resource_id: str) -> int:
        target = str(resource_id)
        items = [
            s
            for s in self._store.values()
            if s.resource_type == resource_type and str(s.resource_id) == target
        ]
        max_seq = max((s.seq or 0) for s in items) if items else 0
        return max_seq + 1

    def clear(self) -> None:
        self._store.clear()
