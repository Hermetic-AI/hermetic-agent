"""Session Model — 对话主表(含 token/cost 聚合, Tortoise ORM).

对应表: ``sessions``
聚合字段 ``message_count`` / ``cost`` / ``tokens_*`` 由 chat_turns 反向汇总,
不强一致, 业务可接受秒级延迟.

ID 格式: 不用 ``UUIDField``, 改 ``CharField(max_length=64)`` 接受任意字符串.
原因: opencode serve 返回的 session id 是 ``ses_xxx`` 短串 (不是 UUID), 
直接写 UUIDField 会抛 ``badly formed hexadecimal UUID string``. Hub 内部
自己生成的 session id 仍走 ``uuid.uuid4()`` (str(uuid4())) 默认值.
"""
from __future__ import annotations

import uuid

from tortoise import fields
from tortoise.models import Model


class Session(Model):
    """对话主表."""

    id = fields.CharField(
        max_length=64,
        pk=True,
        default=lambda: str(uuid.uuid4()),
        description="会话 ID (opencode 返回的 ``ses_xxx`` 或 Hub 生成的 UUID 字符串)",
    )

    user_id = fields.CharField(max_length=64, default="", description="所属用户标识(外部系统传入)")
    title = fields.CharField(max_length=255, default="New Session", description="会话标题")
    model = fields.CharField(max_length=128, null=True, description="LLM 模型标识")
    agent_name = fields.CharField(max_length=128, default="", description="使用的 Agent 名")
    scenario = fields.ForeignKeyField(
        "models.Scenario",
        related_name="sessions",
        null=True,
        on_delete=fields.SET_NULL,
        description="关联场景 ID",
    )
    status = fields.CharField(
        max_length=32,
        default="active",
        description="状态: active / closed / archived",
    )

    message_count = fields.IntField(default=0, description="消息条数缓存")
    cost = fields.DecimalField(max_digits=12, decimal_places=6, default=0, description="累计花费 USD")
    tokens_input = fields.IntField(default=0, description="累计 input tokens")
    tokens_output = fields.IntField(default=0, description="累计 output tokens")
    tokens_reasoning = fields.IntField(default=0, description="累计 reasoning tokens")
    tokens_cache_read = fields.IntField(default=0, description="累计 cache read tokens")
    tokens_cache_write = fields.IntField(default=0, description="累计 cache write tokens")

    metadata = fields.JSONField(
        null=True,
        description="扩展元数据",
    )
    is_deleted = fields.BooleanField(default=False, description="软删除标记")
    deleted_at = fields.DatetimeField(null=True, description="软删除时间")
    created_at = fields.DatetimeField(auto_now_add=True, description="创建时间")
    updated_at = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "sessions"
        indexes = [
            ("user_id", "is_deleted", "updated_at", "id"),
            ("agent_name", "is_deleted", "updated_at", "id"),
            ("scenario_id",),
            ("updated_at",),
        ]


__all__ = ["Session"]
