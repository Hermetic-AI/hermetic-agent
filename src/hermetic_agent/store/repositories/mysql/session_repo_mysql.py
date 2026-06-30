"""MySQL Session Repository — Tortoise ORM 实现."""
from __future__ import annotations

from typing import Any

from tortoise.expressions import F

from hermetic_agent.store.models.session import Session
from hermetic_agent.store.repositories.session_repo import SessionRepository


class MySQLSessionRepository(SessionRepository):
    """会话仓储 — Tortoise ORM (asyncmy) 实现."""

    async def get_by_id(self, entity_id: str) -> Session | None:
        return await Session.get_or_none(id=entity_id, is_deleted=False)

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[Session]:
        qs = Session.all()
        if not include_deleted:
            qs = qs.filter(is_deleted=False)
        for k in ("user_id", "agent_name", "scenario_id", "status", "model"):
            if k in filters and filters[k] is not None:
                qs = qs.filter(**{k: filters[k]})
        return await qs.order_by("-updated_at", "-id").offset(offset).limit(limit)

    async def count(
        self, *, include_deleted: bool = False, **filters: Any
    ) -> int:
        qs = Session.all()
        if not include_deleted:
            qs = qs.filter(is_deleted=False)
        for k in ("user_id", "agent_name", "scenario_id", "status", "model"):
            if k in filters and filters[k] is not None:
                qs = qs.filter(**{k: filters[k]})
        return await qs.count()

    async def create(self, model: Session) -> Session:
        await model.save()
        return model

    async def update(self, entity_id: str, **fields: Any) -> Session | None:
        if not fields:
            return await self.get_by_id(entity_id)
        await Session.filter(id=entity_id).update(**fields)
        return await self.get_by_id(entity_id)

    async def soft_delete(self, entity_id: str) -> bool:
        from hermetic_agent.store.models._common import utcnow

        rc = await Session.filter(id=entity_id, is_deleted=False).update(
            is_deleted=True, deleted_at=utcnow(),
        )
        return rc > 0

    async def hard_delete(self, entity_id: str) -> bool:
        rc = await Session.filter(id=entity_id).delete()
        return rc > 0

    async def list_by_user(
        self,
        user_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> list[Session]:
        return await self.list(
            user_id=user_id, limit=limit, offset=offset, include_deleted=include_deleted,
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
        """增量更新 session 聚合字段.

        业务规则: ``message_count`` 绝对值覆盖, 其他 ``+=`` 增量.
        用 Tortoise ``F()`` 表达式做原子累加 (SQL 层 ``col = col + %s``).
        """
        sets: dict[str, Any] = {}
        if message_count is not None:
            sets["message_count"] = int(message_count)
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
            sets[col] = F(col) + delta
        if not sets:
            return await self.get_by_id(session_id)
        await Session.filter(id=session_id).update(**sets)
        return await self.get_by_id(session_id)


__all__ = ["MySQLSessionRepository"]
