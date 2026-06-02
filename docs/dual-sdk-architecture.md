# Dual-SDK Agent Scheduler 架构方案

> 版本: v2.0（集成 PostgreSQL 持久化 + Skill 目录规范 + Claude Code SDK）
> 日期: 2026-06-01
> 状态: 草稿

---

## 1. 背景与目标

当前 `openagent` 仅依赖 `opencode-ai` Python SDK，对外部 opencode serve 实例做任务调度，会话存储在内存中，重启即丢失。本方案扩展为**双 SDK + 统一持久化 + 统一 Skill 体系**：

| 维度 | 目标 |
|------|------|
| 双 SDK 支持 | OpenCode SDK（调度 opencode serve）+ Claude Code SDK（调度 Claude Code，可配自有模型）|
| Skills 系统 | 统一 Skill 注册与调用抽象，支持本地目录加载 + SKILL.md 规范，两种 SDK 共用 |
| MCP | 统一 MCP Tool 抽象，一次定义，各 SDK 可用，支持本地 handler + 远程 MCP 服务器 |
| 流式 SSE 输出 | 统一 SSE 事件格式，两种 SDK 输出协议完全相同 |
| 持久化 | PostgreSQL（主选）+ Memory 双后端，支持多实例共享；会话 + 消息 + Part 分层存储 |
| 对话入口 | 统一 `POST /agent/chat` 接口 |
| 代码编排 | 统一 Scheduler（run / run_parallel / run_chain / run_in_session）|

---

## 2. 整体架构

```
┌────────────────────────────────────────────────────────────────┐
│                     AgentSchedulerHub (Sanic)                   │
│                                                                 │
│  routes.py ──► Scheduler ──► AgentBridge ──► Adapter          │
│                              │               │                   │
│                         SkillRegistry     OpenCodeAdapter         │
│                         MCPRegistry      ClaudeCodeAdapter      │
│                         StorageBackend◄─────────────────────────│
│                              │                                  │
│                     ┌────────┴────────┐                        │
│                     │  PostgresStorage │  MemoryStorage         │
│                     │  (主存储)        │  (开发/降级)          │
│                     └────────┬────────┘                        │
└──────────────────────────────│──────────────────────────────────┘
                               │
        ┌──────────────────────┴──────────────────────┐
        ▼                                              ▼
opencode-ai SDK                              claude-agent-sdk-python
AsyncOpencode                                ClaudeCode SDK
        │                                              │ (可配置自有模型)
        ▼                                              ▼
opencode serve :4096                        Claude Code Server
(self-hosted)                               (可配任意模型endpoint)
```

### 2.1 核心组件职责

| 组件 | 层级 | 职责 |
|------|------|------|
| `routes.py` | API | HTTP 入口，统一路由到 Scheduler |
| `Scheduler` | 编排层 | 任务编排（run / run_parallel / run_chain / run_in_session）|
| `AgentBridge` | 代理层 | 根据 agent sdk_type 选择对应 adapter |
| `OpenCodeAdapter` | 适配器层 | opencode-ai SDK 实现 |
| `ClaudeCodeAdapter` | 适配器层 | claude-agent-sdk-python 实现（可配自有模型）|
| `SkillRegistry` | 能力层 | Skill 目录扫描 + SKILL.md 解析 + prompt 注入 |
| `MCPRegistry` | 工具层 | MCP Tool 注册与调用（本地 handler + 远程 MCP 服务器）|
| `StreamEvent` | 流式层 | 统一 SSE 事件类型定义 |
| `StorageBackend` | 持久化层 | 抽象接口，对下支持 PostgresStorage / MemoryStorage |
| `PostgresStorage` | 持久化层 | PostgreSQL 实现（主选）|
| `MemoryStorage` | 持久化层 | 内存实现（开发/降级）|

---

## 3. SDK 差异与 Claude Code SDK 澄清

### 3.1 三种 SDK 的定位

| SDK | 调用对象 | 模型配置 | 协议 |
|-----|---------|---------|------|
| `opencode-ai` SDK | opencode serve（自托管）| opencode serve 配置 | REST + SSE |
| `claude-agent-sdk-python` | Claude Code Server（可自托管）| **SDK 可配置模型 endpoint**，不强制 Anthropic API | WebSocket/SSE |

> **重要澄清**：本方案中 Claude SDK = `claude-agent-sdk-python`（Claude Code），**不是** Anthropic 官方 SDK。Claude Code Server 可对接自有模型（Ollama / LocalAI / 其他兼容接口），通过 SDK 的 `model` 参数指定模型，不强依赖 Anthropic 云服务。

### 3.2 三种 SDK 的 API 差异

