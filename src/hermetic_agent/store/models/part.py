"""Part Model — 消息分段(原 messages.parts JSON 拆出, 加 session_id 冗余, Tortoise ORM).

对应表: ``parts``
类型: ``text / image / tool_call / tool_result / file``
冗余: ``session_id`` 冗余, 避免按 session 查 part 时 JOIN messages.
"""
from __future__ import annotations

from tortoise import fields
from tortoise.models import Model


class Part(Model):
    """消息分段."""

    id = fields.UUIDField(pk=True, binary=False)

    message = fields.ForeignKeyField(
        "models.Message",
        related_name="parts",
        on_delete=fields.CASCADE,
        description="所属 message",
    )
    session = fields.ForeignKeyField(
        "models.Session",
        related_name="parts",
        on_delete=fields.CASCADE,
        description="冗余: 所属 session(避免 JOIN message)",
    )
    part_type = fields.CharField(max_length=32, description="text / image / tool_call / tool_result / file / ...")
    content = fields.TextField(null=True, description="段内容(文本/序列化结果)")
    position = fields.IntField(default=0, description="段在 message 内的顺序")
    metadata = fields.JSONField(
        null=True,
        description="扩展元数据(工具名/参数等)",
    )
    is_deleted = fields.BooleanField(default=False, description="软删除标记")
    deleted_at = fields.DatetimeField(null=True, description="软删除时间")
    created_at = fields.DatetimeField(auto_now_add=True, description="创建时间")
    updated_at = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "parts"
        indexes = [
            ("message_id", "is_deleted", "position", "id"),
            ("session_id", "is_deleted", "created_at", "id"),
            ("part_type", "is_deleted", "created_at", "id"),
        ]


__all__ = ["Part"]
