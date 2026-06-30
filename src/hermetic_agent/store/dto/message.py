"""Message DTO 层."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from hermetic_agent.store.dto._common import DTOMixin, iso_or_none
from hermetic_agent.store.models.message import Message


class CreateMessageRequest(DTOMixin):
    """创建消息入参(也支持批量创建时携带 parts)."""

    session_id: str
    role: str = Field(pattern="^(user|assistant|system|tool)$")
    content: str = ""
    turn_id: str | None = None
    metadata: dict[str, Any] | None = None
    parts: list[CreatePartRequest] | None = None  # type: ignore[name-defined]  # noqa: F821


class MessageResponse(DTOMixin):
    """消息出参."""

    id: str
    session_id: str
    turn_id: str | None
    role: str
    content: str
    metadata: dict[str, Any] | None
    created_at: str

    @classmethod
    def from_model(cls, m: Message) -> MessageResponse:
        return cls(
            id=m.id,
            session_id=m.session_id,
            turn_id=m.turn_id,
            role=m.role,
            content=m.content,
            metadata=m.metadata,
            created_at=iso_or_none(m.created_at) or "",
        )


__all__ = [
    "CreateMessageRequest",
    "MessageResponse",
]


# 解决 CreateMessageRequest 引用 CreatePartRequest 的前向引用
from hermetic_agent.store.dto.part import CreatePartRequest  # noqa: E402

CreateMessageRequest.model_rebuild()