| 维度 | OpenCode SDK | Claude Code SDK | Anthropic SDK（参考 不要）               |
|------|-------------|----------------|------------------------------------|
| 会话创建 | `client.session.create()` | `client.sessions.create()` | `client.messages.create()`         |
| 发消息 | `client.session.chat(session_id, parts, ...)` | `client.sessions.chat(session_id, ...)` | `client.messages.create(...)`      |
| 流式 | `with_streaming_response.chat()` | `client.sessions.stream()` | `messages.stream()`                |
| 工具调用 | 无原生，通过 MCP | 原生 `tools` 参数 | `tools` 参数                         |
| Model 配置 | opencode serve 配置文件 | SDK 构造时或 `model` 参数 | `model` 参数                         |
| Reasoning | `parts[type=="reasoning"]` | `content_blocks[type=="thinking"]` | `content_blocks[type=="thinking"]` |
| Auth | Basic Auth / Bearer | API Key / 自有 Auth | API Key                            |

---

## 4. AgentBridge — 统一 SDK 抽象

### 4.1 AgentProvider 抽象基类

```python
class AgentProvider(ABC):
    """SDK 适配器基类 — 所有 adapter 必须实现此接口"""

    @property
    @abstractmethod
    def provider_type(self) -> SDKType:
        """返回 'opencode' 或 'claude_code'"""
        ...

    @abstractmethod
    async def create_session(
        self,
        agent_name: str,
        model: str | None = None,
        system_prompt: str | None = None,
    ) -> SessionInfo:
        """创建新会话"""
        ...

    @abstractmethod
    async def chat(
        self,
        session_id: str,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        system_prompt: str | None = None,
        tools: list[MCPTool] | None = None,
        timeout: float | None = None,
        stream: bool = False,
    ) -> ChatResult | AsyncIterator[StreamEvent]:
        """发送消息并获取回复（非流式）或流式事件"""
        ...

    @abstractmethod
    async def abort(self, session_id: str) -> bool: ...
    @abstractmethod
    async def delete(self, session_id: str) -> bool: ...
    @abstractmethod
    async def get_messages(self, session_id: str) -> list[ChatMessage]: ...
    @abstractmethod
    async def health_check(self, base_url: str) -> bool: ...
```

### 4.2 AgentConfig

```python
@dataclass
class AgentConfig:
    name: str
    base_url: str
    sdk_type: SDKType                      # "opencode" | "claude_code"
    api_key: str | None = None              # OpenCode Bearer / Claude Code API Key
    username: str | None = None              # OpenCode Basic Auth
    password: str | None = None
    default_model: str | None = None        # 可覆盖 SDK 默认模型
    default_skills: list[str] = field(default_factory=list)
    default_tools: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
```

### 4.3 AgentBridge

```python
class AgentBridge:
    """统一代理层 — 根据 agent sdk_type 选择对应 adapter"""

    def __init__(
        self,
        skill_registry: SkillRegistry,
        mcp_registry: MCPRegistry,
        storage: StorageBackend,
    ):
        self._providers: dict[str, AgentProvider] = {}
        self._agents: dict[str, AgentConfig] = {}
        self._skill_registry = skill_registry
        self._mcp_registry = mcp_registry
        self._storage = storage

    def register(self, config: AgentConfig) -> None:
        if config.sdk_type == "opencode":
            self._providers[config.name] = OpenCodeAdapter(...)
        elif config.sdk_type == "claude_code":
            self._providers[config.name] = ClaudeCodeAdapter(...)
        self._agents[config.name] = config

    def get_provider(self, agent_name: str) -> AgentProvider: ...
    def get_config(self, agent_name: str) -> AgentConfig: ...
    def list_agents(self) -> dict[str, AgentConfig]: ...
```

### 4.4 OpenCodeAdapter

```python
class OpenCodeAdapter(AgentProvider):
    provider_type: SDKType = "opencode"

    def __init__(self, skill_registry, mcp_registry, storage):
        self._skill_registry = skill_registry
        self._mcp_registry = mcp_registry
        self._storage = storage
        self._clients: dict[str, AsyncOpencode] = {}
        self._sessions: dict[str, SessionInfo] = {}

    async def chat(self, session_id, messages, *, model=None, system_prompt=None,
                   tools=None, timeout=None, stream=False):
        # 1. ChatMessage[] → opencode parts 格式
        parts = self._build_parts(messages)
        # 2. 注入 skills 到 system_prompt
        system_prompt = self._skill_registry.inject(system_prompt or "", [])
        # 3. MCP tools → opencode 格式
        opencode_tools = self._mcp_registry.to_opencode_format(tools or [])
        # 4. 调用 SDK
        client = self._get_client(session_id)
        if stream:
            return self._stream_chat(client, session_id, parts, ...)
        else:
            result = await client.session.chat(...)
            await self._storage.save_message(...)
            return result

    async def _stream_chat(self, session_id, messages, *, ...) -> AsyncIterator[StreamEvent]:
        # 实时流式：订阅 opencode 全局事件流，过滤本会话事件。
        # 官方 SDK 文档：https://github.com/anomalyco/opencode-sdk-python#streaming-responses
        #
        # 注意：不要用 client.session.with_streaming_response.chat()——它只是
        # HTTP 响应行级流，会在 opencode serve 端完整生成响应后才刷新，
        # 不是真正的实时输出。
        event_stream = await client.event.list()
        try:
            chat_task = asyncio.create_task(
                client.session.chat(session_id, model_id=..., parts=parts)
            )
            assistant_message_ids: set[str] = set()
            async for event in event_stream:
                mapped = map_opencode_event(event, session_id, assistant_message_ids)
                if mapped is OPENCODE_STREAM_END:
                    break
                if mapped is not None:
                    yield mapped
            await chat_task
        finally:
            await event_stream.close()
```

