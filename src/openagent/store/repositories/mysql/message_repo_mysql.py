"""MySQL Message Repository 实现."""

from __future__ import annotations

import json
from typing import Any

import structlog

from openagent.store.driver import MySQLPool
from openagent.store.models.message import Message
from openagent.store.repositories.message_repo import MessageRepository

logger = structlog.get_logger(__name__)


class MySQLMessageRepository(MessageRepository):
    """消息仓储 — MySQL 实现."""

    def __init__(self, pool: MySQLPool) -> None:
        self._pool = pool

    async def get_by_id(self, entity_id: str) -> Message | None:
        row = await self._pool.fetch_one(
            "SELECT * FROM messages WHERE id=%s AND is_deleted=0", (entity_id,)
        )
        return Message.from_db_dict(row) if row else None

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[Message]:
        where = ["1=1"]
        params: list[Any] = []
        if not include_deleted:
            where.append("is_deleted=0")
        for k in ("session_id", "turn_id", "role"):
            if k in filters and filters[k] is not None:
                where.append(f"{k}=%s")
                params.append(filters[k])
        sql = (
            "SELECT * FROM messages WHERE "
            + " AND ".join(where)
            + " ORDER BY created_at ASC, id ASC LIMIT %s OFFSET %s"
        )
        params.extend([limit, offset])
        rows = await self._pool.fetch_all(sql, tuple(params))
        return [Message.from_db_dict(r) for r in rows]

    async def count(
        self, *, include_deleted: bool = False, **filters: Any
    ) -> int:
        where = ["1=1"]
        params: list[Any] = []
        if not include_deleted:
            where.append("is_deleted=0")
        for k in ("session_id", "turn_id", "role"):
            if k in filters and filters[k] is not None:
                where.append(f"{k}=%s")
                params.append(filters[k])
        sql = "SELECT COUNT(*) AS n FROM messages WHERE " + " AND ".join(where)
        row = await self._pool.fetch_one(sql, tuple(params))
        return int(row["n"]) if row else 0

    async def create(self, model: Message) -> Message:
        d = model.to_db_dict()
        cols = list(d.keys())
        placeholders = ", ".join(["%s"] * len(cols))
        col_sql = ", ".join(cols)
        await self._pool.execute(
            f"INSERT INTO messages ({col_sql}) VALUES ({placeholders})",
            tuple(d.values()),
        )
        logger.debug("message_created", id=model.id, session_id=model.session_id, role=model.role)
        return model

    async def update(self, entity_id: str, **fields: Any) -> Message | None:
        if not fields:
            return await self.get_by_id(entity_id)
        if "metadata" in fields and isinstance(fields["metadata"], (dict, list)):
            fields["metadata"] = json.dumps(fields["metadata"], ensure_ascii=False)
        set_clause = ", ".join(f"{k}=%s" for k in fields)
        params = list(fields.values()) + [entity_id]
        await self._pool.execute(
            f"UPDATE messages SET {set_clause}, updated_at=CURRENT_TIMESTAMP(6) WHERE id=%s",
            tuple(params),
        )
        return await self.get_by_id(entity_id)

    async def soft_delete(self, entity_id: str) -> bool:
        rc = await self._pool.execute(
            "UPDATE messages SET is_deleted=1, deleted_at=CURRENT_TIMESTAMP(6), "
            "updated_at=CURRENT_TIMESTAMP(6) WHERE id=%s AND is_deleted=0",
            (entity_id,),
        )
        return rc > 0

    async def hard_delete(self, entity_id: str) -> bool:
        rc = await self._pool.execute("DELETE FROM messages WHERE id=%s", (entity_id,))
        return rc > 0

    # ---------- 业务方法 ----------

    async def list_by_session(
        self,
        session_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> list[Message]:
        return await self.list(
            session_id=session_id, limit=limit, offset=offset, include_deleted=include_deleted
        )

    async def list_by_turn(self, turn_id: str) -> list[Message]:
        return await self.list(turn_id=turn_id, limit=10)
