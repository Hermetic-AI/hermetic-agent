"""Part DTO 层."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from hermetic_agent.store.dto._common import DTOMixin, iso_or_none
from hermetic_agent.store.models.part import Part


class CreatePartRequest(DTOMixin):
    """创建分段入参."""

    message_id: str
    session_id: str
    part_type: str = Field(
        default="text",
        pattern="^(text|image|tool_call|tool_result|file|audio|video)$",
    )
    content: str | None = None
    position: int = 0
    metadata: dict[str, Any] | None = None


class BatchCreatePartRequest(DTOMixin):
    """批量创建分段(同 message)."""

    message_id: str
    session_id: str
    parts: list[CreatePartRequest]


class PartResponse(DTOMixin):
    """分段出参."""

    id: str
    message_id: str
    session_id: str
    part_type: str
    content: str | None
    position: int
    metadata: dict[str, Any] | None
    created_at: str

    @classmethod
    def from_model(cls, m: Part) -> PartResponse:
        return cls(
            id=m.id,
            message_id=m.message_id,
            session_id=m.session_id,
            part_type=m.part_type,
            content=m.content,
            position=m.position,
            metadata=m.metadata,
            created_at=iso_or_none(m.created_at) or "",
        )


__all__ = [
    "CreatePartRequest",
    "BatchCreatePartRequest",
    "PartResponse",
]