### 4.5 ClaudeCodeAdapter

```python
class ClaudeCodeAdapter(AgentProvider):
    """claude-agent-sdk-python 适配器

    Claude Code SDK 支持自定义模型 endpoint：
      client = ClaudeCode(base_url="http://localhost:8080", model="my-ollama-model")
    """

    provider_type: SDKType = "claude_code"

    def __init__(self, skill_registry, mcp_registry, storage):
        self._skill_registry = skill_registry
        self._mcp_registry = mcp_registry
        self._storage = storage
        self._clients: dict[str, ClaudeCode] = {}
        self._sessions: dict[str, SessionInfo] = {}

    async def chat(self, session_id, messages, *, model=None, system_prompt=None,
                   tools=None, timeout=None, stream=False):
        # 1. ChatMessage[] → Claude Code messages 格式
        cc_messages = self._build_messages(messages)
        # 2. 注入 skills
        system_prompt = self._skill_registry.inject(system_prompt or "", [])
        # 3. MCP tools → Claude Code tools 格式
        cc_tools = self._mcp_registry.to_claude_code_format(tools or [])
        # 4. 调用 SDK
        client = self._get_client(session_id)
        if stream:
            return self._stream_chat(client, session_id, cc_messages, ...)
        else:
            result = await client.sessions.chat(session_id, ...)
            await self._storage.save_message(...)
            return result

    async def _stream_chat(self, client, session_id, cc_messages, ...) -> AsyncIterator[StreamEvent]:
        async with client.sessions.stream(session_id, ...) as response:
            async for event in response:
                for block in event.content:
                    mapped = map_claude_code_block(block)
                    if mapped:
                        yield mapped
```

---

## 5. Skill 系统

### 5.1 设计思路

Skill = **有确定输入/输出格式的可调用业务能力**，通过本地目录扫描 + SKILL.md 规范定义，支持 prompt 注入到 system_prompt。

### 5.2 Skill 目录规范（集成 skills-development-guide.md）

```
项目根目录 / ~/.config/openagent/skills/
└── <skill-name>/
    └── SKILL.md

# 也兼容 opencode 规范路径（自动识别）
.opencode/skills/<skill-name>/SKILL.md
~/.config/opencode/skills/<skill-name>/SKILL.md
```

### 5.3 SKILL.md 格式规范

```markdown
---
name: <skill-name>                          # 唯一标识
description: 简短描述 + 触发关键词（必填，描述要说明何时触发）
version: "1.0"
---

# Skill 标题

## 触发条件
（可选，描述在什么场景下激活）

## 能力说明
- 核心能力1
- 核心能力2

## 使用规范
（可选，具体编码/操作规范）

## 示例
（可选，对话示例）
```

**注册到 `openagent.json`**:

```json
{
  "skills": {
    "paths": [
      ".opencode/skills",
      "~/.config/openagent/skills",
      ".openagent/skills"
    ],
    "urls": [
      "https://example.com/skills/"
    ]
  }
}
```

### 5.4 Skill 数据类

```python
@dataclass
class Skill:
    name: str                       # 唯一标识，如 "api-dev"
    description: str                 # 供 LLM 理解何时调用
    version: str = "1.0"
    triggers: list[str] = field(default_factory=list)  # 触发关键词
    input_schema: dict | None = None  # JSON Schema，输入验证
    output_schema: dict | None = None  # JSON Schema，输出格式
    prompt_template: str | None = None  # 自定义注入模板
    mcp_tools: list[str] | None = None  # 关联的 MCP Tool
    source: str | None = None           # 来源路径或 URL
```

### 5.5 SkillRegistry

