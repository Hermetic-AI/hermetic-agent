"""API request/response schemas and app-state accessors.

Shared Pydantic models and request-side helpers used by every
`*_controller.py` in the api/ package.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sanic.request import Request

from hermetic_agent.mcp.registry import MCPRegistry
from hermetic_agent.providers.agent_bridge import AgentBridge
from hermetic_agent.skills.registry import SkillRegistry

# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    """聊天请求的请求体模型。

    用于 `/agent/chat` 与 `/agent/chat/stream` 两个端点，承载用户消息、
    会话/Agent 选择、模型与可选的 Skills/Tools 列表。
    """

    message: str = Field(..., min_length=1, description="用户消息",
                         examples=["帮我查一下从北京到上海的航班"])
    session_id: str | None = Field(None, description="会话 ID，不提供则创建新会话")
    agent_name: str | None = Field(None, description="指定 Agent 实例")
    model: str | None = Field(None, description="指定模型")
    system_prompt: str | None = Field(None, description="系统提示词")
    timeout: float | None = Field(None, description="超时时间（秒）")
    skills: list[str] | None = Field(None, description="技能名称列表")
    tools: list[str] | None = Field(None, description="工具名称列表")
    extra_opencode_mcp: dict[str, dict] = Field(
        default_factory=dict,
        description=(
            "Per-request 注入到 opencode mcpServers 的额外 server; "
            "由 chat_inject 钩子在 chat handler 顶部合并进 bridge.chat。"
        ),
    )


class ChatResponse(BaseModel):
    """聊天调用的统一响应模型。

    同步和流式结束后的最终结果都会规约到该模型。
    """

    success: bool
    session_id: str
    agent_name: str
    result: Any | None = None
    error: str | None = None
    duration: float | None = None
    # F2: scenario 命中信息 (来自 ScenarioMiddleware)
    scenario: dict | None = None
    routing: dict | None = None


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


class CreateSessionRequest(BaseModel):
    """创建会话请求体：选定 Agent 与可选的模型/系统提示/会话 ID。"""

    agent_name: str = Field(..., description="Agent 实例名称")
    model: str | None = Field(None, description="指定模型")
    system_prompt: str | None = Field(None, description="系统提示词")
    session_id: str | None = Field(None, description="指定会话 ID（用于恢复）")


class CreateSessionResponse(BaseModel):
    """创建会话的响应：包含会话归属的 Agent 与 base_url。"""

    success: bool
    session_id: str
    agent_name: str
    agent_base_url: str
    model: str | None = None


# ---------------------------------------------------------------------------
# Generic
# ---------------------------------------------------------------------------


class ErrorResponse(BaseModel):
    """统一的错误响应模型。"""

    success: bool = False
    error: str


# ---------------------------------------------------------------------------
# Skills / Tools
# ---------------------------------------------------------------------------


class SkillResponse(BaseModel):
    """Skill 注册表相关接口的响应模型。

    列表接口使用 `skills` 字段；单条接口使用 `skill` 字段。
    """

    success: bool = True
    skill: dict[str, Any] | None = None
    skills: list[dict[str, Any]] | None = None
    error: str | None = None


class ToolResponse(BaseModel):
    """MCP 工具注册表相关接口的响应模型。

    列表接口使用 `tools` 字段；单条接口使用 `tool` 字段。
    """

    success: bool = True
    tool: dict[str, Any] | None = None
    tools: list[dict[str, Any]] | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# App state accessors
# ---------------------------------------------------------------------------


def get_bridge(request: Request) -> AgentBridge:
    """从 app.ctx 取出启动期注入的 AgentBridge 实例。

    Returns:
        当前 Sanic 应用持有的 AgentBridge。
    """
    return request.app.ctx.bridge


def get_skill_registry(request: Request) -> SkillRegistry:
    """从 app.ctx 取出启动期注入的 SkillRegistry 实例。

    Returns:
        当前 Sanic 应用持有的 SkillRegistry。
    """
    return request.app.ctx.skill_registry


def get_mcp_registry(request: Request) -> MCPRegistry:
    """从 app.ctx 取出启动期注入的 MCPRegistry 实例。

    Returns:
        当前 Sanic 应用持有的 MCPRegistry。
    """
    return request.app.ctx.mcp_registry
