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

    @abstractmethod
    async def list_visible_to(
        self,
        *,
        actor_user_id: str,
        limit: int = 50,
        offset: int = 0,
        code: str | None = None,
        status: str | None = None,
    ) -> list[McpConfig]:
        """列出对 actor 可见的 MCP 配置 (owner 的全部 + 别人的 public)."""

    @abstractmethod
    async def list_public(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        code: str | None = None,
    ) -> list[McpConfig]:
        """列出所有 public MCP 配置."""

    @abstractmethod
    async def set_visibility(
        self,
        config_id: str,
        *,
        visibility: str,
        actor_user_id: str,
    ) -> McpConfig | None:
        """仅 owner 可改 visibility. 失败返回 None."""


__all__ = ["McpConfigRepository"]
