"""SessionService — 会话的业务编排."""

from __future__ import annotations

from typing import Any

import structlog

from hermetic_agent.store.dto.session import (
    CreateSessionRequest,
    SessionResponse,
    UpdateSessionRequest,
)
from hermetic_agent.store.exceptions import NotFoundError
from hermetic_agent.store.models.session import Session
from hermetic_agent.store.repositories.session_repo import SessionRepository
from hermetic_agent.store.services.audit_log_service import AuditLogService

logger = structlog.get_logger(__name__)


class SessionService:
    """会话服务."""

    def __init__(
        self,
        repo: SessionRepository,
        audit: AuditLogService,
    ) -> None:
        self._repo = repo
        self._audit = audit

    # ---------- 查询 ----------

    async def get_by_id(self, session_id: str) -> Session:
        s = await self._repo.get_by_id(session_id)
        if s is None:
            raise NotFoundError("session", session_id)
        return s

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        user_id: str | None = None,
        agent_name: str | None = None,
        scenario_id: str | None = None,
        status: str | None = None,
    ) -> list[Session]:
        return await self._repo.list(
            limit=limit,
            offset=offset,
            include_deleted=include_deleted,
            user_id=user_id,
            agent_name=agent_name,
            scenario_id=scenario_id,
            status=status,
        )

    async def list_by_user(
        self, user_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[Session]:
        return await self._repo.list_by_user(user_id, limit=limit, offset=offset)

    # ---------- 创建 ----------

    async def create(
        self,
        req: CreateSessionRequest,
        *,
        actor_id: str | None = None,
    ) -> Session:
        s = Session(
            user_id=req.user_id,
            title=req.title,
            model=req.model,
            agent_name=req.agent_name,
            scenario_id=req.scenario_id,
            status=req.status,
            metadata=req.metadata,
        )
        s = await self._repo.create(s)
        await self._audit.record(
            actor_type="user",
            actor_id=actor_id,
            action="create",
            resource_type="session",
            resource_id=s.id,
            after_data={
                "title": s.title,
                "agent_name": s.agent_name,
                "user_id": s.user_id,
            },
        )
        return s

    # ---------- 更新 ----------

    async def update(
        self,
        session_id: str,
        req: UpdateSessionRequest,
        *,
        actor_id: str | None = None,
    ) -> Session:
        s = await self.get_by_id(session_id)
        fields: dict[str, Any] = {}
        if req.title is not None:
            fields["title"] = req.title
        if req.model is not None:
            fields["model"] = req.model
        if req.agent_name is not None:
            fields["agent_name"] = req.agent_name
        if req.scenario_id is not None:
            fields["scenario_id"] = req.scenario_id
        if req.status is not None:
            fields["status"] = req.status
        if req.metadata is not None:
            fields["metadata"] = req.metadata
        if not fields:
            return s
        before = {"title": s.title, "status": s.status}
        updated = await self._repo.update(session_id, **fields)
        if updated is None:
            raise NotFoundError("session", session_id)
        await self._audit.record(
            actor_type="user",
            actor_id=actor_id,
            action="update",
            resource_type="session",
            resource_id=session_id,
            before_data=before,
            after_data=fields,
        )
        return updated

    async def close(self, session_id: str, *, actor_id: str | None = None) -> Session:
        """关闭会话(状态 -> closed)."""
        return await self.update(
            session_id, UpdateSessionRequest(status="closed"), actor_id=actor_id
        )

    # ---------- 聚合更新(给 turn 写完时调) ----------

    async def accumulate_turn(
        self,
        session_id: str,
        *,
        cost: float = 0,
        tokens_input: int = 0,
        tokens_output: int = 0,
        tokens_reasoning: int = 0,
        tokens_cache_read: int = 0,
        tokens_cache_write: int = 0,
        increment_message_count: int = 0,
    ) -> Session | None:
        """累加 turn 写入对 session 聚合字段的贡献.

        Returns:
            更新后的 session, 不存在返回 None
        """
        return await self._repo.update_aggregates(
            session_id,
            cost_delta=cost,
            tokens_input_delta=tokens_input,
            tokens_output_delta=tokens_output,
            tokens_reasoning_delta=tokens_reasoning,
            tokens_cache_read_delta=tokens_cache_read,
            tokens_cache_write_delta=tokens_cache_write,
        )

    async def set_message_count(
        self, session_id: str, count: int
    ) -> Session | None:
        """覆盖设置 message_count(定期校正用)."""
        return await self._repo.update_aggregates(session_id, message_count=count)

    # ---------- 删除 ----------

    async def soft_delete(
        self, session_id: str, *, actor_id: str | None = None
    ) -> None:
        s = await self.get_by_id(session_id)
        ok = await self._repo.soft_delete(session_id)
        if not ok:
            return
        await self._audit.record(
            actor_type="user",
            actor_id=actor_id,
            action="delete",
            resource_type="session",
            resource_id=session_id,
            before_data={"title": s.title, "user_id": s.user_id},
        )

    # ---------- DTO 转换 ----------

    @staticmethod
    def to_response(s: Session) -> SessionResponse:
        return SessionResponse.from_model(s)
