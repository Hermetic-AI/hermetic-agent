"""MySQL Session Repository 实现."""

from __future__ import annotations

import json
from typing import Any

import structlog

from openagent.store.driver import MySQLPool
from openagent.store.models.session import Session
from openagent.store.repositories.session_repo import SessionRepository

logger = structlog.get_logger(__name__)


class MySQLSessionRepository(SessionRepository):
    """会话仓储 — MySQL 实现(含 token/cost 聚合)."""

    def __init__(self, pool: MySQLPool) -> None:
        self._pool = pool

    async def get_by_id(self, entity_id: str) -> Session | None:
        row = await self._pool.fetch_one(
            "SELECT * FROM sessions WHERE id=%s AND is_deleted=0", (entity_id,)
        )
        return Session.from_db_dict(row) if row else None

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[Session]:
        where = ["1=1"]
        params: list[Any] = []
        if not include_deleted:
            where.append("is_deleted=0")
        for k in ("user_id", "agent_name", "scenario_id", "status", "model"):
            if k in filters and filters[k] is not None:
                where.append(f"{k}=%s")
                params.append(filters[k])
        sql = (
            "SELECT * FROM sessions WHERE "
            + " AND ".join(where)
            + " ORDER BY updated_at DESC, id DESC LIMIT %s OFFSET %s"
        )
        params.extend([limit, offset])
        rows = await self._pool.fetch_all(sql, tuple(params))
        return [Session.from_db_dict(r) for r in rows]

    async def count(
        self, *, include_deleted: bool = False, **filters: Any
    ) -> int:
        where = ["1=1"]
        params: list[Any] = []
        if not include_deleted:
            where.append("is_deleted=0")
        for k in ("user_id", "agent_name", "scenario_id", "status", "model"):
            if k in filters and filters[k] is not None:
                where.append(f"{k}=%s")
                params.append(filters[k])
        sql = "SELECT COUNT(*) AS n FROM sessions WHERE " + " AND ".join(where)
        row = await self._pool.fetch_one(sql, tuple(params))
        return int(row["n"]) if row else 0

    async def create(self, model: Session) -> Session:
        d = model.to_db_dict()
        cols = list(d.keys())
        placeholders = ", ".join(["%s"] * len(cols))
        col_sql = ", ".join(cols)
        await self._pool.execute(
            f"INSERT INTO sessions ({col_sql}) VALUES ({placeholders})",
            tuple(d.values()),
        )
        logger.debug("session_created", id=model.id, user_id=model.user_id)
        return model

    async def update(self, entity_id: str, **fields: Any) -> Session | None:
        if not fields:
            return await self.get_by_id(entity_id)
        if "metadata" in fields and isinstance(fields["metadata"], (dict, list)):
            fields["metadata"] = json.dumps(fields["metadata"], ensure_ascii=False)
        set_clause = ", ".join(f"{k}=%s" for k in fields)
        params = list(fields.values()) + [entity_id]
        await self._pool.execute(
            f"UPDATE sessions SET {set_clause}, updated_at=CURRENT_TIMESTAMP(6) WHERE id=%s",
            tuple(params),
        )
        return await self.get_by_id(entity_id)

    async def soft_delete(self, entity_id: str) -> bool:
        rc = await self._pool.execute(
            "UPDATE sessions SET is_deleted=1, deleted_at=CURRENT_TIMESTAMP(6), "
            "updated_at=CURRENT_TIMESTAMP(6) WHERE id=%s AND is_deleted=0",
            (entity_id,),
        )
        return rc > 0

    async def hard_delete(self, entity_id: str) -> bool:
        rc = await self._pool.execute("DELETE FROM sessions WHERE id=%s", (entity_id,))
        return rc > 0

    # ---------- 业务方法 ----------

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
        """增量更新 session 聚合字段. 业务规则:

        - ``message_count`` 是绝对值覆盖
        - 其他是 += 增量
        """
        sets: list[str] = []
        params: list[Any] = []
        if message_count is not None:
            sets.append("message_count=%s")
            params.append(int(message_count))
        for col, delta in (
            ("cost", cost_delta),
            ("tokens_input", tokens_input_delta),
            ("tokens_output", tokens_output_delta),
            ("tokens_reasoning", tokens_reasoning_delta),
            ("tokens_cache_read", tokens_cache_read_delta),
            ("tokens_cache_write", tokens_cache_write_delta),
        ):
            if delta is None:
                continue
            sets.append(f"{col}={col}+%s")
            params.append(delta)
        if not sets:
            return await self.get_by_id(session_id)
        sets.append("updated_at=CURRENT_TIMESTAMP(6)")
        params.append(session_id)
        sql = f"UPDATE sessions SET {', '.join(sets)} WHERE id=%s"
        await self._pool.execute(sql, tuple(params))
        return await self.get_by_id(session_id)
