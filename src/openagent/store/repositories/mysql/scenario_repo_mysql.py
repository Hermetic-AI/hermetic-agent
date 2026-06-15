"""MySQL Scenario Repository 实现."""

from __future__ import annotations

import json
from typing import Any

import structlog

from openagent.store.driver import MySQLPool
from openagent.store.models.scenario import Scenario
from openagent.store.repositories.scenario_repo import ScenarioRepository

logger = structlog.get_logger(__name__)


class MySQLScenarioRepository(ScenarioRepository):
    """场景仓储 — MySQL 实现."""

    def __init__(self, pool: MySQLPool) -> None:
        self._pool = pool

    # ---------- 基本 CRUD ----------

    async def get_by_id(self, entity_id: str) -> Scenario | None:
        row = await self._pool.fetch_one(
            "SELECT * FROM scenarios WHERE id=%s AND is_deleted=0", (entity_id,)
        )
        return Scenario.from_db_dict(row) if row else None

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[Scenario]:
        where = ["1=1"]
        params: list[Any] = []
        if not include_deleted:
            where.append("is_deleted=0")
        for k in ("code", "status", "source", "parent_id"):
            if k in filters and filters[k] is not None:
                where.append(f"{k}=%s")
                params.append(filters[k])
        sql = (
            "SELECT * FROM scenarios WHERE "
            + " AND ".join(where)
            + " ORDER BY updated_at DESC, id DESC LIMIT %s OFFSET %s"
        )
        params.extend([limit, offset])
        rows = await self._pool.fetch_all(sql, tuple(params))
        return [Scenario.from_db_dict(r) for r in rows]

    async def count(
        self, *, include_deleted: bool = False, **filters: Any
    ) -> int:
        where = ["1=1"]
        params: list[Any] = []
        if not include_deleted:
            where.append("is_deleted=0")
        for k in ("code", "status", "source", "parent_id"):
            if k in filters and filters[k] is not None:
                where.append(f"{k}=%s")
                params.append(filters[k])
        sql = "SELECT COUNT(*) AS n FROM scenarios WHERE " + " AND ".join(where)
        row = await self._pool.fetch_one(sql, tuple(params))
        return int(row["n"]) if row else 0

    async def create(self, model: Scenario) -> Scenario:
        d = model.to_db_dict()
        cols = list(d.keys())
        placeholders = ", ".join(["%s"] * len(cols))
        col_sql = ", ".join(cols)
        await self._pool.execute(
            f"INSERT INTO scenarios ({col_sql}) VALUES ({placeholders})",
            tuple(d.values()),
        )
        logger.debug("scenario_created", id=model.id, code=model.code, version=model.version)
        return model

    async def update(self, entity_id: str, **fields: Any) -> Scenario | None:
        if not fields:
            return await self.get_by_id(entity_id)
        # dict 字段要 json.dumps
        if "config" in fields and isinstance(fields["config"], (dict, list)):
            fields["config"] = json.dumps(fields["config"], ensure_ascii=False)
        set_clause = ", ".join(f"{k}=%s" for k in fields)
        params = list(fields.values()) + [entity_id]
        await self._pool.execute(
            f"UPDATE scenarios SET {set_clause}, updated_at=CURRENT_TIMESTAMP(6) WHERE id=%s",
            tuple(params),
        )
        return await self.get_by_id(entity_id)

    async def soft_delete(self, entity_id: str) -> bool:
        rc = await self._pool.execute(
            "UPDATE scenarios SET is_deleted=1, deleted_at=CURRENT_TIMESTAMP(6), "
            "updated_at=CURRENT_TIMESTAMP(6) WHERE id=%s AND is_deleted=0",
            (entity_id,),
        )
        return rc > 0

    async def hard_delete(self, entity_id: str) -> bool:
        rc = await self._pool.execute(
            "DELETE FROM scenarios WHERE id=%s", (entity_id,)
        )
        return rc > 0

    # ---------- 业务方法 ----------

    async def get_by_code_version(self, code: str, version: int) -> Scenario | None:
        row = await self._pool.fetch_one(
            "SELECT * FROM scenarios WHERE code=%s AND version=%s AND is_deleted=0",
            (code, version),
        )
        return Scenario.from_db_dict(row) if row else None

    async def list_active(self, *, limit: int = 100) -> list[Scenario]:
        return await self.list(status="enabled", limit=limit)

    async def create_new_version(
        self, parent: Scenario, new_config: dict[str, Any], new_name: str | None = None
    ) -> Scenario:
        """基于父版本创建新版本(同 code, version+1, parent_id 指向父)."""
        new = Scenario(
            code=parent.code,
            name=new_name or parent.name,
            version=parent.version + 1,
            parent_id=parent.id,
            config=new_config,
            source=parent.source,
            status="draft",
        )
        return await self.create(new)
