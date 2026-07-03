"""Command DTO 层 — 入参 / 出参 / 列表响应."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CreateCommandRequest(BaseModel):
    """创建 Command 入参."""

    code: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_\-]+$")
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2048)
    slash_command: str = Field(pattern=r"^/[A-Za-z0-9_\-]+$")
    system_prompt_addendum: str = Field(min_length=1)


class UpdateCommandRequest(BaseModel):
    """更新 Command 入参 (所有字段可选)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2048)
    slash_command: str | None = Field(
        default=None, pattern=r"^/[A-Za-z0-9_\-]+$",
    )
    system_prompt_addendum: str | None = Field(default=None, min_length=1)
    enabled: bool | None = None
    status: str | None = Field(default=None, pattern=r"^(enabled|disabled|draft)$")


class CommandResponse(BaseModel):
    """Command 出参."""

    id: str
    code: str
    name: str
    description: str | None
    slash_command: str
    system_prompt_addendum: str
    enabled: bool
    owner_user_id: str
    visibility: str
    status: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, m) -> CommandResponse:
        data = {}
        for k in cls.model_fields.keys():
            v = getattr(m, k)
            if k == "id" and v is not None:
                v = str(v)
            data[k] = v
        return cls(**data)


class CommandListResponse(BaseModel):
    """Command 列表响应."""

    total: int
    items: list[CommandResponse]


__all__ = [
    "CreateCommandRequest",
    "UpdateCommandRequest",
    "CommandResponse",
    "CommandListResponse",
]