"""AuditLog Model — 审计日志(append-only, Tortoise ORM).

对应表: ``audit_logs``
软引用: ``resource_id`` 不建 FK, append-only 性质.
无 ``updated_at`` / ``is_deleted`` (append-only, 不修改不软删).
"""
from __future__ import annotations

from tortoise import fields
from tortoise.models import Model


class AuditLog(Model):
    """审计日志(append-only)."""

    id = fields.UUIDField(pk=True, binary=False)

    seq = fields.BigIntField(null=True, description="同资源下的事务序号(可选, 默认 NULL)")
    actor_type = fields.CharField(max_length=32, description="user / system / admin / anonymous")
    actor_id = fields.CharField(max_length=128, null=True, description="操作者 ID")
    action = fields.CharField(max_length=64, description="create / update / delete / login / state_change ...")
    resource_type = fields.CharField(max_length=64, description="session / message / scenario / turn / config ...")
    resource_id = fields.CharField(max_length=36, null=True, description="资源 ID(软引用, 不建 FK)")
    before_data = fields.JSONField(null=True, description="变更前快照")
    after_data = fields.JSONField(null=True, description="变更后快照")
    ip = fields.CharField(max_length=64, null=True, description="客户端 IP")
    user_agent = fields.CharField(max_length=512, null=True, description="UA")
    request_id = fields.CharField(max_length=64, null=True, description="链路 trace ID")
    metadata = fields.JSONField(
        null=True,
        description="扩展",
    )
    created_at = fields.DatetimeField(auto_now_add=True, description="写入时间")

    class Meta:
        table = "audit_logs"
        indexes = [
            ("resource_type", "resource_id", "seq", "created_at"),
            ("actor_type", "actor_id", "created_at", "id"),
            ("action", "created_at", "id"),
        ]


__all__ = ["AuditLog"]
