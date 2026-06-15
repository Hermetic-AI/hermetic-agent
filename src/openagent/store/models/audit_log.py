"""AuditLog Model — 审计日志(append-only)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from openagent.store.models._common import from_db_json, to_db_json, utcnow


@dataclass
class AuditLog:
    """审计日志(append-only, 不软删).

    对应表: ``audit_logs``
    软引用: ``resource_id`` 不建 FK, append-only 性质.
    """

    actor_type: str
    action: str
    resource_type: str
    actor_id: str | None = None
    resource_id: str | None = None
    seq: int | None = None
    before_data: dict[str, Any] | None = None
    after_data: dict[str, Any] | None = None
    ip: str | None = None
    user_agent: str | None = None
    request_id: str | None = None
    metadata: dict[str, Any] | None = None

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=utcnow)

    def to_db_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "seq": self.seq,
            "actor_type": self.actor_type,
            "actor_id": self.actor_id,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "before_data": to_db_json(self.before_data),
            "after_data": to_db_json(self.after_data),
            "ip": self.ip,
            "user_agent": self.user_agent,
            "request_id": self.request_id,
            "metadata": to_db_json(self.metadata),
            "created_at": self.created_at,
        }

    @classmethod
    def from_db_dict(cls, row: dict[str, Any]) -> AuditLog:
        return cls(
            id=row["id"],
            seq=row.get("seq"),
            actor_type=row["actor_type"],
            actor_id=row.get("actor_id"),
            action=row["action"],
            resource_type=row["resource_type"],
            resource_id=row.get("resource_id"),
            before_data=from_db_json(row.get("before_data")),
            after_data=from_db_json(row.get("after_data")),
            ip=row.get("ip"),
            user_agent=row.get("user_agent"),
            request_id=row.get("request_id"),
            metadata=from_db_json(row.get("metadata")),
            created_at=row["created_at"],
        )
