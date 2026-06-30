"""Memory MCP Config Repository."""

from __future__ import annotations

from typing import Any

from hermetic_agent.store.models.mcp_config import McpConfig
from hermetic_agent.store.repositories.mcp_config_repo import McpConfigRepository
from hermetic_agent.store.repositories.memory._base import MemoryRepository


class MemoryMcpConfigRepository(MemoryRepository[McpConfig], McpConfigRepository):
    def __init__(self) -> None:
        super().__init__()

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[McpConfig]:
        items = list(self._store.values())
        if not include_deleted:
            items = [m for m in items if not m.is_deleted]
        for k in ("code", "status", "source", "mcp_type"):
            if k in filters and filters[k] is not None:
                items = [m for m in items if getattr(m, k) == filters[k]]
        items.sort(key=lambda m: (m.updated_at, m.id), reverse=True)
        return items[offset : offset + limit]

    async def count(
        self, *, include_deleted: bool = False, **filters: Any
    ) -> int:
        items = list(self._store.values())
        if not include_deleted:
            items = [m for m in items if not m.is_deleted]
        for k in ("code", "status"):
            if k in filters and filters[k] is not None:
                items = [m for m in items if getattr(m, k) == filters[k]]
        return len(items)

    async def get_by_code(self, code: str) -> McpConfig | None:
        for m in self._store.values():
            if m.code == code and not m.is_deleted:
                return m
        return None

    async def list_active(self, *, limit: int = 100) -> list[McpConfig]:
        items = list(self._store.values())
        items = [
            m for m in items
            if not m.is_deleted and m.status == "enabled" and not m.disabled
        ]
        items.sort(key=lambda m: (m.updated_at, m.id), reverse=True)
        return items[:limit]


__all__ = ["MemoryMcpConfigRepository"]