```python
class SkillRegistry:
    """Skill 注册表 — 支持目录扫描 + 配置加载 + 运行时注册"""

    def __init__(self, config: SkillConfig | None = None):
        self._skills: dict[str, Skill] = {}

    def load_from_paths(self, paths: list[Path]) -> int:
        """扫描多个目录，解析所有 SKILL.md，批量注册"""
        loaded = 0
        for base in paths:
            for skill_path in base.rglob("SKILL.md"):
                skill = self._parse_skill_md(skill_path)
                if skill:
                    self.register(skill)
                    loaded += 1
        return loaded

    def _parse_skill_md(self, path: Path) -> Skill | None:
        """解析 SKILL.md，提取 frontmatter + 内容"""
        content = path.read_text(encoding="utf-8")
        # 解析 frontmatter (name, description, triggers)
        # 返回 Skill 对象

    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill

    def register_from_config(self, skills_config: list[dict]) -> None:
        for cfg in skills_config:
            self.register(Skill(**cfg))

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def list_all(self) -> list[Skill]:
        return list(self._skills.values())

    def inject(self, system_prompt: str, skill_names: list[str]) -> str:
        """将指定 skills 注入到 system_prompt"""
        if not skill_prompt:
            return system_prompt
        fragments = [system_prompt]
        for name in skill_names:
            skill = self._skills.get(name)
            if skill:
                if skill.prompt_template:
                    fragment = skill.prompt_template.format(
                        name=skill.name,
                        description=skill.description,
                        input=json.dumps(skill.input_schema or {}),
                        output=json.dumps(skill.output_schema or {}),
                    )
                else:
                    fragment = self._default_template.format(
                        name=skill.name,
                        description=skill.description,
                        triggers=", ".join(skill.triggers),
                    )
                fragments.append(fragment)
        return "\n\n".join(fragments)

    def match_by_trigger(self, query: str) -> list[Skill]:
        """根据触发关键词匹配相关 skills"""
        query_lower = query.lower()
        return [
            s for s in self._skills.values()
            if any(t in query_lower for t in s.triggers)
        ]

    # 默认注入模板
    DEFAULT_TEMPLATE = """
## Skill: {name}
{description}
(triggers: {triggers})
Use this skill when user asks about tasks matching its description.
"""
```

### 5.6 场景化 Skill 加载

```python
# 按场景批量激活 skills
SCENE_SKILLS = {
    "api": ["api-dev", "database-migration", "auth-implementation"],
    "frontend": ["react-dev", "css-expert", "playwright-testing"],
    "devops": ["docker-compose", "kubernetes-deploy", "ci-cd"],
}

def inject_scene(skill_registry: SkillRegistry, scene: str) -> list[Skill]:
    skill_names = SCENE_SKILLS.get(scene, [])
    return [skill_registry.get(name) for name in skill_names if skill_registry.get(name)]
```

---

## 6. MCP 系统

### 6.1 设计思路

MCP (Model Context Protocol) = **工具定义 + 调用协议**。支持两种工具来源：
- **本地 Handler**：Python 函数直接在进程中执行
- **远程 MCP 服务器**：通过 HTTP 调用外部 MCP 服务（如 playwright、postgres、github 等）

### 6.2 MCPTool 定义

```python
@dataclass
class MCPTool:
    name: str                              # 工具名
    description: str                       # 供 LLM 理解
    input_schema: dict                    # JSON Schema
    # 本地工具
    handler: Callable[..., Awaitable[dict]] | None = None
    # 远程 MCP 服务器
    remote_url: str | None = None
    remote_tool_name: str | None = None
    # 启用状态
    enabled: bool = True
```

### 6.3 MCPRegistry

```python
class MCPRegistry:
    """MCP Tool 注册表"""

    def __init__(self):
        self._tools: dict[str, MCPTool] = {}

    def register(self, tool: MCPTool) -> None:
        self._tools[tool.name] = tool

    def register_handler(
        self,
        name: str,
        handler: Callable,
        description: str,
        input_schema: dict,
    ) -> None:
        self.register(MCPTool(
            name=name,
            description=description,
            input_schema=input_schema,
            handler=handler,
        ))

    async def call_tool(self, tool_name: str, tool_input: dict) -> dict:
        tool = self._tools.get(tool_name)
        if not tool:
            raise ValueError(f"MCP tool '{tool_name}' not found")
        if not tool.enabled:
            raise ValueError(f"MCP tool '{tool_name}' is disabled")
        if tool.remote_url:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    tool.remote_url,
                    json={"name": tool.remote_tool_name or tool.name, "input": tool_input},
                )
                return resp.json()
        if tool.handler:
            return await tool.handler(tool_input)
        raise ValueError(f"MCP tool '{tool_name}' has no handler or remote_url")

    def list_all(self, enabled_only: bool = True) -> list[MCPTool]:
        tools = self._tools.values()
        if enabled_only:
            tools = [t for t in tools if t.enabled]
        return list(tools)

    def set_enabled(self, tool_name: str, enabled: bool) -> None:
        if tool_name in self._tools:
            self._tools[tool_name].enabled = enabled

    def to_opencode_format(self, tool_names: list[str]) -> list[dict]:
        return [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in self._tools.values()
            if t.name in tool_names and t.enabled
        ]

    def to_anthropic_format(self, tool_names: list[str]) -> list[dict]:
        # 同上，转为 Anthropic tools 格式
        ...

    def to_claude_code_format(self, tool_names: list[str]) -> list[dict]:
        # claude-agent-sdk-python 的 tools 格式
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in self._tools.values()
            if t.name in tool_names and t.enabled
        ]

    def from_config(self, config: list[dict]) -> None:
        for cfg in config:
            self.register(MCPTool(**cfg))
```

### 6.4 场景化 MCP 配置（集成 skills-development-guide.md）

