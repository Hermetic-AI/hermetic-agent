"""McpConfigService — MCP 配置的业务编排."""

from __future__ import annotations

from typing import Any

import structlog

from hermetic_agent.store.dto.mcp_config import (
    CreateMcpConfigRequest,
    McpConfigResponse,
    UpdateMcpConfigRequest,
)
from hermetic_agent.store.exceptions import DuplicateError, NotFoundError
from hermetic_agent.store.models.mcp_config import McpConfig
from hermetic_agent.store.repositories.mcp_config_repo import McpConfigRepository
from hermetic_agent.store.services.audit_log_service import AuditLogService

logger = structlog.get_logger(__name__)


class McpConfigService:
    """MCP 配置服务."""

    def __init__(
        self,
        repo: McpConfigRepository,
        audit: AuditLogService,
    ) -> None:
        self._repo = repo
        self._audit = audit

    async def get_by_id(self, config_id: str) -> McpConfig:
        c = await self._repo.get_by_id(config_id)
        if c is None:
            raise NotFoundError("mcp_config", config_id)
        return c

    async def get_by_code(self, code: str) -> McpConfig:
        c = await self._repo.get_by_code(code)
        if c is None:
            raise NotFoundError("mcp_config", code)
        return c

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        code: str | None = None,
    ) -> list[McpConfig]:
        return await self._repo.list(
            limit=limit, offset=offset, status=status, code=code
        )

    async def list_active(self, *, limit: int = 100) -> list[McpConfig]:
        return await self._repo.list_active(limit=limit)

    async def create(
        self,
        req: CreateMcpConfigRequest,
        *,
        actor_id: str | None = None,
    ) -> McpConfig:
        existing = await self._repo.get_by_code(req.code)
        if existing is not None:
            raise DuplicateError(
                f"mcp_config {req.code} already exists: {existing.id}"
            )
        c = McpConfig(
            code=req.code,
            name=req.name,
            mcp_type=req.mcp_type,
            url=req.url,
            command=req.command,
            args=req.args,
            env=req.env,
            cwd=req.cwd,
            headers=req.headers,
            allowed_tools=req.allowed_tools,
            disabled=req.disabled,
            config=req.config,
            source=req.source,
            status=req.status,
        )
        c = await self._repo.create(c)
        await self._audit.record(
            actor_type="user",
            actor_id=actor_id,
            action="create",
            resource_type="mcp_config",
            resource_id=c.id,
            after_data={"code": c.code, "name": c.name, "mcp_type": c.mcp_type},
        )
        return c

    async def update(
        self,
        config_id: str,
        req: UpdateMcpConfigRequest,
        *,
        actor_id: str | None = None,
    ) -> McpConfig:
        c = await self.get_by_id(config_id)
        fields: dict[str, Any] = {}
        for field_name in (
            "name", "mcp_type", "url", "command", "args", "env", "cwd",
            "headers", "allowed_tools", "disabled", "config", "status",
        ):
            val = getattr(req, field_name, None)
            if val is not None:
                fields[field_name] = val
        if not fields:
            return c
        before = {"name": c.name, "status": c.status}
        updated = await self._repo.update(config_id, **fields)
        if updated is None:
            raise NotFoundError("mcp_config", config_id)
        await self._audit.record(
            actor_type="user",
            actor_id=actor_id,
            action="update",
            resource_type="mcp_config",
            resource_id=config_id,
            before_data=before,
            after_data=fields,
        )
        return updated

    async def soft_delete(
        self, config_id: str, *, actor_id: str | None = None
    ) -> None:
        c = await self.get_by_id(config_id)
        ok = await self._repo.soft_delete(config_id)
        if not ok:
            return
        await self._audit.record(
            actor_type="user",
            actor_id=actor_id,
            action="delete",
            resource_type="mcp_config",
            resource_id=config_id,
            before_data={"code": c.code},
        )

    @staticmethod
    def to_response(c: McpConfig) -> McpConfigResponse:
        return McpConfigResponse.from_model(c)


__all__ = ["McpConfigService"]
