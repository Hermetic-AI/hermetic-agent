"""ChatTurn Model — 单轮执行单元(含本 turn token 用量)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from openagent.store.models._common import (
    from_db_bool,
    from_db_json,
    to_db_bool,
    to_db_json,
    utcnow,
)


@dataclass
class ChatTurn:
    """单轮执行单元: 一次 user -> assistant 往返.

    对应表: ``chat_turns``
    状态: ``pending / running / success / failed / cancelled``
    """

    session_id: str
    status: str = "pending"
    user_message_id: str | None = None
    assistant_message_id: str | None = None
    agent_name: str | None = None
    model: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None

    cost: Decimal = field(default_factory=lambda: Decimal("0"))
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_reasoning: int = 0
    tokens_cache_read: int = 0
    tokens_cache_write: int = 0

    error_code: str | None = None
    error_message: str | None = None
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
            "user_message_id": self.user_message_id,
            "assistant_message_id": self.assistant_message_id,
            "agent_name": self.agent_name,
            "model": self.model,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "cost": self.cost,
            "tokens_input": int(self.tokens_input),
            "tokens_output": int(self.tokens_output),
            "tokens_reasoning": int(self.tokens_reasoning),
            "tokens_cache_read": int(self.tokens_cache_read),
            "tokens_cache_write": int(self.tokens_cache_write),
            "error_code": self.error_code,
            "error_message": self.error_message,
            "metadata": to_db_json(self.metadata),
            "is_deleted": to_db_bool(self.is_deleted),
            "deleted_at": self.deleted_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_db_dict(cls, row: dict[str, Any]) -> ChatTurn:
        cost = row.get("cost", 0)
        cost_dec = cost if isinstance(cost, Decimal) else Decimal(str(cost))
        return cls(
            id=row["id"],
            session_id=row["session_id"],
            user_message_id=row.get("user_message_id"),
            assistant_message_id=row.get("assistant_message_id"),
            agent_name=row.get("agent_name"),
            model=row.get("model"),
            status=row.get("status") or "pending",
            started_at=row.get("started_at"),
            finished_at=row.get("finished_at"),
            duration_ms=row.get("duration_ms"),
            cost=cost_dec,
            tokens_input=int(row.get("tokens_input", 0)),
            tokens_output=int(row.get("tokens_output", 0)),
            tokens_reasoning=int(row.get("tokens_reasoning", 0)),
            tokens_cache_read=int(row.get("tokens_cache_read", 0)),
            tokens_cache_write=int(row.get("tokens_cache_write", 0)),
            error_code=row.get("error_code"),
            error_message=row.get("error_message"),
            metadata=from_db_json(row.get("metadata")),
            is_deleted=from_db_bool(row.get("is_deleted", 0)),
            deleted_at=row.get("deleted_at"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
