"""Prompt DTO 层 — 入参 / 出参 / 列表响应."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CreatePromptRequest(BaseModel):
    """创建 Prompt 入参."""

    code: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_\-]+$")
    name: str = Field(min_length=1, max_length=255)
    version: int = Field(default=1, ge=1)
    description: str | None = Field(default=None, max_length=2048)
    content: str = Field(min_length=1)


class UpdatePromptRequest(BaseModel):
    """更新 Prompt 入参 (所有字段可选)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2048)
    content: str | None = Field(default=None, min_length=1)
    status: str | None = Field(default=None, pattern=r"^(enabled|disabled|draft)$")


class PromptResponse(BaseModel):
    """Prompt 出参."""

    id: str
    code: str
    name: str
    version: int
    description: str | None
    content: str
    owner_user_id: str
    visibility: str
    status: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, m) -> PromptResponse:
        return cls(
            id=str(m.id),
            code=m.code,
            name=m.name,
            version=m.version,
            description=m.description,
            content=m.content,
            owner_user_id=m.owner_user_id,
            visibility=m.visibility,
            status=m.status,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )


class PromptListResponse(BaseModel):
    """Prompt 列表响应."""

    total: int
    items: list[PromptResponse]


__all__ = [
    "CreatePromptRequest",
    "UpdatePromptRequest",
    "PromptResponse",
    "PromptListResponse",
]