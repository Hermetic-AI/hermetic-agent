"""AuditLogRepository ABC — 审计日志仓储接口."""

from __future__ import annotations

from abc import abstractmethod

from openagent.store.models.audit_log import AuditLog
from openagent.store.repositories._base import Repository


class AuditLogRepository(Repository[AuditLog]):
    """审计日志仓储接口(append-only)."""

    @abstractmethod
    async def list_by_resource(
        self,
        resource_type: str,
        resource_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]:
        """按资源列审计(按 seq ASC)."""

    @abstractmethod
    async def list_by_actor(
        self,
        actor_type: str,
        actor_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]:
        """按操作者列审计(按 created_at DESC)."""

    @abstractmethod
    async def next_seq(self, resource_type: str, resource_id: str) -> int:
        """取下一个事务序号(同 resource 下 +1). 事务内调用, 避免并发冲突."""


__all__ = ["AuditLogRepository"]
