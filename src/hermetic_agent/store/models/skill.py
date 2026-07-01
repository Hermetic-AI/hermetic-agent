"""store/models/skill.py — Skill 资产 Tortoise ORM 模型.

Phase 3: 将 Skill 从纯文件系统迁移到数据库.
模型设计遵循 scenario.py 的命名/字段约定.
"""

from __future__ import annotations

from tortoise import fields
from tortoise.models import Model


class Skill(Model):
    """Agent Skill 资产 (对应 SKILL.md + skill.yaml).

    基座 SkillRegistry 从本表加载, 再结合文件系统的 SKILL.md 作降级.
    详见 ``docs/core-skill-boundary.md`` §4.2.
    """

    id = fields.UUIDField(pk=True)
    code = fields.CharField(max_length=128, unique=True, description="业务编码 (唯一标识)")
    name = fields.CharField(max_length=255, description="SKILL 名称")
    version = fields.IntField(default=1, description="语义版本号 (同 code 自增)")
    description = fields.TextField(null=True, default=None, description="SKILL 描述")
    triggers = fields.JSONField(null=True, default=None, description="触发词列表 (e.g. ['echo', '回声'])")
    input_schema = fields.JSONField(null=True, default=None, description="输入 JSON Schema")
    output_schema = fields.JSONField(null=True, default=None, description="输出 JSON Schema")
    prompt_template = fields.TextField(null=True, default=None, description="SKILL.md body (LLM 系统提示词模板)")
    mcp_tools = fields.JSONField(null=True, default=None, description="MCP 工具声明 (``{server: {tools: [...]}}``)")
    required_envs = fields.JSONField(null=True, default=None, description="SKILL 需要的 env 变量声明")
    config = fields.JSONField(null=True, default=None, description="skill.yaml 完整配置 (JSON)")
    source = fields.CharField(max_length=32, default="db", description="来源: db / yaml / builtin")
    status = fields.CharField(max_length=32, default="enabled", description="enabled / disabled / draft")
    owner_user_id = fields.CharField(max_length=128, default="anonymous", index=True)
    visibility = fields.CharField(max_length=16, default="private", index=True)
    file_count = fields.IntField(default=0, description="MinIO 中文件总数")
    file_fingerprint = fields.CharField(max_length=64, default="", description="所有 etag 排序 sha1")
    is_deleted = fields.BooleanField(default=False, description="软删除")
    deleted_at = fields.DatetimeField(null=True, default=None)
    created_at = fields.DatetimeField(auto_now_add=True, description="创建时间")
    updated_at = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "skills"
        indexes = [
            ("status", "is_deleted"),
            ("owner_user_id", "visibility", "is_deleted"),
            ("updated_at",),
        ]
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"Skill({self.code} v{self.version})"


__all__ = ["Skill"]
