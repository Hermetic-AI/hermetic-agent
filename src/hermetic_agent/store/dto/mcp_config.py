"""MCP Config DTO 层."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from hermetic_agent.store.dto._common import DTOMixin, iso_or_none
from hermetic_agent.store.models.mcp_config import McpConfig


class CreateMcpConfigRequest(DTOMixin):
    """创建 MCP 配置入参."""

    code: str = Field(min_length=1, max_length=128, description="MCP server 唯一编码")
    name: str = Field(min_length=1, max_length=255)
    mcp_type: str = Field(default="http", pattern="^(http|sse|stdio)$")
    source: str = Field(default="db", pattern="^(db|json|env)$")
    status: str = Field(default="enabled", pattern="^(enabled|disabled|draft)$")
    disabled: bool = False
    url: str | None = None
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    cwd: str | None = None
    headers: dict[str, str] | None = None
    allowed_tools: list[str] | None = None
    config: dict[str, Any] | None = None


class UpdateMcpConfigRequest(DTOMixin):
    """更新 MCP 配置入参(所有字段可选)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    mcp_type: str | None = Field(default=None, pattern="^(http|sse|stdio)$")
    url: str | None = None
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    cwd: str | None = None
    headers: dict[str, str] | None = None
    allowed_tools: list[str] | None = None
    disabled: bool | None = None
    config: dict[str, Any] | None = None
    status: str | None = Field(default=None, pattern="^(enabled|disabled|draft)$")


class McpConfigResponse(DTOMixin):
    """MCP 配置出参."""

    id: str
    code: str
    name: str
    mcp_type: str
    url: str | None
    command: str | None
    args: Any = None
    env: Any = None
    cwd: str | None
    headers: Any = None
    allowed_tools: Any = None
    disabled: bool
    config: Any = None
    source: str
    status: str
    is_deleted: bool
    created_at: str
    updated_at: str | None
    deleted_at: str | None

    @classmethod
    def from_model(cls, m: McpConfig) -> McpConfigResponse:
        return cls(
            id=m.id,
            code=m.code,
            name=m.name,
            mcp_type=m.mcp_type,
            url=m.url,
            command=m.command,
            args=m.args,
            env=m.env,
            cwd=m.cwd,
            headers=m.headers,
            allowed_tools=m.allowed_tools,
            disabled=m.disabled,
            config=m.config,
            source=m.source,
            status=m.status,
            is_deleted=m.is_deleted,
            created_at=iso_or_none(m.created_at) or "",
            updated_at=iso_or_none(m.updated_at),
            deleted_at=iso_or_none(m.deleted_at),
        )


__all__ = [
    "CreateMcpConfigRequest",
    "UpdateMcpConfigRequest",
    "McpConfigResponse",
]