```python
# 场景化 MCP 服务器配置
SCENE_MCP = {
    "frontend": ["playwright"],
    "backend": ["postgresql", "redis"],
    "devops": ["docker", "kubernetes", "aws"],
    "api": ["swagger", "postman"],
}

def switch_mcp_scene(mcp_registry: MCPRegistry, scene: str) -> None:
    """切换 MCP 场景 — 全局启用/禁用"""
    for tool_name, tool in mcp_registry._tools.items():
        tool.enabled = tool_name in SCENE_MCP.get(scene, [])

def enable_mcp(mcp_registry: MCPRegistry, tool_name: str) -> None:
    mcp_registry.set_enabled(tool_name, True)

def disable_mcp(mcp_registry: MCPRegistry, tool_name: str) -> None:
    mcp_registry.set_enabled(tool_name, False)
```

### 6.5 MCP 与 Skill 的关系

```
Skill (业务能力定义)
  └─ 定义: name, description, triggers, input_schema, output_schema
  └─ 可选关联 → MCP Tool (工具实现)
                        ├─ handler (本地 Python 函数)
                        └─ remote_url (远程 MCP 服务器)

场景化加载:
  Skill + MCP Tool 联动 → 通过 scene 配置批量激活
```

---

## 7. 统一 SSE 流式输出格式

### 7.1 统一事件类型

```
event: session
data: {"session_id": "xxx", "agent_name": "yyy"}

event: text
data: {"content": "你好"}

event: reasoning
data: {"content": "用户想订机票..."}

event: tool_use
data: {"tool": "flight_search", "input": {...}, "tool_call_id": "tc_xxx"}

event: tool_result
data: {"tool_call_id": "tc_xxx", "content": "..."}

event: done
data: {"stop_reason": "end_turn"}

event: error
data: {"message": "..."}
```

### 7.2 StreamEvent 数据类

```python
@dataclass
class StreamEvent:
    type: Literal["session", "text", "reasoning", "tool_use", "tool_result", "done", "error"]
    data: dict

    def to_sse(self) -> str:
        return f"event: {self.type}\ndata: {json.dumps(self.data)}\n\n"

    @classmethod
    def session(cls, session_id: str, agent_name: str) -> "StreamEvent": ...
    @classmethod
    def text(cls, content: str) -> "StreamEvent": ...
    @classmethod
    def reasoning(cls, content: str) -> "StreamEvent": ...
    @classmethod
    def tool_use(cls, tool: str, tool_input: dict, tool_call_id: str) -> "StreamEvent": ...
    @classmethod
    def tool_result(cls, tool_call_id: str, content: str) -> "StreamEvent": ...
    @classmethod
    def done(cls, stop_reason: str) -> "StreamEvent": ...
    @classmethod
    def error(cls, message: str) -> "StreamEvent": ...
```

### 7.3 SDK → StreamEvent 映射

| SDK | 原始事件 | StreamEvent |
|-----|---------|-------------|
| OpenCode | `parts[*].type=="text"` | `text` |
| OpenCode | `parts[*].type=="reasoning"` | `reasoning` |
| OpenCode | `parts[*].type=="tool_use"` | `tool_use` |
| OpenCode | `parts[*].type=="tool_result"` | `tool_result` |
| Claude Code | `content_block.type=="text"` | `text` |
| Claude Code | `content_block.type=="thinking"` | `reasoning` |
| Claude Code | `content_block.type=="tool_use"` | `tool_use` |
| Claude Code | `content_block.type=="tool_result"` | `tool_result` |

---

## 8. 持久化存储（集成 postgres-persistence-plan.md）

### 8.1 存储后端接口

```python
class StorageBackend(ABC):
    """存储后端抽象接口 — 支持多后端实现"""

    @abstractmethod
    async def connect(self) -> None: ...
    @abstractmethod
    async def close(self) -> None: ...
    @abstractmethod
    async def init_schema(self) -> None: ...

    # Session
    @abstractmethod
    async def create_session(self, session: Session) -> Session: ...
    @abstractmethod
    async def get_session(self, session_id: str) -> Session | None: ...
    @abstractmethod
    async def update_session(self, session: Session) -> Session: ...
    @abstractmethod
    async def list_sessions(self, limit: int = 50, offset: int = 0,
                            agent_name: str | None = None) -> list[Session]: ...
    @abstractmethod
    async def delete_session(self, session_id: str) -> None: ...

    # Message
    @abstractmethod
    async def create_message(self, message: Message) -> Message: ...
    @abstractmethod
    async def get_messages(self, session_id: str) -> list[Message]: ...

    # Part
    @abstractmethod
    async def create_part(self, message_id: str, part_index: int, part: Part) -> Part: ...
    @abstractmethod
    async def get_parts(self, message_id: str) -> list[Part]: ...
```

### 8.2 分层数据模型

