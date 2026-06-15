"""MySQL Part Repository 实现."""

from __future__ import annotations

import json
from typing import Any

import structlog

from openagent.store.driver import MySQLPool
from openagent.store.models.part import Part
from openagent.store.repositories.part_repo import PartRepository

logger = structlog.get_logger(__name__)


class MySQLPartRepository(PartRepository):
    """消息分段仓储 — MySQL 实现."""

    def __init__(self, pool: MySQLPool) -> None:
        self._pool = pool

    async def get_by_id(self, entity_id: str) -> Part | None:
        row = await self._pool.fetch_one(
            "SELECT * FROM parts WHERE id=%s AND is_deleted=0", (entity_id,)
        )
        return Part.from_db_dict(row) if row else None

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[Part]:
        where = ["1=1"]
        params: list[Any] = []
        if not include_deleted:
            where.append("is_deleted=0")
        for k in ("message_id", "session_id", "part_type"):
            if k in filters and filters[k] is not None:
                where.append(f"{k}=%s")
                params.append(filters[k])
        sql = (
            "SELECT * FROM parts WHERE "
            + " AND ".join(where)
            + " ORDER BY created_at ASC, id ASC LIMIT %s OFFSET %s"
        )
        params.extend([limit, offset])
        rows = await self._pool.fetch_all(sql, tuple(params))
        return [Part.from_db_dict(r) for r in rows]

    async def count(
        self, *, include_deleted: bool = False, **filters: Any
    ) -> int:
        where = ["1=1"]
        params: list[Any] = []
        if not include_deleted:
            where.append("is_deleted=0")
        for k in ("message_id", "session_id", "part_type"):
            if k in filters and filters[k] is not None:
                where.append(f"{k}=%s")
                params.append(filters[k])
        sql = "SELECT COUNT(*) AS n FROM parts WHERE " + " AND ".join(where)
        row = await self._pool.fetch_one(sql, tuple(params))
        return int(row["n"]) if row else 0

    async def create(self, model: Part) -> Part:
        d = model.to_db_dict()
        cols = list(d.keys())
        placeholders = ", ".join(["%s"] * len(cols))
        col_sql = ", ".join(cols)
        await self._pool.execute(
            f"INSERT INTO parts ({col_sql}) VALUES ({placeholders})",
            tuple(d.values()),
        )
        logger.debug(
            "part_created",
            id=model.id,
            message_id=model.message_id,
            part_type=model.part_type,
        )
        return model

    async def update(self, entity_id: str, **fields: Any) -> Part | None:
        if not fields:
            return await self.get_by_id(entity_id)
        if "metadata" in fields and isinstance(fields["metadata"], (dict, list)):
            fields["metadata"] = json.dumps(fields["metadata"], ensure_ascii=False)
        set_clause = ", ".join(f"{k}=%s" for k in fields)
        params = list(fields.values()) + [entity_id]
        await self._pool.execute(
            f"UPDATE parts SET {set_clause}, updated_at=CURRENT_TIMESTAMP(6) WHERE id=%s",
            tuple(params),
        )
        return await self.get_by_id(entity_id)

    async def soft_delete(self, entity_id: str) -> bool:
        rc = await self._pool.execute(
            "UPDATE parts SET is_deleted=1, deleted_at=CURRENT_TIMESTAMP(6), "
            "updated_at=CURRENT_TIMESTAMP(6) WHERE id=%s AND is_deleted=0",
            (entity_id,),
        )
        return rc > 0

    async def hard_delete(self, entity_id: str) -> bool:
        rc = await self._pool.execute("DELETE FROM parts WHERE id=%s", (entity_id,))
        return rc > 0

    # ---------- 业务方法 ----------

    async def list_by_message(
        self, message_id: str, *, include_deleted: bool = False
    ) -> list[Part]:
        return await self.list(
            message_id=message_id, include_deleted=include_deleted, limit=1000
        )

    async def list_by_session(
        self,
        session_id: str,
        *,
        limit: int = 200,
        offset: int = 0,
        part_type: str | None = None,
    ) -> list[Part]:
        return await self.list(
            session_id=session_id, part_type=part_type, limit=limit, offset=offset
        )

    async def batch_create(self, parts: list[Part]) -> list[Part]:
        """批量 INSERT, 用 executemany 一次往返."""
        if not parts:
            return []
        first = parts[0]
        cols = list(first.to_db_dict().keys())
        placeholders = ", ".join(["%s"] * len(cols))
        col_sql = ", ".join(cols)
        params_list = [tuple(p.to_db_dict().values()) for p in parts]
        async with self._pool.acquire() as conn, conn.cursor() as cur:
            await cur.executemany(
                f"INSERT INTO parts ({col_sql}) VALUES ({placeholders})",
                params_list,
            )
        logger.debug("parts_batch_created", count=len(parts))
        return parts
