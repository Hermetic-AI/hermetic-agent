"""Message Model — 消息(parts 已拆出, Tortoise ORM).

对应表: ``messages``
角色: ``user / assistant / system / tool``
"""
from __future__ import annotations

from tortoise import fields
from tortoise.models import Model


class Message(Model):
    """消息(parts 已拆出到 parts 表)."""

    id = fields.UUIDField(pk=True, binary=False)

    session = fields.ForeignKeyField(
        "models.Session",
        related_name="messages",
        on_delete=fields.CASCADE,
        description="所属 session",
    )
    turn = fields.ForeignKeyField(
        "models.ChatTurn",
        related_name="messages",
        null=True,
        on_delete=fields.SET_NULL,
        description="所属 chat_turn(可空, 系统消息/老数据)",
    )
    role = fields.CharField(max_length=32, description="user / assistant / system / tool")
    content = fields.TextField(description="消息文本主体")
    metadata = fields.JSONField(
        null=True,
        description="扩展元数据(工具名/trace_id 等)",
    )
    is_deleted = fields.BooleanField(default=False, description="软删除标记")
    deleted_at = fields.DatetimeField(null=True, description="软删除时间")
    created_at = fields.DatetimeField(auto_now_add=True, description="创建时间")
    updated_at = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "messages"
        indexes = [
            ("session_id", "is_deleted", "created_at", "id"),
            ("turn_id",),
            ("role", "is_deleted"),
        ]


__all__ = ["Message"]
