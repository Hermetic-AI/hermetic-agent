"""Scenario DTO 层."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from openagent.store.dto._common import DTOMixin, iso_or_none, model_to_dict
from openagent.store.models.scenario import Scenario


class CreateScenarioRequest(DTOMixin):
    """创建场景入参. ``id`` / ``version`` / 时间戳 / 软删字段由系统填."""

    code: str = Field(min_length=1, max_length=128, description="业务短码, 全局唯一")
    name: str = Field(min_length=1, max_length=255)
    config: dict[str, Any] = Field(description="ScenarioConfig Pydantic 序列化结果")
    version: int = Field(default=1, ge=1)
    source: str = Field(default="db", pattern="^(db|yaml|builtin)$")
    status: str = Field(default="enabled", pattern="^(enabled|disabled|draft)$")
    description: str | None = None
    parent_id: str | None = None


class UpdateScenarioRequest(DTOMixin):
    """更新场景入参(所有字段可选)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    config: dict[str, Any] | None = None
    status: str | None = Field(default=None, pattern="^(enabled|disabled|draft)$")


class ScenarioResponse(DTOMixin):
    """场景出参."""

    id: str
    code: str
    name: str
    version: int
    parent_id: str | None
    description: str | None
    config: dict[str, Any]
    source: str
    status: str
    is_deleted: bool
    created_at: str
    updated_at: str | None
    deleted_at: str | None

    @classmethod
    def from_model(cls, m: Scenario) -> ScenarioResponse:
        return cls(
            id=m.id,
            code=m.code,
            name=m.name,
            version=m.version,
            parent_id=m.parent_id,
            description=m.description,
            config=m.config,
            source=m.source,
            status=m.status,
            is_deleted=m.is_deleted,
            created_at=iso_or_none(m.created_at) or "",
            updated_at=iso_or_none(m.updated_at),
            deleted_at=iso_or_none(m.deleted_at),
        )

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> ScenarioResponse:
        return cls.from_model(Scenario.from_db_dict(row))


__all__ = [
    "CreateScenarioRequest",
    "UpdateScenarioRequest",
    "ScenarioResponse",
    "model_to_dict",  # re-export for convenience
]
