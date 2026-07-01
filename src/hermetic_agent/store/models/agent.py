"""store/models/agent.py — Agent 复合体 Tortoise ORM 模型.

Phase 3 of asset-registry plan: Agent 是复合体, 引用 Skill / McpConfig /
Prompt / Command 四类资产 (用 code 列表, 不建 FK). 见
``docs/designs/2026-06-30-asset-registry-tables.md`` §2.5.
"""
from __future__ import annotations

from tortoise import fields
from tortoise.models import Model


class Agent(Model):
    """Agent 复合体资产 (引用 4 类资产 + 自身 system_prompt / model / tool / network)."""

    id = fields.UUIDField(pk=True, binary=False)
    code = fields.CharField(max_length=128, unique=True, description="业务编码 (唯一标识)")
    name = fields.CharField(max_length=255, description="Agent 名称")
    version = fields.IntField(default=1, description="语义版本号")
    description = fields.TextField(null=True, default=None, description="Agent 描述")

    # === Agent 自身配置 ===
    system_prompt = fields.TextField(default="", description="Agent system_prompt 基础段")
    model = fields.CharField(max_length=128, default="openai/gpt-4o-mini", description="LLM 模型 ID")
    tool_level = fields.CharField(max_length=16, default="standard", description="工具权限: safe/standard/full")
    network = fields.CharField(max_length=16, default="local", description="网络权限: off/local/any")

    # === 引用 (不强制 FK, 软删除不级联) ===
    skill_codes = fields.JSONField(
        default=list,
        description="引用的 Skill.code 列表, 例 ['flight-query', 'booking-helper']",
    )
    mcp_server_codes = fields.JSONField(
        default=list,
        description="引用的 McpConfig.code 列表, 例 ['default_mcp', 'company-crm']",
    )
    prompt_codes = fields.JSONField(
        default=list,
        description="引用的 Prompt.code 列表, 顺序即拼到 system_prompt 后的顺序",
    )
    command_codes = fields.JSONField(
        default=list,
        description="引用的 Command.code 列表, 顺序即渲染 system_prompt_addendum 的顺序",
    )

    # === 通用字段 ===
    owner_user_id = fields.CharField(max_length=128, default="anonymous", index=True)
    visibility = fields.CharField(max_length=16, default="private", index=True)
    status = fields.CharField(max_length=32, default="enabled")
    is_deleted = fields.BooleanField(default=False, description="软删除")
    deleted_at = fields.DatetimeField(null=True, default=None)
    created_at = fields.DatetimeField(auto_now_add=True, description="创建时间")
    updated_at = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "agents"
        indexes = [
            ("status", "is_deleted"),
            ("owner_user_id", "visibility", "is_deleted"),
            ("model",),
            ("updated_at",),
        ]
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"Agent({self.code})"


__all__ = ["Agent"]
