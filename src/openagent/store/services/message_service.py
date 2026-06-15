"""MessageService — 消息 + 关联 parts 的业务编排.

典型用例:
- ``create_message(req, parts=[...])`` 同时创建消息和所有 parts (单事务)
- ``list_by_session_with_parts(session_id)`` 一次性拉 message + parts (避免 N+1)
"""

from __future__ import annotations

import structlog

from openagent.store.dto.message import CreateMessageRequest, MessageResponse
from openagent.store.exceptions import NotFoundError
from openagent.store.models.message import Message
from openagent.store.models.part import Part
from openagent.store.repositories.message_repo import MessageRepository
from openagent.store.repositories.part_repo import PartRepository
from openagent.store.services.audit_log_service import AuditLogService
from openagent.store.services.session_service import SessionService

logger = structlog.get_logger(__name__)


class MessageService:
    """消息服务."""

    def __init__(
        self,
        repo: MessageRepository,
        part_repo: PartRepository,
        audit: AuditLogService,
        session_service: SessionService | None = None,
    ) -> None:
        self._repo = repo
        self._part_repo = part_repo
        self._audit = audit
        self._session_service = session_service

    # ---------- 查询 ----------

    async def get_by_id(self, message_id: str) -> Message:
        m = await self._repo.get_by_id(message_id)
        if m is None:
            raise NotFoundError("message", message_id)
        return m

    async def list_by_session(
        self,
        session_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Message]:
        return await self._repo.list_by_session(session_id, limit=limit, offset=offset)

    async def list_by_turn(self, turn_id: str) -> list[Message]:
        return await self._repo.list_by_turn(turn_id)

    async def list_by_session_with_parts(
        self, session_id: str, *, limit: int = 100
    ) -> list[tuple[Message, list[Part]]]:
        """拉某 session 全部消息 + 各自 parts(避免 N+1)."""
        msgs = await self._repo.list_by_session(session_id, limit=limit)
        if not msgs:
            return []
        # 用 parts.session_id 冗余, 一次拉所有 parts
        all_parts = await self._part_repo.list_by_session(session_id, limit=limit * 50)
        parts_by_msg: dict[str, list[Part]] = {}
        for p in all_parts:
            parts_by_msg.setdefault(p.message_id, []).append(p)
        for k in parts_by_msg:
            parts_by_msg[k].sort(key=lambda x: (x.position, x.id))
        return [(m, parts_by_msg.get(m.id, [])) for m in msgs]

    # ---------- 创建 ----------

    async def create(
        self,
        req: CreateMessageRequest,
        *,
        actor_id: str | None = None,
    ) -> Message:
        """创建消息. 如果 req.parts 非空, 一起创建 parts(批量 INSERT)."""
        m = Message(
            session_id=req.session_id,
            turn_id=req.turn_id,
            role=req.role,
            content=req.content,
            metadata=req.metadata,
        )
        m = await self._repo.create(m)
        if req.parts:
            parts = [
                Part(
                    message_id=m.id,
                    session_id=m.session_id,
                    part_type=p.part_type,
                    content=p.content,
                    position=p.position,
                    metadata=p.metadata,
                )
                for p in req.parts
            ]
            await self._part_repo.batch_create(parts)
        # 累加 session.message_count
        if self._session_service is not None:
            current = await self._session_service.get_by_id(m.session_id)
            await self._session_service.set_message_count(
                m.session_id, current.message_count + 1
            )
        await self._audit.record(
            actor_type="system",
            actor_id=actor_id,
            action="create",
            resource_type="message",
            resource_id=m.id,
            after_data={
                "role": m.role,
                "session_id": m.session_id,
                "turn_id": m.turn_id,
            },
        )
        return m

    # ---------- 删除 ----------

    async def soft_delete(
        self, message_id: str, *, actor_id: str | None = None
    ) -> None:
        m = await self.get_by_id(message_id)
        ok = await self._repo.soft_delete(message_id)
        if not ok:
            return
        await self._audit.record(
            actor_type="user",
            actor_id=actor_id,
            action="delete",
            resource_type="message",
            resource_id=message_id,
            before_data={"role": m.role, "session_id": m.session_id},
        )

    @staticmethod
    def to_response(m: Message) -> MessageResponse:
        return MessageResponse.from_model(m)
