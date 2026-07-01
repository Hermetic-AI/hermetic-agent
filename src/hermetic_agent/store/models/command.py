"""store/models/command.py — Command 资产 Tortoise ORM 模型.

Phase 2 of asset-registry plan: 把 Command 从纯文件系统迁到数据库.
Command 是用户输入的斜杠命令 (例如 /summarize), 触发后拼到 chat system_prompt 后面.
"""
from __future__ import annotations

from tortoise import fields
from tortoise.models import Model


class Command(Model):
    """Agent Command 资产 (用户斜杠命令)."""

    id = fields.UUIDField(pk=True, binary=False)
    code = fields.CharField(max_length=128, description="业务短码")
    name = fields.CharField(max_length=255, description="Command 名称")
    version = fields.IntField(default=1, description="语义版本号")
    description = fields.TextField(null=True, default=None, description="Command 描述")
    slash_command = fields.CharField(
        max_length=64,
        description="用户输入的命令，如 /summarize；带 / 前缀",
    )
    system_prompt_addendum = fields.TextField(
        description="拼到 chat system_prompt 后面的说明文字，LLM 据此识别该 slash 的作用",
    )
    enabled = fields.BooleanField(default=True, description="是否启用")
    owner_user_id = fields.CharField(max_length=128, default="anonymous", index=True)
    visibility = fields.CharField(max_length=16, default="private", index=True)
    status = fields.CharField(max_length=32, default="enabled")
    is_deleted = fields.BooleanField(default=False, description="软删除")
    deleted_at = fields.DatetimeField(null=True, default=None)
    created_at = fields.DatetimeField(auto_now_add=True, description="创建时间")
    updated_at = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "commands"
        unique_together = [("code", "slash_command")]
        indexes = [
            ("status", "is_deleted"),
            ("owner_user_id", "visibility", "is_deleted"),
            ("slash_command",),
            ("updated_at",),
        ]
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"Command({self.code} {self.slash_command})"


__all__ = ["Command"]
