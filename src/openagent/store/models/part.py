"""Part Model — 消息分段(原 messages.parts JSON 拆出, 加 session_id 冗余)."""

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
class Part:
    """消息分段(原 messages.parts JSON 拆出, 加 session_id 冗余).

    对应表: ``parts``
    类型: ``text / image / tool_call / tool_result / file``
    冗余: ``session_id`` 冗余, 避免按 session 查 part 时 JOIN messages.
    """

    message_id: str
    session_id: str
    part_type: str
    content: str | None = None
    position: int = 0
    metadata: dict[str, Any] | None = None

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    is_deleted: bool = False
    deleted_at: datetime | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    def to_db_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "message_id": self.message_id,
            "session_id": self.session_id,
            "part_type": self.part_type,
            "content": self.content,
            "position": int(self.position),
            "metadata": to_db_json(self.metadata),
            "is_deleted": to_db_bool(self.is_deleted),
            "deleted_at": self.deleted_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_db_dict(cls, row: dict[str, Any]) -> Part:
        return cls(
            id=row["id"],
            message_id=row["message_id"],
            session_id=row["session_id"],
            part_type=row["part_type"],
            content=row.get("content"),
            position=int(row.get("position", 0)),
            metadata=from_db_json(row.get("metadata")),
            is_deleted=from_db_bool(row.get("is_deleted", 0)),
            deleted_at=row.get("deleted_at"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
