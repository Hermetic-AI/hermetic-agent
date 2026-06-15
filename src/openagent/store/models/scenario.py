"""Scenario Model — 场景定义/快照."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from openagent.store.models._common import (
    from_db_bool,
    from_db_json,
    to_db_bool,
    to_db_json,
    utcnow,
)


@dataclass
class Scenario:
    """场景定义/快照(支持版本链).

    对应表: ``scenarios``
    唯一约束: ``(code, version)`` 应用层保证 (uk_scenarios_code_version)
    """

    code: str
    name: str
    config: dict[str, Any]
    version: int = 1
    source: str = "db"
    status: str = "enabled"
    description: str | None = None
    parent_id: str | None = None

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    is_deleted: bool = False
    deleted_at: datetime | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    def to_db_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "version": self.version,
            "parent_id": self.parent_id,
            "description": self.description,
            "config": to_db_json(self.config),
            "source": self.source,
            "status": self.status,
            "is_deleted": to_db_bool(self.is_deleted),
            "deleted_at": self.deleted_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_db_dict(cls, row: dict[str, Any]) -> Scenario:
        return cls(
            id=row["id"],
            code=row["code"],
            name=row["name"],
            version=int(row["version"]),
            parent_id=row.get("parent_id"),
            description=row.get("description"),
            config=from_db_json(row.get("config")) or {},
            source=row.get("source") or "db",
            status=row.get("status") or "enabled",
            is_deleted=from_db_bool(row.get("is_deleted", 0)),
            deleted_at=row.get("deleted_at"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
