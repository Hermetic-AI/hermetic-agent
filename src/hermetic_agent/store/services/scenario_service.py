"""ScenarioService — 场景定义/快照的业务编排."""

from __future__ import annotations

from typing import Any

import structlog

from hermetic_agent.store.dto.scenario import (
    CreateScenarioRequest,
    ScenarioResponse,
    UpdateScenarioRequest,
)
from hermetic_agent.store.exceptions import DuplicateError, NotFoundError
from hermetic_agent.store.models.scenario import Scenario
from hermetic_agent.store.repositories.scenario_repo import ScenarioRepository
from hermetic_agent.store.services.audit_log_service import AuditLogService

logger = structlog.get_logger(__name__)


class ScenarioService:
    """场景服务."""

    def __init__(
        self,
        repo: ScenarioRepository,
        audit: AuditLogService,
    ) -> None:
        self._repo = repo
        self._audit = audit

    # ---------- 查询 ----------

    async def get_by_id(self, scenario_id: str) -> Scenario:
        s = await self._repo.get_by_id(scenario_id)
        if s is None:
            raise NotFoundError("scenario", scenario_id)
        return s

    async def get_by_code_version(self, code: str, version: int) -> Scenario:
        s = await self._repo.get_by_code_version(code, version)
        if s is None:
            raise NotFoundError("scenario", f"{code}@v{version}")
        return s

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        code: str | None = None,
    ) -> list[Scenario]:
        return await self._repo.list(
            limit=limit, offset=offset, status=status, code=code
        )

    async def list_active(self, *, limit: int = 100) -> list[Scenario]:
        return await self._repo.list_active(limit=limit)

    # ---------- 创建 ----------

    async def create(
        self,
        req: CreateScenarioRequest,
        *,
        actor_id: str | None = None,
    ) -> Scenario:
        """创建场景. 同 (code, version) 已存在抛 DuplicateError."""
        existing = await self._repo.get_by_code_version(req.code, req.version)
        if existing is not None:
            raise DuplicateError(
                f"scenario {req.code}@v{req.version} already exists: {existing.id}"
            )
        s = Scenario(
            code=req.code,
            name=req.name,
            version=req.version,
            description=req.description,
            config=req.config,
            source=req.source,
            status=req.status,
        )
        if req.parent_id is not None:
            s.parent_id = req.parent_id
        s = await self._repo.create(s)
        await self._audit.record(
            actor_type="user",
            actor_id=actor_id,
            action="create",
            resource_type="scenario",
            resource_id=s.id,
            after_data={"code": s.code, "version": s.version, "name": s.name},
        )
        return s

    # ---------- 更新 ----------

    async def update(
        self,
        scenario_id: str,
        req: UpdateScenarioRequest,
        *,
        actor_id: str | None = None,
    ) -> Scenario:
        s = await self.get_by_id(scenario_id)
        fields: dict[str, Any] = {}
        if req.name is not None:
            fields["name"] = req.name
        if req.description is not None:
            fields["description"] = req.description
        if req.config is not None:
            fields["config"] = req.config
        if req.status is not None:
            fields["status"] = req.status
        if not fields:
            return s
        before = {"name": s.name, "status": s.status}
        updated = await self._repo.update(scenario_id, **fields)
        if updated is None:
            raise NotFoundError("scenario", scenario_id)
        await self._audit.record(
            actor_type="user",
            actor_id=actor_id,
            action="update",
            resource_type="scenario",
            resource_id=scenario_id,
            before_data=before,
            after_data=fields,
        )
        return updated

    # ---------- 版本演化 ----------

    async def create_new_version(
        self,
        parent_id: str,
        new_config: dict[str, Any],
        new_name: str | None = None,
        *,
        actor_id: str | None = None,
    ) -> Scenario:
        """基于父版本创建新版本(自动 +1, parent_id 指向父)."""
        parent = await self.get_by_id(parent_id)
        new = await self._repo.create_new_version(parent, new_config, new_name)
        await self._audit.record(
            actor_type="user",
            actor_id=actor_id,
            action="version",
            resource_type="scenario",
            resource_id=new.id,
            after_data={
                "code": new.code,
                "version": new.version,
                "parent_id": parent.id,
            },
        )
        return new

    # ---------- 软删除 ----------

    async def soft_delete(
        self, scenario_id: str, *, actor_id: str | None = None
    ) -> None:
        s = await self.get_by_id(scenario_id)
        ok = await self._repo.soft_delete(scenario_id)
        if not ok:
            return
        await self._audit.record(
            actor_type="user",
            actor_id=actor_id,
            action="delete",
            resource_type="scenario",
            resource_id=scenario_id,
            before_data={"code": s.code, "version": s.version},
        )

    # ---------- DTO 转换辅助 ----------

    @staticmethod
    def to_response(s: Scenario) -> ScenarioResponse:
        return ScenarioResponse.from_model(s)
