"""Session DTO 层."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from hermetic_agent.store.dto._common import DTOMixin, iso_or_none
from hermetic_agent.store.models.session import Session


class CreateSessionRequest(DTOMixin):
    """创建会话入参."""

    user_id: str = Field(default="", max_length=64)
    title: str = Field(default="New Session", max_length=255)
    model: str | None = Field(default=None, max_length=128)
    agent_name: str = Field(default="", max_length=128)
    scenario_id: str | None = None
    status: str = Field(default="active", pattern="^(active|closed|archived)$")
    metadata: dict[str, Any] | None = None


class UpdateSessionRequest(DTOMixin):
    """更新会话入参(部分字段)."""

    title: str | None = Field(default=None, max_length=255)
    model: str | None = None
    agent_name: str | None = None
    scenario_id: str | None = None
    status: str | None = Field(default=None, pattern="^(active|closed|archived)$")
    metadata: dict[str, Any] | None = None


class SessionResponse(DTOMixin):
    """会话出参(不含 token 聚合字段; 列表接口用)."""

    id: str
    user_id: str
    title: str
    model: str | None
    agent_name: str
    scenario_id: str | None
    status: str
    message_count: int
    cost: float
    tokens_input: int
    tokens_output: int
    tokens_reasoning: int
    tokens_cache_read: int
    tokens_cache_write: int
    metadata: dict[str, Any] | None
    created_at: str
    updated_at: str | None
    is_deleted: bool

    @classmethod
    def from_model(cls, m: Session) -> SessionResponse:
        return cls(
            id=m.id,
            user_id=m.user_id,
            title=m.title,
            model=m.model,
            agent_name=m.agent_name,
            scenario_id=m.scenario_id,
            status=m.status,
            message_count=m.message_count,
            cost=float(m.cost),
            tokens_input=m.tokens_input,
            tokens_output=m.tokens_output,
            tokens_reasoning=m.tokens_reasoning,
            tokens_cache_read=m.tokens_cache_read,
            tokens_cache_write=m.tokens_cache_write,
            metadata=m.metadata,
            created_at=iso_or_none(m.created_at) or "",
            updated_at=iso_or_none(m.updated_at),
            is_deleted=m.is_deleted,
        )


__all__ = [
    "CreateSessionRequest",
    "UpdateSessionRequest",
    "SessionResponse",
]
