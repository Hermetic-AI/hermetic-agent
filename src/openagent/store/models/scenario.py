"""Scenario Model — 场景定义/快照(Tortoise ORM).

对应表: ``scenarios``
唯一约束: ``(code, version)`` — ``Meta.unique_together`` 表达.
自引用 FK: ``parent`` 指向上一个 version 的 scenario.
"""
from __future__ import annotations

from tortoise import fields
from tortoise.models import Model


class Scenario(Model):
    """场景定义/快照(支持版本链).

    业务规则: 同一 code 的 version 必须严格 +1, 跨版本无空洞. 顺序由
    ``create_new_version`` 业务方法保证, DB 唯一约束只防并发写冲突.
    """

    id = fields.UUIDField(pk=True, binary=False)

    code = fields.CharField(max_length=128, description="业务短码, 全局唯一(配合 version)")
    name = fields.CharField(max_length=255, description="场景名")
    version = fields.IntField(default=1, description="语义版本号, 同 code 自增")
    parent = fields.ForeignKeyField(
        "models.Scenario",
        related_name="versions",
        null=True,
        on_delete=fields.SET_NULL,
        description="上一版本场景 ID(版本演化链)",
    )
    description = fields.TextField(null=True, description="场景描述")
    config = fields.JSONField(description="ScenarioConfig Pydantic 序列化结果")
    source = fields.CharField(max_length=32, default="db", description="来源: db / yaml / builtin")
    status = fields.CharField(max_length=32, default="enabled", description="状态: enabled / disabled / draft")
    is_deleted = fields.BooleanField(default=False, description="软删除标记")
    deleted_at = fields.DatetimeField(null=True, description="软删除时间")
    created_at = fields.DatetimeField(auto_now_add=True, description="创建时间")
    updated_at = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "scenarios"
        unique_together = [("code", "version")]
        indexes = [
            ("status", "is_deleted", "updated_at", "id"),
            ("parent_id",),
            ("updated_at",),
        ]


__all__ = ["Scenario"]
