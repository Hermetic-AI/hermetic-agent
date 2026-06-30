"""Skill DTO 层."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from hermetic_agent.store.dto._common import DTOMixin, iso_or_none
from hermetic_agent.store.models.skill import Skill


class CreateSkillRequest(DTOMixin):
    """创建技能入参."""

    code: str = Field(min_length=1, max_length=128, description="业务编码(唯一标识)")
    name: str = Field(min_length=1, max_length=255)
    version: int = Field(default=1, ge=1)
    source: str = Field(default="db", pattern="^(db|yaml|builtin)$")
    status: str = Field(default="enabled", pattern="^(enabled|disabled|draft)$")
    description: str | None = None
    triggers: list[str] | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    prompt_template: str | None = None
    mcp_tools: dict[str, Any] | None = None
    required_envs: dict[str, Any] | None = None
    config: dict[str, Any] | None = None


class UpdateSkillRequest(DTOMixin):
    """更新技能入参(所有字段可选)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    triggers: list[str] | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    prompt_template: str | None = None
    mcp_tools: dict[str, Any] | None = None
    required_envs: dict[str, Any] | None = None
    config: dict[str, Any] | None = None
    status: str | None = Field(default=None, pattern="^(enabled|disabled|draft)$")


class SkillResponse(DTOMixin):
    """技能出参."""

    id: str
    code: str
    name: str
    version: int
    description: str | None
    triggers: Any = None
    input_schema: Any = None
    output_schema: Any = None
    prompt_template: str | None
    mcp_tools: Any = None
    required_envs: Any = None
    config: Any = None
    source: str
    status: str
    is_deleted: bool
    created_at: str
    updated_at: str | None
    deleted_at: str | None

    @classmethod
    def from_model(cls, m: Skill) -> SkillResponse:
        return cls(
            id=m.id,
            code=m.code,
            name=m.name,
            version=m.version,
            description=m.description,
            triggers=m.triggers,
            input_schema=m.input_schema,
            output_schema=m.output_schema,
            prompt_template=m.prompt_template,
            mcp_tools=m.mcp_tools,
            required_envs=m.required_envs,
            config=m.config,
            source=m.source,
            status=m.status,
            is_deleted=m.is_deleted,
            created_at=iso_or_none(m.created_at) or "",
            updated_at=iso_or_none(m.updated_at),
            deleted_at=iso_or_none(m.deleted_at),
        )


__all__ = [
    "CreateSkillRequest",
    "UpdateSkillRequest",
    "SkillResponse",
]
