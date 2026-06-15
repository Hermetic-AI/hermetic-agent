"""MySQL AuditLog Repository 实现."""

from __future__ import annotations

from typing import Any

import structlog

from openagent.store.driver import MySQLPool
from openagent.store.models.audit_log import AuditLog
from openagent.store.repositories.audit_log_repo import AuditLogRepository

logger = structlog.get_logger(__name__)


class MySQLAuditLogRepository(AuditLogRepository):
    """审计日志仓储 — MySQL 实现(append-only)."""

    def __init__(self, pool: MySQLPool) -> None:
        self._pool = pool

    async def get_by_id(self, entity_id: str) -> AuditLog | None:
        row = await self._pool.fetch_one(
            "SELECT * FROM audit_logs WHERE id=%s", (entity_id,)
        )
        return AuditLog.from_db_dict(row) if row else None

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[AuditLog]:
        where = ["1=1"]
        params: list[Any] = []
        for k in ("actor_type", "actor_id", "action", "resource_type", "resource_id", "request_id"):
            if k in filters and filters[k] is not None:
                where.append(f"{k}=%s")
                params.append(filters[k])
        sql = (
            "SELECT * FROM audit_logs WHERE "
            + " AND ".join(where)
            + " ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s"
        )
        params.extend([limit, offset])
        rows = await self._pool.fetch_all(sql, tuple(params))
        return [AuditLog.from_db_dict(r) for r in rows]

    async def count(
        self, *, include_deleted: bool = False, **filters: Any
    ) -> int:
        where = ["1=1"]
        params: list[Any] = []
        for k in ("actor_type", "actor_id", "action", "resource_type", "resource_id"):
            if k in filters and filters[k] is not None:
                where.append(f"{k}=%s")
                params.append(filters[k])
        sql = "SELECT COUNT(*) AS n FROM audit_logs WHERE " + " AND ".join(where)
        row = await self._pool.fetch_one(sql, tuple(params))
        return int(row["n"]) if row else 0

    async def create(self, model: AuditLog) -> AuditLog:
        # append-only: 不支持 update / soft_delete / hard_delete 走 base 抛错
        d = model.to_db_dict()
        cols = list(d.keys())
        placeholders = ", ".join(["%s"] * len(cols))
        col_sql = ", ".join(cols)
        await self._pool.execute(
            f"INSERT INTO audit_logs ({col_sql}) VALUES ({placeholders})",
            tuple(d.values()),
        )
        logger.debug("audit_log_created", id=model.id, action=model.action, resource=model.resource_type)
        return model

    async def update(self, entity_id: str, **fields: Any) -> AuditLog | None:
        raise NotImplementedError("AuditLog is append-only; update() not allowed")

    async def soft_delete(self, entity_id: str) -> bool:
        raise NotImplementedError("AuditLog is append-only; soft_delete() not allowed")

    async def hard_delete(self, entity_id: str) -> bool:
        raise NotImplementedError("AuditLog is append-only; hard_delete() not allowed")

    # ---------- 业务方法 ----------

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
        """同资源下 +1 序号. 用 ``COALESCE(MAX(seq), 0) + 1`` 原子取.

        业务可接受轻微并发竞争(同 resource 多 writer 时 seq 顺序不严格保证);
        严格顺序需借助 ``SELECT ... FOR UPDATE`` + 事务, 此处简化为单连接.
        """
        row = await self._pool.fetch_one(
            "SELECT COALESCE(MAX(seq), 0) + 1 AS n FROM audit_logs "
            "WHERE resource_type=%s AND resource_id=%s",
            (resource_type, resource_id),
        )
        return int(row["n"]) if row else 1
