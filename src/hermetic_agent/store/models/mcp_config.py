"""store/models/mcp_config.py — MCP Server 配置 Tortoise ORM 模型.

Phase 3: 将 MCP 配置从 work/mcp/*.json 迁移到数据库.
"""

from __future__ import annotations

from tortoise import fields
from tortoise.models import Model


class McpConfig(Model):
    """MCP Server 配置 (对应 work/mcp/servers.json 中的单个 server).

    每个 McpConfig 记录代表一个 MCP server 的 wire-level 配置.
    opencode 启动时从本表渲染 ``mcpServers`` 块.
    """

    id = fields.UUIDField(pk=True)
    code = fields.CharField(max_length=128, unique=True, description="MCP server 唯一编码 (e.g. 'my-mcp')")
    name = fields.CharField(max_length=255, default="", description="Server 显示名称")
    mcp_type = fields.CharField(max_length=32, default="http", description="类型: http / sse / stdio")
    url = fields.CharField(max_length=2048, null=True, default=None, description="HTTP/SSE 端点 URL")
    command = fields.CharField(max_length=512, null=True, default=None, description="stdio 启动命令")
    args = fields.JSONField(null=True, default=None, description="stdio 启动参数列表")
    env = fields.JSONField(null=True, default=None, description="传给子进程的环境变量")
    cwd = fields.CharField(max_length=1024, null=True, default=None, description="stdio cwd")
    headers = fields.JSONField(null=True, default=None, description="HTTP header (key→value)")
    allowed_tools = fields.JSONField(null=True, default=None, description="工具白名单")
    disabled = fields.BooleanField(default=False, description="是否禁用")
    config = fields.JSONField(null=True, default=None, description="完整配置 JSON (兜底)")
    source = fields.CharField(max_length=32, default="db", description="来源: db / json / env")
    status = fields.CharField(max_length=32, default="enabled", description="enabled / disabled / draft")
    is_deleted = fields.BooleanField(default=False)
    deleted_at = fields.DatetimeField(null=True, default=None)

    class Meta:
        table = "mcp_configs"
        indexes = (("status", "is_deleted"),)
        ordering = ["code"]

    def __str__(self) -> str:
        return f"McpConfig({self.code} [{self.mcp_type}])"


__all__ = ["McpConfig"]
