"""AuditLogService — 审计写入."""

from __future__ import annotations

import structlog

from hermetic_agent.store.dto.audit_log import CreateAuditLogRequest
from hermetic_agent.store.models.audit_log import AuditLog
from hermetic_agent.store.repositories.audit_log_repo import AuditLogRepository

logger = structlog.get_logger(__name__)


class AuditLogService:
    """审计服务(只负责写, 读由其他服务按需调 repository)."""

    def __init__(self, repo: AuditLogRepository) -> None:
        self._repo = repo

    async def record(
        self,
        actor_type: str,
        action: str,
        resource_type: str,
        *,
        actor_id: str | None = None,
        resource_id: str | None = None,
        before_data: dict | None = None,
        after_data: dict | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        use_seq: bool = False,
    ) -> AuditLog:
        """写一条审计(append-only).

        Args:
            actor_type: 操作者类型 (user/system/admin/anonymous)
            action: 行为 (create/update/delete/state_change/login)
            resource_type: 资源类型 (session/message/scenario/turn)
            resource_id: 资源 ID (软引用)
            use_seq: True 时自动取下一序号 (同 resource 下 +1)
        """
        seq = None
        if use_seq and resource_id:
            seq = await self._repo.next_seq(resource_type, resource_id)
        log = AuditLog(
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            seq=seq,
            before_data=before_data,
            after_data=after_data,
            ip=ip,
            user_agent=user_agent,
            request_id=request_id,
        )
        return await self._repo.create(log)

    async def create_from_request(self, req: CreateAuditLogRequest) -> AuditLog:
        """从 DTO 创建审计(测试/外部调用)."""
        log = AuditLog(
            actor_type=req.actor_type,
            actor_id=req.actor_id,
            action=req.action,
            resource_type=req.resource_type,
            resource_id=req.resource_id,
            seq=req.seq,
            before_data=req.before_data,
            after_data=req.after_data,
            ip=req.ip,
            user_agent=req.user_agent,
            request_id=req.request_id,
            metadata=req.metadata,
        )
        return await self._repo.create(log)

    async def list_by_resource(
        self, resource_type: str, resource_id: str, *, limit: int = 100, offset: int = 0
    ) -> list[AuditLog]:
        return await self._repo.list_by_resource(
            resource_type, resource_id, limit=limit, offset=offset
        )

    async def list_by_actor(
        self, actor_type: str, actor_id: str, *, limit: int = 100, offset: int = 0
    ) -> list[AuditLog]:
        return await self._repo.list_by_actor(actor_type, actor_id, limit=limit, offset=offset)
