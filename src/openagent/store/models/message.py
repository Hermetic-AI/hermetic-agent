"""Message Model — 消息(parts 已拆出)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from openagent.store.models._common import (
    from_db_bool,
    from_db_json,
    to_db_bool,
    to_db_json,
    utcnow,
)


@dataclass
class Message:
    """消息(parts 已拆出到 parts 表).

    对应表: ``messages``
    角色: ``user / assistant / system / tool``
    """

    session_id: str
    role: str
    content: str
    turn_id: str | None = None
    metadata: dict[str, Any] | None = None

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    is_deleted: bool = False
    deleted_at: datetime | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    def to_db_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "role": self.role,
            "content": self.content,
            "metadata": to_db_json(self.metadata),
            "is_deleted": to_db_bool(self.is_deleted),
            "deleted_at": self.deleted_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_db_dict(cls, row: dict[str, Any]) -> Message:
        return cls(
            id=row["id"],
            session_id=row["session_id"],
            turn_id=row.get("turn_id"),
            role=row["role"],
            content=row.get("content") or "",
            metadata=from_db_json(row.get("metadata")),
            is_deleted=from_db_bool(row.get("is_deleted", 0)),
            deleted_at=row.get("deleted_at"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
