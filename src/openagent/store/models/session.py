"""Session Model — 对话主表(含 token/cost 聚合)."""

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
class Session:
    """对话主表.

    对应表: ``sessions``
    聚合字段: ``message_count`` / ``cost`` / ``tokens_*`` 由 chat_turns 反向汇总,
              不强一致, 业务可接受秒级延迟.
    """

    user_id: str = ""
    title: str = "New Session"
    model: str | None = None
    agent_name: str = ""
    scenario_id: str | None = None
    status: str = "active"

    message_count: int = 0
    cost: Decimal = field(default_factory=lambda: Decimal("0"))
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_reasoning: int = 0
    tokens_cache_read: int = 0
    tokens_cache_write: int = 0

    metadata: dict[str, Any] | None = None

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    is_deleted: bool = False
    deleted_at: datetime | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    def to_db_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "model": self.model,
            "agent_name": self.agent_name,
            "scenario_id": self.scenario_id,
            "status": self.status,
            "message_count": int(self.message_count),
            "cost": self.cost,
            "tokens_input": int(self.tokens_input),
            "tokens_output": int(self.tokens_output),
            "tokens_reasoning": int(self.tokens_reasoning),
            "tokens_cache_read": int(self.tokens_cache_read),
            "tokens_cache_write": int(self.tokens_cache_write),
            "metadata": to_db_json(self.metadata),
            "is_deleted": to_db_bool(self.is_deleted),
            "deleted_at": self.deleted_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_db_dict(cls, row: dict[str, Any]) -> Session:
        cost = row.get("cost", 0)
        cost_dec = cost if isinstance(cost, Decimal) else Decimal(str(cost))
        return cls(
            id=row["id"],
            user_id=row.get("user_id") or "",
            title=row.get("title") or "New Session",
            model=row.get("model"),
            agent_name=row.get("agent_name") or "",
            scenario_id=row.get("scenario_id"),
            status=row.get("status") or "active",
            message_count=int(row.get("message_count", 0)),
            cost=cost_dec,
            tokens_input=int(row.get("tokens_input", 0)),
            tokens_output=int(row.get("tokens_output", 0)),
            tokens_reasoning=int(row.get("tokens_reasoning", 0)),
            tokens_cache_read=int(row.get("tokens_cache_read", 0)),
            tokens_cache_write=int(row.get("tokens_cache_write", 0)),
            metadata=from_db_json(row.get("metadata")),
            is_deleted=from_db_bool(row.get("is_deleted", 0)),
            deleted_at=row.get("deleted_at"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