```python
@dataclass
class Session:
    id: str
    title: str = "New Session"
    model: str | None = None
    agent_name: str | None = None
    parent_id: str | None = None        # 父会话 ID（支持分支）
    version: str | None = None
    metadata: dict | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Message:
    id: str
    session_id: str
    role: Literal["user", "assistant", "system", "tool"]
    model_id: str | None = None
    cost: Decimal | None = None
    tokens: int | None = None
    error: str | None = None
    summary: bool = False
    metadata: dict | None = None
    created_at: datetime | None = None


@dataclass
class Part:
    id: str
    message_id: str
    part_type: str                      # "text" | "file" | "tool" | "reasoning" | "step_start" | "step_finish"
    content: dict                        # JSON — 类型不同 content 结构不同
    part_index: int
```

**Part Type 映射**：

| part_type | content 结构 |
|-----------|-------------|
| `text` | `{"text": "..."}` |
| `file` | `{"path": "...", "content": "..."}` |
| `tool` | `{"tool_call_id": "...", "tool_name": "...", "input": {...}}` |
| `reasoning` | `{"reasoning": "..."}` |
| `step_start` | `{"step": 1}` |
| `step_finish` | `{"step": 1, "duration_ms": 123}` |

### 8.3 PostgresStorage 实现

```python
class PostgresStorage(StorageBackend):
    """PostgreSQL 存储后端 — 主选生产存储"""

    DSN: str

    def __init__(self, dsn: str, pool_min_size: int = 5, pool_max_size: int = 20):
        self.pool: asyncpg.Pool | None = None
        self.DSN = dsn
        self._pool_min = pool_min_size
        self._pool_max = pool_max_size

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(
            self.DSN,
            min_size=self._pool_min,
            max_size=self._pool_max,
        )

    async def init_schema(self) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id VARCHAR(64) PRIMARY KEY,
                    title VARCHAR(255) NOT NULL DEFAULT 'New Session',
                    model VARCHAR(128),
                    agent_name VARCHAR(128),
                    parent_id VARCHAR(64),
                    version VARCHAR(32),
                    metadata JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id VARCHAR(64) PRIMARY KEY,
                    session_id VARCHAR(64) NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
                    model_id VARCHAR(128),
                    cost DECIMAL(12, 4) DEFAULT 0,
                    tokens INT DEFAULT 0,
                    error TEXT,
                    summary BOOLEAN DEFAULT FALSE,
                    metadata JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS message_parts (
                    id VARCHAR(64) PRIMARY KEY,
                    message_id VARCHAR(64) NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
                    part_type VARCHAR(32) NOT NULL,
                    content JSONB NOT NULL,
                    part_index INT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions(updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_sessions_agent_name ON sessions(agent_name);
                CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
                CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
                CREATE INDEX IF NOT EXISTS idx_message_parts_message_id ON message_parts(message_id);
            """)

    async def create_session(self, session: Session) -> Session:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO sessions(id, title, model, agent_name, parent_id, version, metadata)
                   VALUES($1, $2, $3, $4, $5, $6, $7)""",
                session.id, session.title, session.model, session.agent_name,
                session.parent_id, session.version, json.dumps(session.metadata or {}),
            )
        return session

    async def get_session(self, session_id: str) -> Session | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM sessions WHERE id = $1", session_id)
        return self._row_to_session(row) if row else None

    async def create_message(self, message: Message) -> Message:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO messages(id, session_id, role, model_id, cost, tokens, error, summary, metadata)
                   VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                message.id, message.session_id, message.role,
                message.model_id, message.cost or 0, message.tokens or 0,
                message.error, message.summary, json.dumps(message.metadata or {}),
            )
        return message

    async def create_part(self, message_id: str, part_index: int, part: Part) -> Part:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO message_parts(id, message_id, part_type, content, part_index)
                   VALUES($1, $2, $3, $4, $5)""",
                part.id, message_id, part.part_type, json.dumps(part.content), part_index,
            )
        return part
```

### 8.4 MemoryStorage 实现（开发/降级）

```python
class MemoryStorage(StorageBackend):
    """内存存储后端 — 开发/降级用"""

    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._messages: dict[str, list[Message]] = {}
        self._parts: dict[str, list[Part]] = {}

    async def connect(self) -> None: pass
    async def close(self) -> None: pass
    async def init_schema(self) -> None: pass
    # ... 全部内存实现，与 PostgresStorage 接口一致
```

### 8.5 分层存储架构

```
应用层
  └─ SessionStore / AgentStore  (调用 StorageBackend 接口)
           │
           ├─► MemoryStorage   (开发 / 快速原型)
           └─► PostgresStorage (生产 / 多实例共享)
                      │
                      └─► asyncpg 连接池
                                │
                                └─► PostgreSQL
```

### 8.6 配置

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENT_SCHEDULER_", env_file=".env")

    storage_backend: str = Field(
        default="postgres",
        description="存储后端: postgres | memory"
    )
    postgres_dsn: str = Field(
        default="postgresql://localhost:5432/openagent",
        description="PostgreSQL 连接字符串"
    )
    postgres_pool_min_size: int = Field(default=5, ge=1)
    postgres_pool_max_size: int = Field(default=20, ge=1)
