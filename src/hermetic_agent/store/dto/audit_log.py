"""AuditLog DTO 层."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from hermetic_agent.store.dto._common import DTOMixin, iso_or_none
from hermetic_agent.store.models.audit_log import AuditLog


class CreateAuditLogRequest(DTOMixin):
    """创建审计入参."""

    actor_type: str = Field(
        default="system", pattern="^(user|system|admin|anonymous)$"
    )
    actor_id: str | None = None
    action: str = Field(min_length=1, max_length=64)
    resource_type: str = Field(min_length=1, max_length=64)
    resource_id: str | None = None
    seq: int | None = None
    before_data: dict[str, Any] | None = None
    after_data: dict[str, Any] | None = None
    ip: str | None = None
    user_agent: str | None = Field(default=None, max_length=512)
    request_id: str | None = None
    metadata: dict[str, Any] | None = None


class AuditLogResponse(DTOMixin):
    """审计出参."""

    id: str
    seq: int | None
    actor_type: str
    actor_id: str | None
    action: str
    resource_type: str
    resource_id: str | None
    before_data: dict[str, Any] | None
    after_data: dict[str, Any] | None
    ip: str | None
    user_agent: str | None
    request_id: str | None
    created_at: str

    @classmethod
    def from_model(cls, m: AuditLog) -> AuditLogResponse:
        return cls(
            id=m.id,
            seq=m.seq,
            actor_type=m.actor_type,
            actor_id=m.actor_id,
            action=m.action,
            resource_type=m.resource_type,
            resource_id=m.resource_id,
            before_data=m.before_data,
            after_data=m.after_data,
            ip=m.ip,
            user_agent=m.user_agent,
            request_id=m.request_id,
            created_at=iso_or_none(m.created_at) or "",
        )


__all__ = [
    "CreateAuditLogRequest",
    "AuditLogResponse",
]
