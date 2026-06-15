"""ChatTurn Model — 单轮执行单元(含本 turn token 用量, Tortoise ORM).

对应表: ``chat_turns``
状态: ``pending / running / success / failed / cancelled``

注意: ``user_message_id`` / ``assistant_message_id`` 是 **软引用** (CharField),
不建 FK. 原因: messages 表有 ``turn_id`` FK 反向引用 chat_turns, 跟
``chat_turns.user_message_id`` FK 形成循环依赖, ``Tortoise.generate_schemas()``
不支持循环 FK. 软引用在应用层校验一致性, 跟 ``AuditLog.resource_id`` 同模式.
"""
from __future__ import annotations

from tortoise import fields
from tortoise.models import Model


class ChatTurn(Model):
    """单轮执行单元: 一次 user -> assistant 往返."""

    id = fields.UUIDField(pk=True, binary=False)

    session = fields.ForeignKeyField(
        "models.Session",
        related_name="turns",
        on_delete=fields.CASCADE,
        description="所属 session",
    )
    user_message_id = fields.CharField(
        max_length=36,
        null=True,
        description="触发本 turn 的 user 消息(软引用 messages.id, 不建 FK)",
    )
    assistant_message_id = fields.CharField(
        max_length=36,
        null=True,
        description="本 turn 产出的 assistant 消息(软引用 messages.id, 不建 FK)",
    )
    agent_name = fields.CharField(max_length=128, null=True, description="执行 agent 名(快照)")
    model = fields.CharField(max_length=128, null=True, description="调用模型(快照)")
    status = fields.CharField(max_length=32, default="pending", description="pending / running / success / failed / cancelled")
    started_at = fields.DatetimeField(null=True, description="执行开始")
    finished_at = fields.DatetimeField(null=True, description="执行结束")
    duration_ms = fields.IntField(null=True, description="耗时(毫秒)")

    cost = fields.DecimalField(max_digits=12, decimal_places=6, default=0, description="本 turn 花费 USD")
    tokens_input = fields.IntField(default=0, description="本 turn input tokens")
    tokens_output = fields.IntField(default=0, description="本 turn output tokens")
    tokens_reasoning = fields.IntField(default=0, description="本 turn reasoning tokens")
    tokens_cache_read = fields.IntField(default=0, description="本 turn cache read tokens")
    tokens_cache_write = fields.IntField(default=0, description="本 turn cache write tokens")

    error_code = fields.CharField(max_length=64, null=True, description="错误码")
    error_message = fields.TextField(null=True, description="错误信息")
    metadata = fields.JSONField(
        null=True,
        description="扩展元数据",
    )
    is_deleted = fields.BooleanField(default=False, description="软删除标记")
    deleted_at = fields.DatetimeField(null=True, description="软删除时间")
    created_at = fields.DatetimeField(auto_now_add=True, description="创建时间")
    updated_at = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "chat_turns"
        indexes = [
            ("session_id", "is_deleted", "created_at", "id"),
            ("status", "is_deleted", "created_at", "id"),
            ("started_at",),
        ]


__all__ = ["ChatTurn"]
