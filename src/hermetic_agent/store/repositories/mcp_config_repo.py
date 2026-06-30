"""McpConfigRepository ABC — MCP 配置仓储接口."""

from __future__ import annotations

from abc import abstractmethod

from hermetic_agent.store.models.mcp_config import McpConfig
from hermetic_agent.store.repositories._base import Repository


class McpConfigRepository(Repository[McpConfig]):
    """MCP 配置仓储接口."""

    @abstractmethod
    async def get_by_code(self, code: str) -> McpConfig | None:
        """按业务编码查 MCP 配置."""

    @abstractmethod
    async def list_active(self, *, limit: int = 100) -> list[McpConfig]:
        """列出 status=enabled 且 disabled=False 的配置."""


__all__ = ["McpConfigRepository"]