```

### 8.7 启动恢复流程

```
应用启动 (app.py after_server_start)
  │
  1. Settings 加载 → 确定 storage_backend
  2. StorageBackendFactory.create(settings) → PostgresStorage 或 MemoryStorage
  3. storage.connect() + storage.init_schema()
  4. AgentStore.load_agents()     → 恢复 agent 注册
  5. SkillRegistry.load_from_paths() → 扫描 SKILL.md
  6. AgentStore.load_skills()     → 补充配置中的 skill
  7. AgentStore.load_mcp_tools()  → 恢复 MCP tool
  8. AgentBridge.register(agent_config) → 创建对应 adapter
```

---

## 9. 对话入口统一

### 9.1 统一请求模型

```python
class ChatRequest(BaseModel):
    message:       str
    session_id:    str | None = None
    agent_name:    str | None = None    # 不指定则自动分配
    model:         str | None = None    # 不指定用 agent 默认
    system_prompt: str | None = None
    skills:        list[str] | None = None   # 激活的 skills
    tools:         list[str] | None = None   # 激活的 MCP tools
    stream:        bool = False
    timeout:       float | None = None
```

### 9.2 统一 REST 路由

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/agent/chat` | 统一聊天入口（非流式）|
| `POST` | `/agent/chat/stream` | 统一聊天入口（SSE 流式）|
| `POST` | `/agent/session` | 创建会话 |
| `GET` | `/agent/session/<id>` | 获取会话信息 |
| `GET` | `/agent/session/<id>/messages` | 获取会话历史 |
| `DELETE` | `/agent/session/<id>` | 删除会话 |
| `POST` | `/agent/session/<id>/abort` | 中止会话 |
| `POST` | `/agent/pool/register` | 注册 Agent（含 sdk_type）|
| `DELETE` | `/agent/pool/<name>` | 注销 Agent |
| `GET` | `/agent/pool/stats` | 实例池统计 |
| `GET` | `/agent/skills` | 列出所有 Skill |
| `POST` | `/agent/skills` | 注册 Skill |
| `GET` | `/agent/tools` | 列出所有 MCP Tool |
| `POST` | `/agent/tools` | 注册 MCP Tool |
| `PATCH` | `/agent/tools/<name>/enabled` | 启用/禁用 MCP Tool |

### 9.3 chat 路由内部流程

```
POST /agent/chat (或 /agent/chat/stream)

1. 解析 ChatRequest
2. AgentBridge.get_provider(agent_name)  → 拿到 adapter
3. AgentConfig 合并 → 最终 model / skills / tools
4. SkillRegistry.inject(system_prompt, skills)  → 注入 skills
5. MCPRegistry.to_xxx_format(tools)     → 转为目标 SDK tools 格式
6. adapter.create_session()              → 创建会话，写入 storage
7. adapter.chat(stream=stream)            → 执行（流式：实时 SSE；非流式：完成后统一写入）
8. storage.save_message() + storage.create_part()  → 持久化
9. 返回 ChatResponse 或 SSE StreamEvent
```

---

## 10. Scheduler 代码编排

接口不变，内部通过 AgentBridge 路由。

### 10.1 接口

```python
class Scheduler:
    async def run(
        self,
        prompt: str,
        agent_name: str | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        skills: list[str] | None = None,
        tools: list[str] | None = None,
        timeout: float | None = None,
    ) -> TaskResult: ...

    async def run_parallel(
        self,
        prompts: list[str],
        agent_names: list[str] | None = None,
        skills: list[str] | None = None,
        tools: list[str] | None = None,
        timeout: float | None = None,
    ) -> list[TaskResult]: ...

    async def run_chain(
        self,
        prompts: list[str],
        agent_name: str | None = None,
        skills: list[str] | None = None,
        tools: list[str] | None = None,
        timeout: float | None = None,
    ) -> TaskResult: ...

    async def run_in_session(
        self,
        session_id: str,
        prompt: str,
        skills: list[str] | None = None,
        tools: list[str] | None = None,
        timeout: float | None = None,
    ) -> TaskResult: ...
```

### 10.2 run() 内部实现

```python
async def run(self, prompt, agent_name, ..., skills=None, tools=None, timeout=None):
    # 1. 分配 agent
    instance = await self._pool.acquire_idle_instance()
    agent_config = self._bridge.get_config(instance.name)

    # 2. 合并 skills: agent.default_skills ∪ 请求中的 skills
    final_skills = list(set(agent_config.default_skills) | set(skills or []))

    # 3. 合并 tools: agent.default_tools ∪ 请求中的 tools
    final_tools = list(set(agent_config.default_tools) | set(tools or []))

    # 4. 注入 skills
    system_prompt = self._skill_registry.inject(system_prompt or "", final_skills)

    # 5. 获取 MCP tools
    mcp_tools = self._mcp_registry.get_tools(final_tools)

    # 6. 通过 bridge 路由到正确 adapter
    result = await self._bridge.chat(
        agent_name=instance.name,
        session_id=session_info.session_id,
        messages=[...],
        system_prompt=system_prompt,
        tools=mcp_tools,
        stream=False,
        timeout=timeout,
    )

    # 7. 写入存储（adapter 内部已完成）
    # 8. 释放 agent
    self._pool.release(instance.name)
```

