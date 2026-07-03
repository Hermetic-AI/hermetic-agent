"""ChatTurn DTO 层."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import Field

from hermetic_agent.store.dto._common import DTOMixin, iso_or_none
from hermetic_agent.store.models.chat_turn import ChatTurn


class CreateChatTurnRequest(DTOMixin):
    """创建 turn 入参(开启一个 turn, 状态 pending)."""

    session_id: str
    agent_name: str | None = None
    model: str | None = None
    metadata: dict[str, Any] | None = None


class UpdateChatTurnRequest(DTOMixin):
    """更新 turn 入参(执行过程中填字段)."""

    status: str | None = Field(
        default=None, pattern="^(pending|running|success|failed|cancelled)$"
    )
    user_message_id: str | None = None
    assistant_message_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    cost: Decimal | None = None
    tokens_input: int | None = None
    tokens_output: int | None = None
    tokens_reasoning: int | None = None
    tokens_cache_read: int | None = None
    tokens_cache_write: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] | None = None


class ChatTurnResponse(DTOMixin):
    """turn 出参."""

    id: str
    session_id: str
    user_message_id: str | None
    assistant_message_id: str | None
    agent_name: str | None
    model: str | None
    status: str
    started_at: str | None
    finished_at: str | None
    duration_ms: int | None
    cost: float
    tokens_input: int
    tokens_output: int
    tokens_reasoning: int
    tokens_cache_read: int
    tokens_cache_write: int
    error_code: str | None
    error_message: str | None
    created_at: str

    @classmethod
    def from_model(cls, m: ChatTurn) -> ChatTurnResponse:
        return cls(
            id=m.id,
            session_id=m.session_id,
            user_message_id=m.user_message_id,
            assistant_message_id=m.assistant_message_id,
            agent_name=m.agent_name,
            model=m.model,
            status=m.status,
            started_at=iso_or_none(m.started_at),
            finished_at=iso_or_none(m.finished_at),
            duration_ms=m.duration_ms,
            cost=float(m.cost),
            tokens_input=m.tokens_input,
            tokens_output=m.tokens_output,
            tokens_reasoning=m.tokens_reasoning,
            tokens_cache_read=m.tokens_cache_read,
            tokens_cache_write=m.tokens_cache_write,
            error_code=m.error_code,
            error_message=m.error_message,
            created_at=iso_or_none(m.created_at) or "",
        )


__all__ = [
    "CreateChatTurnRequest",
    "UpdateChatTurnRequest",
    "ChatTurnResponse",
]
