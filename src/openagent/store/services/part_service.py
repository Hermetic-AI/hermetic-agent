"""PartService — 消息分段业务编排."""

from __future__ import annotations

import structlog

from openagent.store.dto.part import (
    BatchCreatePartRequest,
    CreatePartRequest,
    PartResponse,
)
from openagent.store.exceptions import NotFoundError
from openagent.store.models.part import Part
from openagent.store.repositories.part_repo import PartRepository
from openagent.store.services.audit_log_service import AuditLogService

logger = structlog.get_logger(__name__)


class PartService:
    """Part 服务."""

    def __init__(
        self,
        repo: PartRepository,
        audit: AuditLogService,
    ) -> None:
        self._repo = repo
        self._audit = audit

    async def get_by_id(self, part_id: str) -> Part:
        p = await self._repo.get_by_id(part_id)
        if p is None:
            raise NotFoundError("part", part_id)
        return p

    async def list_by_message(self, message_id: str) -> list[Part]:
        return await self._repo.list_by_message(message_id)

    async def list_by_session(
        self,
        session_id: str,
        *,
        limit: int = 200,
        offset: int = 0,
        part_type: str | None = None,
    ) -> list[Part]:
        return await self._repo.list_by_session(
            session_id, limit=limit, offset=offset, part_type=part_type
        )

    async def create(
        self, req: CreatePartRequest, *, actor_id: str | None = None
    ) -> Part:
        p = Part(
            message_id=req.message_id,
            session_id=req.session_id,
            part_type=req.part_type,
            content=req.content,
            position=req.position,
            metadata=req.metadata,
        )
        p = await self._repo.create(p)
        await self._audit.record(
            actor_type="system",
            actor_id=actor_id,
            action="create",
            resource_type="part",
            resource_id=p.id,
            after_data={
                "message_id": p.message_id,
                "part_type": p.part_type,
                "position": p.position,
            },
        )
        return p

    async def batch_create(
        self, req: BatchCreatePartRequest, *, actor_id: str | None = None
    ) -> list[Part]:
        parts = [
            Part(
                message_id=req.message_id,
                session_id=req.session_id,
                part_type=p.part_type,
                content=p.content,
                position=p.position,
                metadata=p.metadata,
            )
            for p in req.parts
        ]
        parts = await self._repo.batch_create(parts)
        await self._audit.record(
            actor_type="system",
            actor_id=actor_id,
            action="batch_create",
            resource_type="part",
            resource_id=req.message_id,
            after_data={"count": len(parts), "message_id": req.message_id},
        )
        return parts

    async def soft_delete(
        self, part_id: str, *, actor_id: str | None = None
    ) -> None:
        p = await self.get_by_id(part_id)
        ok = await self._repo.soft_delete(part_id)
        if not ok:
            return
        await self._audit.record(
            actor_type="user",
            actor_id=actor_id,
            action="delete",
            resource_type="part",
            resource_id=part_id,
            before_data={"part_type": p.part_type, "position": p.position},
        )

    @staticmethod
    def to_response(p: Part) -> PartResponse:
        return PartResponse.from_model(p)