---

## 11. 关键数据类定义

```python
@dataclass
class ChatMessage:
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    tool_call_id: str | None = None
    tool_name: str | None = None
    metadata: dict | None = None

@dataclass
class ChatResult:
    success: bool
    message: ChatMessage
    stop_reason: str | None = None
    session_id: str
    agent_name: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    duration: float | None = None
    error: str | None = None

@dataclass
class ToolCall:
    id: str
    name: str
    input: dict

@dataclass
class SessionInfo:
    session_id: str
    agent_name: str
    agent_base_url: str
    model: str | None = None
    created_at: float | None = None

SDKType = Literal["opencode", "claude_code"]
```

---

## 12. 文件变更清单

### 新增文件

```
src/openagent/
├── streaming.py                          # StreamEvent + SSE helpers + SDK mappers
├── providers/
│   ├── __init__.py
│   ├── base.py                          # AgentProvider ABC + 数据类
│   ├── opencode_adapter.py              # OpenCodeAdapter
│   ├── claude_code_adapter.py           # ClaudeCodeAdapter (claude-agent-sdk-python)
│   └── agent_bridge.py                  # AgentBridge
├── skills/
│   ├── __init__.py
│   └── registry.py                      # SkillRegistry + Skill + 目录扫描
├── mcp/
│   ├── __init__.py
│   └── registry.py                      # MCPRegistry + MCPTool + 场景化 MCP
└── store/
    ├── __init__.py
    ├── base.py                          # StorageBackend ABC
    ├── postgres.py                      # PostgresStorage (asyncpg)
    ├── memory.py                        # MemoryStorage
    └── factory.py                       # StorageBackendFactory
```

### 修改文件

```
src/openagent/
├── core/
│   ├── agent_pool.py         # 移除 SessionManager，改用 AgentBridge
│   ├── session.py            # 删除，内容并入 providers/
│   └── scheduler.py          # 支持 skills/tools，通过 AgentBridge 调用
├── api/
│   ├── routes.py              # 支持 skills/tools/stream，新增 skills/tools/tool 路由
│   └── app.py                # 启动时加载持久化，Skill 目录扫描
├── config/
│   └── settings.py           # 新增: storage_backend, postgres_dsn, skill_paths
└── main.py                    # 无变化
tests/
└── conftest.py                # 新增 storage/provider fixtures
```

---

## 13. 实现顺序

```
Phase 1: 存储基础设施（1-2天）
  1. store/base.py — StorageBackend ABC
  2. store/postgres.py — PostgresStorage
  3. store/memory.py — MemoryStorage
  4. store/factory.py — StorageBackendFactory
  5. 更新 settings.py — 新增存储相关配置
  6. 更新 app.py — 启动时初始化存储

Phase 2: Provider 基础设施（1-2天）
  7. streaming.py — StreamEvent + SSE helpers + SDK mappers
  8. providers/base.py — AgentProvider ABC + 数据类
  9. providers/opencode_adapter.py — 从 session.py 提取改造
  10. providers/claude_code_adapter.py — claude-agent-sdk-python 适配器
  11. providers/agent_bridge.py — 统一代理层

Phase 3: Skills + MCP（1-2天）
  12. skills/registry.py — SkillRegistry + SKILL.md 解析 + 目录扫描
  13. mcp/registry.py — MCPRegistry + 场景化 MCP
  14. routes.py — 支持 skills/tools 参数，新增 skills/tools 路由
  15. scheduler.py — 注入 skills 到 system_prompt

Phase 4: 整合测试（1天）
  16. 更新 conftest.py fixtures
  17. 端到端测试两种 SDK 模式
  18. SSE 流式输出验证
  19. Skill/MCP 集成测试
  20. PostgreSQL 持久化验证
```

---

## 14. 验证方案

```bash
# 1. OpenCode SDK 模式
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你好", "agent_name": "opencode-default"}'

# 2. Claude Code SDK 模式（可配自有模型）
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你好", "agent_name": "claude-code-default"}'

# 3. SSE 流式（两种 agent 均输出相同格式）
curl -X POST http://localhost:8000/agent/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "写一个快排", "stream": true}'

# 4. Skill 激活
curl -X POST http://localhost:8000/agent/chat \
  -d '{"message": "帮我查北京到上海的机票", "skills": ["flight_search"]}'

# 5. MCP Tool 调用
curl -X POST http://localhost:8000/agent/chat \
  -d '{"message": "查一下明天机票", "tools": ["flight_search"]}'

# 6. Skill 目录扫描验证
curl http://localhost:8000/agent/skills

# 7. 重启后验证 PostgreSQL 持久化
# 重启服务后 GET /agent/session/<id>/messages 应恢复历史数据
```
