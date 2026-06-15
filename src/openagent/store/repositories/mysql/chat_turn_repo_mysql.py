"""MySQL ChatTurn Repository 实现."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import structlog

from openagent.store.driver import MySQLPool
from openagent.store.models._common import utcnow
from openagent.store.models.chat_turn import ChatTurn
from openagent.store.repositories.chat_turn_repo import ChatTurnRepository

logger = structlog.get_logger(__name__)


class MySQLChatTurnRepository(ChatTurnRepository):
    """单轮执行仓储 — MySQL 实现."""

    def __init__(self, pool: MySQLPool) -> None:
        self._pool = pool

    async def get_by_id(self, entity_id: str) -> ChatTurn | None:
        row = await self._pool.fetch_one(
            "SELECT * FROM chat_turns WHERE id=%s AND is_deleted=0", (entity_id,)
        )
        return ChatTurn.from_db_dict(row) if row else None

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[ChatTurn]:
        where = ["1=1"]
        params: list[Any] = []
        if not include_deleted:
            where.append("is_deleted=0")
        for k in ("session_id", "status", "agent_name", "model"):
            if k in filters and filters[k] is not None:
                where.append(f"{k}=%s")
                params.append(filters[k])
        sql = (
            "SELECT * FROM chat_turns WHERE "
            + " AND ".join(where)
            + " ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s"
        )
        params.extend([limit, offset])
        rows = await self._pool.fetch_all(sql, tuple(params))
        return [ChatTurn.from_db_dict(r) for r in rows]

    async def count(
        self, *, include_deleted: bool = False, **filters: Any
    ) -> int:
        where = ["1=1"]
        params: list[Any] = []
        if not include_deleted:
            where.append("is_deleted=0")
        for k in ("session_id", "status"):
            if k in filters and filters[k] is not None:
                where.append(f"{k}=%s")
                params.append(filters[k])
        sql = "SELECT COUNT(*) AS n FROM chat_turns WHERE " + " AND ".join(where)
        row = await self._pool.fetch_one(sql, tuple(params))
        return int(row["n"]) if row else 0

    async def create(self, model: ChatTurn) -> ChatTurn:
        d = model.to_db_dict()
        cols = list(d.keys())
        placeholders = ", ".join(["%s"] * len(cols))
        col_sql = ", ".join(cols)
        await self._pool.execute(
            f"INSERT INTO chat_turns ({col_sql}) VALUES ({placeholders})",
            tuple(d.values()),
        )
        logger.debug("chat_turn_created", id=model.id, session_id=model.session_id)
        return model

    async def update(self, entity_id: str, **fields: Any) -> ChatTurn | None:
        if not fields:
            return await self.get_by_id(entity_id)
        if "metadata" in fields and isinstance(fields["metadata"], (dict, list)):
            fields["metadata"] = json.dumps(fields["metadata"], ensure_ascii=False)
        set_clause = ", ".join(f"{k}=%s" for k in fields)
        params = list(fields.values()) + [entity_id]
        await self._pool.execute(
            f"UPDATE chat_turns SET {set_clause}, updated_at=CURRENT_TIMESTAMP(6) WHERE id=%s",
            tuple(params),
        )
        return await self.get_by_id(entity_id)

    async def soft_delete(self, entity_id: str) -> bool:
        rc = await self._pool.execute(
            "UPDATE chat_turns SET is_deleted=1, deleted_at=CURRENT_TIMESTAMP(6), "
            "updated_at=CURRENT_TIMESTAMP(6) WHERE id=%s AND is_deleted=0",
            (entity_id,),
        )
        return rc > 0

    async def hard_delete(self, entity_id: str) -> bool:
        rc = await self._pool.execute(
            "DELETE FROM chat_turns WHERE id=%s", (entity_id,)
        )
        return rc > 0

    # ---------- 业务方法 ----------

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
        ts = when or utcnow()
        await self._pool.execute(
            "UPDATE chat_turns SET status='running', started_at=%s, "
            "updated_at=CURRENT_TIMESTAMP(6) WHERE id=%s",
            (ts, turn_id),
        )
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
        # duration_ms: started_at 存在时算
        cur = await self.get_by_id(turn_id)
        duration_ms: int | None = None
        if cur and cur.started_at:
            duration_ms = int((ts - cur.started_at).total_seconds() * 1000)
        await self._pool.execute(
            "UPDATE chat_turns SET status=%s, finished_at=%s, duration_ms=%s, "
            "error_code=%s, error_message=%s, updated_at=CURRENT_TIMESTAMP(6) "
            "WHERE id=%s",
            (status, ts, duration_ms, error_code, error_message, turn_id),
        )
        return await self.get_by_id(turn_id)
