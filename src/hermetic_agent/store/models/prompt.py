"""store/models/prompt.py — Prompt 资产 Tortoise ORM 模型.

Phase 3 of asset-registry plan: 把 Prompt 从纯文件系统迁到数据库.
Prompt 是一段可复用的 system_prompt 模板, 用 code 唯一标识.
"""
from __future__ import annotations

from tortoise import fields
from tortoise.models import Model


class Prompt(Model):
    """Agent Prompt 资产 (一段 LLM system_prompt 模板)."""

    id = fields.UUIDField(pk=True, binary=False)
    code = fields.CharField(max_length=128, unique=True, description="业务编码 (唯一标识)")
    name = fields.CharField(max_length=255, description="Prompt 名称")
    version = fields.IntField(default=1, description="语义版本号 (同 code 自增)")
    description = fields.TextField(null=True, default=None, description="Prompt 描述")
    content = fields.TextField(description="Prompt 模板正文 (LLM system_prompt 来源)")
    owner_user_id = fields.CharField(max_length=128, default="anonymous", index=True)
    visibility = fields.CharField(max_length=16, default="private", index=True)
    status = fields.CharField(max_length=32, default="enabled")
    is_deleted = fields.BooleanField(default=False, description="软删除")
    deleted_at = fields.DatetimeField(null=True, default=None)
    created_at = fields.DatetimeField(auto_now_add=True, description="创建时间")
    updated_at = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "prompts"
        indexes = [
            ("status", "is_deleted"),
            ("owner_user_id", "visibility", "is_deleted"),
            ("updated_at",),
        ]
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"Prompt({self.code})"


__all__ = ["Prompt"]
