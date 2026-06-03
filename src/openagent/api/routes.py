"""REST API Routes - REST API 路由

提供 Agent 调度相关的 REST API 端点：
- POST /agent/chat - 发送消息并获取回复
- POST /agent/chat/stream - 流式发送消息并获取回复 (SSE)
- POST /agent/session - 创建新会话
- GET /agent/session/{session_id} - 获取会话信息
- GET /agent/session/{session_id}/messages - 获取会话历史
- DELETE /agent/session/{session_id} - 删除会话
- POST /agent/session/{session_id}/abort - 中止运行中的会话
- GET /agent/skills - 获取所有技能
- POST /agent/skills - 注册新技能
- GET /agent/tools - 获取所有工具
- POST /agent/tools - 注册新工具
- PATCH /agent/tools/<name>/enabled - 启用/禁用工具
- GET /health - 健康检查
- GET /ready - 就绪检查
- GET /pool/stats - 实例池统计
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field
from sanic import Blueprint, HTTPResponse, text
from sanic.response import json as JSONResponse
from sanic.response.types import ResponseStream
from sanic.request import Request

from sanic_ext import openapi as sanic_openapi

doc_summary = sanic_openapi.summary
doc_description = sanic_openapi.description
doc_tag = sanic_openapi.tag
operation = sanic_openapi.operation
response = sanic_openapi.response
body = sanic_openapi.body

from openagent.providers.agent_bridge import AgentBridge
from openagent.providers.base import ChatMessage
from openagent.skills.registry import Skill, SkillRegistry
from openagent.mcp.registry import MCPRegistry, MCPTool
from openagent.streaming import StreamEvent

router = Blueprint("agent_scheduler", url_prefix="/agent")


# --- Request/Response Models ---


class ChatRequest(BaseModel):
    """聊天请求"""

    message: str = Field(
        ...,
        description="用户消息",
        min_length=1,
        examples=["帮我查一下从北京到上海的航班"],
    )
    session_id: Optional[str] = Field(
        None,
        description="会话 ID，不提供则创建新会话",
        examples=["a1b2c3d4-1234-5678-9abc-def012345678"],
    )
    agent_name: Optional[str] = Field(
        None,
        description="指定 Agent 实例",
        examples=["agent-shanghai"],
    )
    model: Optional[str] = Field(
        None,
        description="指定模型",
        examples=["claude-sonnet-4-5"],
    )
    system_prompt: Optional[str] = Field(
        None,
        description="系统提示词",
        examples=["你是一个旅行助手"],
    )
    timeout: Optional[float] = Field(
        None,
        description="超时时间（秒）",
        examples=[120.0],
    )
    skills: Optional[list[str]] = Field(
        None,
        description="技能名称列表",
        examples=[["weather", "calendar"]],
    )
    tools: Optional[list[str]] = Field(
        None,
        description="工具名称列表",
        examples=[["web_search", "send_email"]],
    )


class ChatResponse(BaseModel):
    """聊天响应"""

    success: bool = Field(..., examples=[True])
    session_id: str = Field(..., examples=["a1b2c3d4-1234-5678-9abc-def012345678"])
    agent_name: str = Field(..., examples=["agent-shanghai"])
    result: Optional[Any] = Field(
        None,
        examples=[
            {
                "message": {
                    "role": "assistant",
                    "content": "已为你查询 2026-06-01 北京→上海航班，共找到 12 个班次。",
                },
                "tool_calls": [],
            }
        ],
    )
    error: Optional[str] = Field(None, examples=[None])
    duration: Optional[float] = Field(None, examples=[1.234])


class CreateSessionRequest(BaseModel):
    """创建会话请求"""

    agent_name: str = Field(..., description="Agent 实例名称", examples=["agent-shanghai"])
    model: Optional[str] = Field(None, description="指定模型", examples=["claude-sonnet-4-5"])
    system_prompt: Optional[str] = Field(None, description="系统提示词", examples=["你是一个旅行助手"])
    session_id: Optional[str] = Field(
        None,
        description="指定会话 ID（用于恢复）",
        examples=["a1b2c3d4-1234-5678-9abc-def012345678"],
    )


class CreateSessionResponse(BaseModel):
    """创建会话响应"""

    success: bool = Field(..., examples=[True])
    session_id: str = Field(..., examples=["a1b2c3d4-1234-5678-9abc-def012345678"])
    agent_name: str = Field(..., examples=["agent-shanghai"])
    agent_base_url: str = Field(..., examples=["http://localhost:4096"])
    model: Optional[str] = Field(None, examples=["claude-sonnet-4-5"])


class ErrorResponse(BaseModel):
    """错误响应"""

    success: bool = Field(False, examples=[False])
    error: str = Field(..., examples=["Session not found"])


class SkillResponse(BaseModel):
    """技能响应"""

    success: bool = Field(True, examples=[True])
    skill: Optional[dict[str, Any]] = Field(
        None,
        examples=[
            {
                "name": "weather",
                "description": "查询天气",
                "version": "1.0.0",
                "triggers": ["weather", "天气"],
                "input_schema": {"city": "string"},
                "output_schema": {"temp": "number", "desc": "string"},
                "mcp_tools": [],
                "source": "registry",
            }
        ],
    )
    skills: Optional[list[dict[str, Any]]] = Field(
        None,
        examples=[
            [
                {
                    "name": "weather",
                    "description": "查询天气",
                    "version": "1.0.0",
                    "triggers": ["weather", "天气"],
                    "input_schema": {"city": "string"},
                    "output_schema": {"temp": "number", "desc": "string"},
                    "mcp_tools": [],
                    "source": "registry",
                }
            ]
        ],
    )
    error: Optional[str] = Field(None, examples=[None])


class ToolResponse(BaseModel):
    """工具响应"""

    success: bool = Field(True, examples=[True])
    tool: Optional[dict[str, Any]] = Field(
        None,
        examples=[{"name": "web_search", "description": "Web 搜索", "enabled": True}],
    )
    tools: Optional[list[dict[str, Any]]] = Field(
        None,
        examples=[
            [
                {
                    "name": "web_search",
                    "description": "Web 搜索",
                    "input_schema": {"query": "string"},
                    "enabled": True,
                }
            ]
        ],
    )
    error: Optional[str] = Field(None, examples=[None])


# --- App State Accessors ---


def get_bridge(request: Request) -> AgentBridge:
    """获取 AgentBridge 实例"""
    return request.app.ctx.bridge


def get_storage(request: Request) -> Any:
    """获取 StorageBackend 实例"""
    return request.app.ctx.storage


def _resolve_session_directory(request: Request) -> str | None:
    """从 ScenarioMiddleware 注入的 ``request.ctx.scenario`` 提取工作区.

    ScenarioConfig.workspace.workspace_dirs 在 ``loader.py`` 加载 YAML 时
    已经过 placeholder 解析(``${PROJECT_DIR}`` → 实际路径),直接取
    ``[0]`` 即可。

    未命中 scenario 时返回 ``None`` — opencode serve 会回落到启动时的
    ``--cwd``,与 launcher.py 行为一致。
    """
    scenario = getattr(request.ctx, "scenario", None)
    if scenario is None:
        return None
    dirs = scenario.workspace.workspace_dirs
    return dirs[0] if dirs else None


def get_skill_registry(request: Request) -> SkillRegistry:
    """获取 SkillRegistry 实例"""
    return request.app.ctx.skill_registry


def get_mcp_registry(request: Request) -> MCPRegistry:
    """获取 MCPRegistry 实例"""
    return request.app.ctx.mcp_registry


# --- Routes ---


@router.post("/chat")
@doc_summary("发送消息并获取回复")
@doc_description(
    "向 Agent 发送一条用户消息并同步等待完整回复。\n\n"
    "如果不提供 `session_id`，会自动创建新会话；提供则继续已有会话的上下文。"
)
@doc_tag("Chat")
@operation("agentChat")
@body(ChatRequest)
@response(200, ChatResponse, description="成功返回 Agent 回复")
@response(400, ErrorResponse, description="参数错误或无可用 Agent")
@response(500, ErrorResponse, description="服务器内部错误")
async def chat(request: Request) -> JSONResponse:
    """发送消息并获取回复

    如果不提供 session_id，则创建新会话。
    """
    bridge = get_bridge(request)
    json_body = ChatRequest(**request.json)

    try:
        if json_body.session_id:
            # 继续已有会话
            message = ChatMessage(role="user", content=json_body.message)
            result = await bridge.chat(
                session_id=json_body.session_id,
                messages=[message],
                model=json_body.model,
                system_prompt=json_body.system_prompt,
                skills=json_body.skills,
                tools=json_body.tools,
                timeout=json_body.timeout,
            )
            session_info = None
            for agent_name in bridge.list_agents():
                try:
                    provider = bridge.get_provider(agent_name)
                    # Get session info from provider if possible
                    session_info = getattr(provider, 'get_session', lambda x: None)(json_body.session_id)
                    if session_info:
                        break
                except Exception:
                    continue
            agent_name = session_info.agent_name if session_info else "unknown"
        else:
            # 创建新会话并发送消息
            if not json_body.agent_name:
                agents = bridge.list_agents()
                if not agents:
                    return JSONResponse(
                        ErrorResponse(error="No agents registered").model_dump(),
                        status=400,
                    )
                agent_name = agents[0]
            else:
                agent_name = json_body.agent_name

            session_info = await bridge.create_session(
                agent_name=agent_name,
                directory=_resolve_session_directory(request),
            )
            session_id = session_info.session_id

            message = ChatMessage(role="user", content=json_body.message)
            result = await bridge.chat(
                session_id=session_id,
                messages=[message],
                model=json_body.model,
                system_prompt=json_body.system_prompt,
                skills=json_body.skills,
                tools=json_body.tools,
                timeout=json_body.timeout,
            )

        return JSONResponse(
            ChatResponse(
                success=result.success,
                session_id=result.session_id or json_body.session_id or "",
                agent_name=agent_name,
                result=(
                    {
                        "message": {
                            "role": result.message.role,
                            "content": result.message.content,
                        },
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "name": tc.name,
                                "input": tc.input,
                            }
                            for tc in (result.tool_calls or [])
                        ],
                        "stop_reason": result.stop_reason,
                    }
                    if result.message
                    else None
                ),
                error=result.error,
                duration=result.duration,
            ).model_dump()
        )

    except Exception as e:
        return JSONResponse(
            ErrorResponse(error=str(e)).model_dump(),
            status=500,
        )


@router.post("/chat/stream")
@doc_summary("发送消息并获取流式回复 (SSE)")
@doc_description(
    "向 Agent 发送一条用户消息并以 Server-Sent Events 形式流式返回响应。\n\n"
    "如果不提供 `session_id`，会自动创建新会话。"
)
@doc_tag("Chat")
@operation("agentChatStream")
@body(ChatRequest)
async def chat_stream(request: Request) -> ResponseStream:
    """发送消息并获取流式回复 (SSE)

    如果不提供 session_id，则创建新会话。
    """
    bridge = get_bridge(request)
    json_body = ChatRequest(**request.json)

    async def streaming_fn(resp: ResponseStream):
        try:
            if json_body.session_id:
                # Verify session exists
                session_id = json_body.session_id
                agent_name = None
                for agent in bridge.list_agents():
                    try:
                        provider = bridge.get_provider(agent)
                        session_info = getattr(provider, 'get_session', lambda x: None)(session_id)
                        if session_info:
                            agent_name = agent
                            break
                    except Exception:
                        continue
                if agent_name is None:
                    await resp.write(StreamEvent.error(message="Session not found").to_sse())
                    await resp.eof()
                    return
            else:
                # Create new session
                if not json_body.agent_name:
                    agents = bridge.list_agents()
                    if not agents:
                        await resp.write(StreamEvent.error(message="No agents registered").to_sse())
                        await resp.eof()
                        return
                    agent_name = agents[0]
                else:
                    agent_name = json_body.agent_name

                session_info = await bridge.create_session(
                    agent_name=agent_name,
                    directory=_resolve_session_directory(request),
                )
                session_id = session_info.session_id

            await resp.write(StreamEvent.session(session_id=session_id).to_sse())

            message = ChatMessage(role="user", content=json_body.message)

            iterator = await bridge.chat(
                session_id=session_id,
                messages=[message],
                model=json_body.model,
                system_prompt=json_body.system_prompt,
                skills=json_body.skills,
                tools=json_body.tools,
                timeout=json_body.timeout,
                stream=True,
            )
            async for event in iterator:
                await resp.write(event.to_sse())

            await resp.write(StreamEvent.done().to_sse())

        except Exception as e:
            await resp.write(StreamEvent.error(message=str(e)).to_sse())
        finally:
            await resp.eof()

    return ResponseStream(
        streaming_fn,
        status=200,
        content_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/session")
@doc_summary("创建新会话")
@doc_description("在指定 Agent 实例上创建新的会话上下文，可用于后续 chat 调用。")
@doc_tag("Session")
@operation("createSession")
@body(CreateSessionRequest)
@response(201, CreateSessionResponse, description="会话创建成功")
@response(404, ErrorResponse, description="Agent 实例不存在")
@response(500, ErrorResponse, description="服务器内部错误")
async def create_session(request: Request) -> JSONResponse:
    """创建新会话"""
    bridge = get_bridge(request)
    json_body = CreateSessionRequest(**request.json)

    try:
        session_info = await bridge.create_session(
            agent_name=json_body.agent_name,
            session_id=json_body.session_id,
            directory=_resolve_session_directory(request),
        )

        return JSONResponse(
            CreateSessionResponse(
                success=True,
                session_id=session_info.session_id,
                agent_name=session_info.agent_name,
                agent_base_url=session_info.agent_base_url,
                model=session_info.model,
            ).model_dump(),
            status=201,
        )

    except ValueError as e:
        return JSONResponse(
            ErrorResponse(error=str(e)).model_dump(),
            status=404,
        )
    except RuntimeError as e:
        return JSONResponse(
            ErrorResponse(error=str(e)).model_dump(),
            status=500,
        )


@router.get("/session/<session_id>")
@doc_summary("获取会话信息")
@doc_description("根据 session_id 查询会话的元信息（所属 Agent、模型、URL 等）。")
@doc_tag("Session")
@operation("getSession")
@response(200, CreateSessionResponse, description="返回会话信息")
@response(404, ErrorResponse, description="会话不存在")
async def get_session(request: Request, session_id: str) -> JSONResponse:
    """获取会话信息"""
    bridge = get_bridge(request)

    agent_name = bridge._get_agent_for_session(session_id)
    if agent_name is None:
        return JSONResponse(
            ErrorResponse(error=f"Session '{session_id}' not found").model_dump(),
            status=404,
        )

    try:
        provider = bridge.get_provider(agent_name)
        session_info = getattr(provider, 'get_session', lambda x: None)(session_id)
        if session_info is None:
            return JSONResponse(
                ErrorResponse(error=f"Session '{session_id}' not found").model_dump(),
                status=404,
            )

        return JSONResponse(
            {
                "success": True,
                "session_id": session_info.session_id,
                "agent_name": session_info.agent_name,
                "agent_base_url": session_info.agent_base_url,
                "model": session_info.model,
            }
        )
    except KeyError:
        return JSONResponse(
            ErrorResponse(error=f"Session '{session_id}' not found").model_dump(),
            status=404,
        )


@router.get("/session/<session_id>/messages")
@doc_summary("获取会话历史消息")
@doc_description("返回该会话下所有历史消息（按时间顺序）。")
@doc_tag("Session")
@operation("getSessionMessages")
@response(200, {"success": bool, "session_id": str, "messages": list}, description="返回消息列表")
@response(404, ErrorResponse, description="会话不存在")
async def get_messages(request: Request, session_id: str) -> JSONResponse:
    """获取会话历史消息"""
    bridge = get_bridge(request)

    try:
        messages = await bridge.get_messages(session_id)
        return JSONResponse(
            {
                "success": True,
                "session_id": session_id,
                "messages": [msg.content if hasattr(msg, 'content') else str(msg) for msg in messages],
            }
        )
    except ValueError as e:
        return JSONResponse(
            ErrorResponse(error=str(e)).model_dump(),
            status=404,
        )
    except RuntimeError as e:
        return JSONResponse(
            ErrorResponse(error=str(e)).model_dump(),
            status=500,
        )


@router.delete("/session/<session_id>")
@doc_summary("删除会话")
@doc_description("删除指定会话及其历史消息。")
@doc_tag("Session")
@operation("deleteSession")
@response(200, {"success": bool, "session_id": str}, description="删除结果")
@response(404, ErrorResponse, description="会话不存在")
async def delete_session(request: Request, session_id: str) -> JSONResponse:
    """删除会话"""
    bridge = get_bridge(request)

    try:
        success = await bridge.delete_session(session_id)
        return JSONResponse(
            {
                "success": success,
                "session_id": session_id,
            }
        )
    except ValueError as e:
        return JSONResponse(
            ErrorResponse(error=str(e)).model_dump(),
            status=404,
        )


@router.post("/session/<session_id>/abort")
@doc_summary("中止运行中的会话")
@doc_description("打断当前正在执行的 Agent 调用。")
@doc_tag("Session")
@operation("abortSession")
@response(200, {"success": bool, "session_id": str}, description="中止结果")
@response(404, ErrorResponse, description="会话不存在")
async def abort_session(request: Request, session_id: str) -> JSONResponse:
    """中止运行中的会话"""
    bridge = get_bridge(request)

    try:
        success = await bridge.abort(session_id)
        return JSONResponse(
            {
                "success": success,
                "session_id": session_id,
            }
        )
    except ValueError as e:
        return JSONResponse(
            ErrorResponse(error=str(e)).model_dump(),
            status=404,
        )


# --- Skills Endpoints ---


@router.get("/skills")
@doc_summary("获取所有技能")
@doc_description("列出当前已注册的全部 Skill。")
@doc_tag("Skills")
@operation("listSkills")
@response(200, SkillResponse, description="技能列表")
async def get_skills(request: Request) -> JSONResponse:
    """获取所有技能"""
    skill_registry = get_skill_registry(request)

    skills = skill_registry.list_all()
    return JSONResponse(
        SkillResponse(
            success=True,
            skills=[
                {
                    "name": s.name,
                    "description": s.description,
                    "version": s.version,
                    "triggers": s.triggers,
                    "input_schema": s.input_schema,
                    "output_schema": s.output_schema,
                    "mcp_tools": s.mcp_tools,
                    "source": s.source,
                }
                for s in skills
            ],
        ).model_dump()
    )


@router.post("/skills")
@doc_summary("注册新技能")
@doc_description(
    "动态注册一个 Skill。Body 字段：\n"
    "- `name` (必填): 技能唯一名称\n"
    "- `description`: 描述\n"
    "- `triggers`: 触发关键词列表\n"
    "- `input_schema` / `output_schema`: JSON Schema\n"
    "- `prompt_template`: 提示词模板\n"
    "- `mcp_tools`: 关联 MCP 工具名"
)
@doc_tag("Skills")
@operation("registerSkill")
@body(
    {
        "application/json": {
            "schema": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string", "example": "weather", "description": "技能名称"},
                    "description": {"type": "string", "example": "查询天气"},
                    "version": {"type": "string", "example": "1.0.0"},
                    "triggers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "example": ["weather", "天气"],
                    },
                    "input_schema": {"type": "object", "additionalProperties": True},
                    "output_schema": {"type": "object", "additionalProperties": True},
                    "prompt_template": {"type": "string"},
                    "mcp_tools": {"type": "array", "items": {"type": "string"}},
                    "source": {"type": "string", "example": "api"},
                },
            },
            "example": {
                "name": "weather",
                "description": "查询天气",
                "triggers": ["weather", "天气"],
                "input_schema": {"city": "string"},
                "output_schema": {"temp": "number", "desc": "string"},
            },
        }
    }
)
@response(201, SkillResponse, description="注册成功")
@response(400, ErrorResponse, description="参数错误")
async def register_skill(request: Request) -> JSONResponse:
    """注册新技能

    Body: {"name": "skill_name", "description": "...", "triggers": [...], ...}
    """
    skill_registry = get_skill_registry(request)
    body = request.json

    if not body or "name" not in body:
        return JSONResponse(
            ErrorResponse(error="name is required").model_dump(),
            status=400,
        )

    try:
        skill = Skill(
            name=str(body["name"]),
            description=str(body.get("description", "")),
            version=str(body.get("version", "1.0.0")),
            triggers=list(body.get("triggers", [])),
            input_schema=body.get("input_schema", {}),
            output_schema=body.get("output_schema", {}),
            prompt_template=str(body.get("prompt_template", "")),
            mcp_tools=list(body.get("mcp_tools", [])),
            source=str(body.get("source", "api")),
        )
        skill_registry.register(skill)
        return JSONResponse(
            SkillResponse(
                success=True,
                skill={
                    "name": skill.name,
                    "description": skill.description,
                    "version": skill.version,
                    "triggers": skill.triggers,
                    "input_schema": skill.input_schema,
                    "output_schema": skill.output_schema,
                    "mcp_tools": skill.mcp_tools,
                    "source": skill.source,
                },
            ).model_dump(),
            status=201,
        )
    except ValueError as e:
        return JSONResponse(
            ErrorResponse(error=str(e)).model_dump(),
            status=400,
        )


# --- Tools Endpoints ---


@router.get("/tools")
@doc_summary("获取所有工具")
@doc_description("列出当前 MCP 注册表中的全部工具。")
@doc_tag("Tools")
@operation("listTools")
@response(200, ToolResponse, description="工具列表")
async def get_tools(request: Request) -> JSONResponse:
    """获取所有工具"""
    mcp_registry = get_mcp_registry(request)

    tools = mcp_registry.list_all()
    return JSONResponse(
        ToolResponse(
            success=True,
            tools=[t.to_dict() for t in tools],
        ).model_dump()
    )


@router.post("/tools")
@doc_summary("注册新工具")
@doc_description(
    "动态注册 MCP 工具。Body 字段：\n"
    "- `name` (必填): 工具名称\n"
    "- `description`: 描述\n"
    "- `input_schema`: 工具入参 JSON Schema\n"
    "- `handler` 或 `remote_url`: 二选一（本地 handler / 远程 MCP URL）\n"
    "- `enabled`: 默认 true"
)
@doc_tag("Tools")
@operation("registerTool")
@body(
    {
        "application/json": {
            "schema": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string", "example": "web_search"},
                    "description": {"type": "string", "example": "Web 搜索"},
                    "input_schema": {
                        "type": "object",
                        "additionalProperties": True,
                        "example": {"query": "string"},
                    },
                    "handler": {"type": "object", "description": "本地 handler（callable 描述）"},
                    "remote_url": {"type": "string", "format": "uri", "example": "http://mcp.local/tools"},
                    "remote_tool_name": {"type": "string", "example": "search"},
                    "enabled": {"type": "boolean", "example": True},
                },
            },
            "example": {
                "name": "web_search",
                "description": "Web 搜索",
                "input_schema": {"query": "string"},
                "enabled": True,
            },
        }
    }
)
@response(201, ToolResponse, description="注册成功")
@response(400, ErrorResponse, description="参数错误")
async def register_tool(request: Request) -> JSONResponse:
    """注册新工具

    Body: {"name": "tool_name", "description": "...", "input_schema": {...}, ...}
    """
    mcp_registry = get_mcp_registry(request)
    body = request.json

    if not body or "name" not in body:
        return JSONResponse(
            ErrorResponse(error="name is required").model_dump(),
            status=400,
        )

    try:
        tool = mcp_registry.register(
            name=str(body["name"]),
            description=str(body.get("description", "")),
            input_schema=body.get("input_schema"),
            handler=body.get("handler"),
            remote_url=body.get("remote_url"),
            remote_tool_name=body.get("remote_tool_name"),
            enabled=body.get("enabled", True),
        )
        return JSONResponse(
            ToolResponse(
                success=True,
                tool=tool.to_dict(),
            ).model_dump(),
            status=201,
        )
    except ValueError as e:
        return JSONResponse(
            ErrorResponse(error=str(e)).model_dump(),
            status=400,
        )


@router.patch("/tools/<name>/enabled")
@doc_summary("启用或禁用工具")
@doc_description("Body: `{\"enabled\": true/false}`")
@doc_tag("Tools")
@operation("updateToolEnabled")
@body(
    {
        "application/json": {
            "schema": {
                "type": "object",
                "required": ["enabled"],
                "properties": {
                    "enabled": {"type": "boolean", "example": True},
                },
            },
            "example": {"enabled": True},
        }
    }
)
@response(200, ToolResponse, description="更新后的工具信息")
@response(404, ErrorResponse, description="工具不存在")
async def update_tool_enabled(request: Request, name: str) -> JSONResponse:
    """启用或禁用工具

    Body: {"enabled": true/false}
    """
    mcp_registry = get_mcp_registry(request)
    body = request.json

    if body is None or "enabled" not in body:
        return JSONResponse(
            ErrorResponse(error="enabled field is required").model_dump(),
            status=400,
        )

    try:
        mcp_registry.set_enabled(name, bool(body["enabled"]))
        tool = mcp_registry.get_tool(name)
        return JSONResponse(
            ToolResponse(
                success=True,
                tool=tool.to_dict() if tool else None,
            ).model_dump()
        )
    except KeyError as e:
        return JSONResponse(
            ErrorResponse(error=str(e)).model_dump(),
            status=404,
        )


# --- Pool Endpoints (kept for backwards compatibility) ---


@router.post("/pool/register")
@doc_summary("注册新 Agent 实例")
@doc_description(
    "向 Agent Pool 注册一个 OpenCode 兼容后端实例。\n"
    "Body: `{\"name\": \"agent-shanghai\", \"base_url\": \"http://192.168.1.101:4096\"}`"
)
@doc_tag("Pool")
@operation("registerAgent")
@body(
    {
        "application/json": {
            "schema": {
                "type": "object",
                "required": ["name", "base_url"],
                "properties": {
                    "name": {"type": "string", "example": "agent-shanghai"},
                    "base_url": {
                        "type": "string",
                        "format": "uri",
                        "example": "http://192.168.1.101:4096",
                    },
                },
            },
            "example": {
                "name": "agent-shanghai",
                "base_url": "http://192.168.1.101:4096",
            },
        }
    }
)
@response(201, {"success": bool, "name": str, "base_url": str, "status": str}, description="注册成功")
@response(400, ErrorResponse, description="参数错误")
async def register_agent(request: Request) -> JSONResponse:
    """注册新 Agent 实例

    Body: {"name": "agent-shanghai", "base_url": "http://192.168.1.101:4096"}
    """
    bridge = get_bridge(request)
    body = request.json

    if not body or "name" not in body or "base_url" not in body:
        return JSONResponse(
            ErrorResponse(error="name and base_url are required").model_dump(),
            status=400,
        )

    try:
        from openagent.providers.base import AgentConfig
        sdk_type = body.get("sdk_type", "opencode")
        if sdk_type not in ("opencode", "claude_code"):
            return JSONResponse(
                ErrorResponse(
                    error=f"invalid sdk_type '{sdk_type}', must be 'opencode' or 'claude_code'"
                ).model_dump(),
                status=400,
            )
        config = AgentConfig(
            name=body["name"],
            base_url=body["base_url"],
            sdk_type=sdk_type,
            default_model=body.get("default_model"),
        )
        bridge.register(config)
        return JSONResponse(
            {
                "success": True,
                "name": body["name"],
                "base_url": body["base_url"],
                "sdk_type": sdk_type,
                "status": "registered",
            },
            status=201,
        )
    except ValueError as e:
        return JSONResponse(
            ErrorResponse(error=str(e)).model_dump(),
            status=400,
        )
    except Exception as e:
        import traceback
        import structlog
        structlog.get_logger(__name__).error(
            "register_agent_failed",
            name=body.get("name"),
            sdk_type=body.get("sdk_type"),
            error=str(e),
            traceback=traceback.format_exc(),
        )
        return JSONResponse(
            ErrorResponse(error=f"{type(e).__name__}: {e}").model_dump(),
            status=500,
        )


@router.delete("/pool/<name>")
@doc_summary("注销 Agent 实例")
@doc_description("从 Agent Pool 移除一个实例。")
@doc_tag("Pool")
@operation("unregisterAgent")
@response(501, ErrorResponse, description="未实现")
async def unregister_agent(request: Request, name: str) -> JSONResponse:
    """注销 Agent 实例"""
    bridge = get_bridge(request)

    # Bridge doesn't have unregister, but pool endpoints are kept for compatibility
    # In a full implementation, bridge would have unregister_agent method
    return JSONResponse(
        {
            "success": False,
            "name": name,
            "error": "Unregister not implemented via bridge",
        },
        status=501,
    )


@router.get("/pool/stats")
@doc_summary("获取实例池统计信息")
@doc_description("返回当前已注册的 Agent 实例数量和名称列表。")
@doc_tag("Pool")
@operation("poolStats")
@response(200, {"total_agents": int, "agents": list}, description="池统计")
async def pool_stats(request: Request) -> JSONResponse:
    """获取实例池统计信息"""
    bridge = get_bridge(request)

    agents = bridge.list_agents()
    return JSONResponse(
        {
            "total_agents": len(agents),
            "agents": {name: asdict(cfg) for name, cfg in agents.items()},
        }
    )
