"""ChatTurnService — 单轮执行单元的业务编排."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

import structlog

from openagent.store.dto.chat_turn import (
    ChatTurnResponse,
    CreateChatTurnRequest,
    UpdateChatTurnRequest,
)
from openagent.store.exceptions import NotFoundError
from openagent.store.models.chat_turn import ChatTurn
from openagent.store.repositories.chat_turn_repo import ChatTurnRepository
from openagent.store.services.audit_log_service import AuditLogService
from openagent.store.services.session_service import SessionService

logger = structlog.get_logger(__name__)


class ChatTurnService:
    """单轮执行服务.

    业务规则:
    - 创建 turn: 状态默认 pending, started_at=None
    - 启动 turn: mark_started() -> running, 写 started_at
    - 完成 turn: mark_finished() -> success/failed/cancelled, 写 finished_at + duration
    - 完成后累加 session 聚合
    """

    def __init__(
        self,
        repo: ChatTurnRepository,
        audit: AuditLogService,
        session_service: SessionService | None = None,
    ) -> None:
        self._repo = repo
        self._audit = audit
        self._session_service = session_service

    # ---------- 查询 ----------

    async def get_by_id(self, turn_id: str) -> ChatTurn:
        t = await self._repo.get_by_id(turn_id)
        if t is None:
            raise NotFoundError("chat_turn", turn_id)
        return t

    async def list_by_session(
        self,
        session_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
    ) -> list[ChatTurn]:
        return await self._repo.list_by_session(
            session_id, limit=limit, offset=offset, status=status
        )

    async def list_by_status(
        self, status: str, *, limit: int = 50
    ) -> list[ChatTurn]:
        return await self._repo.list_by_status(status, limit=limit)

    # ---------- 创建 ----------

    async def create(
        self,
        req: CreateChatTurnRequest,
        *,
        actor_id: str | None = None,
    ) -> ChatTurn:
        t = ChatTurn(
            session_id=req.session_id,
            agent_name=req.agent_name,
            model=req.model,
            status="pending",
            metadata=req.metadata,
        )
        t = await self._repo.create(t)
        await self._audit.record(
            actor_type="system",
            actor_id=actor_id,
            action="create",
            resource_type="turn",
            resource_id=t.id,
            after_data={"session_id": t.session_id, "status": t.status},
        )
        return t

    async def update(
        self, turn_id: str, req: UpdateChatTurnRequest
    ) -> ChatTurn:
        t = await self.get_by_id(turn_id)
        fields: dict[str, Any] = {}
        if req.status is not None:
            fields["status"] = req.status
        if req.user_message_id is not None:
            fields["user_message_id"] = req.user_message_id
        if req.assistant_message_id is not None:
            fields["assistant_message_id"] = req.assistant_message_id
        if req.started_at is not None:
            fields["started_at"] = req.started_at
        if req.finished_at is not None:
            fields["finished_at"] = req.finished_at
        if req.duration_ms is not None:
            fields["duration_ms"] = req.duration_ms
        if req.cost is not None:
            fields["cost"] = req.cost
        for k in (
            "tokens_input",
            "tokens_output",
            "tokens_reasoning",
            "tokens_cache_read",
            "tokens_cache_write",
        ):
            v = getattr(req, k)
            if v is not None:
                fields[k] = v
        if req.error_code is not None:
            fields["error_code"] = req.error_code
        if req.error_message is not None:
            fields["error_message"] = req.error_message
        if req.metadata is not None:
            fields["metadata"] = req.metadata
        if not fields:
            return t
        updated = await self._repo.update(turn_id, **fields)
        if updated is None:
            raise NotFoundError("chat_turn", turn_id)
        return updated

    # ---------- 状态机辅助 ----------

    async def start(self, turn_id: str) -> ChatTurn:
        """启动 turn (pending -> running)."""
        t = await self.repo_mark_started(turn_id)
        if t is None:
            raise NotFoundError("chat_turn", turn_id)
        await self._audit.record(
            actor_type="system",
            action="state_change",
            resource_type="turn",
            resource_id=turn_id,
            after_data={"status": "running"},
        )
        return t

    async def complete(
        self,
        turn_id: str,
        *,
        cost: float | Decimal = 0,
        tokens_input: int = 0,
        tokens_output: int = 0,
        tokens_reasoning: int = 0,
        tokens_cache_read: int = 0,
        tokens_cache_write: int = 0,
    ) -> ChatTurn:
        """完成 turn (running -> success), 累加 session 聚合."""
        t = await self.repo_mark_finished(turn_id, "success")
        if t is None:
            raise NotFoundError("chat_turn", turn_id)
        # 把 token / cost 写回 turn 行
        await self._repo.update(
            turn_id,
            cost=Decimal(str(cost)),
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            tokens_reasoning=tokens_reasoning,
            tokens_cache_read=tokens_cache_read,
            tokens_cache_write=tokens_cache_write,
        )
        # 累加 session 聚合
        if self._session_service is not None:
            await self._session_service.accumulate_turn(
                t.session_id,
                cost=float(cost),
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                tokens_reasoning=tokens_reasoning,
                tokens_cache_read=tokens_cache_read,
                tokens_cache_write=tokens_cache_write,
            )
        await self._audit.record(
            actor_type="system",
            action="state_change",
            resource_type="turn",
            resource_id=turn_id,
            after_data={
                "status": "success",
                "cost": float(cost),
                "tokens_input": tokens_input,
                "tokens_output": tokens_output,
            },
        )
        return await self.get_by_id(turn_id)

    async def fail(
        self,
        turn_id: str,
        error_code: str,
        error_message: str,
    ) -> ChatTurn:
        """失败 turn (running -> failed)."""
        t = await self.repo_mark_finished(
            turn_id, "failed", error_code=error_code, error_message=error_message
        )
        if t is None:
            raise NotFoundError("chat_turn", turn_id)
        await self._audit.record(
            actor_type="system",
            action="state_change",
            resource_type="turn",
            resource_id=turn_id,
            after_data={
                "status": "failed",
                "error_code": error_code,
                "error_message": error_message,
            },
        )
        return t

    async def cancel(self, turn_id: str) -> ChatTurn:
        """取消 turn (任何非终态 -> cancelled)."""
        t = await self.repo_mark_finished(turn_id, "cancelled")
        if t is None:
            raise NotFoundError("chat_turn", turn_id)
        await self._audit.record(
            actor_type="system",
            action="state_change",
            resource_type="turn",
            resource_id=turn_id,
            after_data={"status": "cancelled"},
        )
        return t

    # ---------- 删除 ----------

    async def soft_delete(self, turn_id: str) -> None:
        await self.get_by_id(turn_id)
        await self._repo.soft_delete(turn_id)

    # ---------- 内部代理(为了审计/扩展) ----------

    async def repo_mark_started(
        self, turn_id: str, when: datetime | None = None
    ) -> ChatTurn | None:
        return await self._repo.mark_started(turn_id, when)

    async def repo_mark_finished(
        self,
        turn_id: str,
        status: str,
        *,
        finished_at: datetime | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> ChatTurn | None:
        return await self._repo.mark_finished(
            turn_id,
            status,
            finished_at=finished_at,
            error_code=error_code,
            error_message=error_message,
        )

    # ---------- DTO ----------

    @staticmethod
    def to_response(t: ChatTurn) -> ChatTurnResponse:
        return ChatTurnResponse.from_model(t)
