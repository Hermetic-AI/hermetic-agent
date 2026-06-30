# hermetic_agent API 接口文档

> 最后更新：2026-06-03 ｜ 基线版本：`agent-scheduler-hub` 0.1.0
>
> 服务地址：默认 `http://localhost:28000`（在 `.env` 里改 `AGENT_SCHEDULER_HOST` / `AGENT_SCHEDULER_PORT`）
>
> 认证：当前版本**无认证**（私有化部署）
>
> 数据格式：所有请求/响应均为 `application/json`，流式端点为 `text/event-stream` (SSE)

---

## 0. 目录

| 端点 | 用途 |
|------|------|
| `GET /health` | 进程存活探针 |
| `GET /ready` | 依赖就绪探针（K8s readiness） |
| `POST /agent/chat` | 同步对话 |
| `POST /agent/chat/stream` | SSE 流式对话 |
| `POST /agent/session` | 创建新会话 |
| `GET /agent/session/<id>` | 查询会话元信息 |
| `GET /agent/session/<id>/messages` | 查询会话历史消息 |
| `DELETE /agent/session/<id>` | 删除会话 |
| `POST /agent/session/<id>/abort` | 中止运行中的会话 |
| `GET /agent/skills` | 列出所有已注册技能 |
| `POST /agent/skills` | 动态注册技能 |
| `GET /agent/tools` | 列出所有 MCP 工具 |
| `POST /agent/tools` | 动态注册 MCP 工具 |
| `PATCH /agent/tools/<name>/enabled` | 启用/禁用工具 |
| `POST /agent/pool/register` | 注册 Agent 实例 |
| `DELETE /agent/pool/<name>` | 注销 Agent 实例（501，未实现）|
| `GET /agent/pool/stats` | 池统计信息 |
| `GET /agent/scenarios` | 列出所有 routing scenario |
| `GET /agent/scenarios/<name>` | 查询单个 scenario |
| `POST /agent/scenarios` | 注册/覆盖一个 scenario |
| `DELETE /agent/scenarios/<name>` | 注销一个 scenario |
| `POST /agent/scenarios/reload` | 重载所有 scenario |
| `GET /agent/scenarios/<name>/validate` | 校验 scenario 语法（不注册）|
| `POST /agent/scenarios/<name>/chat` | 向指定 scenario 发起 chat（stub）|
| `POST /agent/scenarios/<name>/chat/stream` | 向指定 scenario 发起流式 chat（stub）|
| `GET /agent/scenarios/routing-log` | 导出 routing 历史（stub）|

---

## 1. 系统探针

### `GET /health`

进程存活探针。Liveness probe 用这个。

```bash
curl -s http://localhost:28000/health
```

**响应 200：**
```json
{"status": "ok"}
```

### `GET /ready`

依赖就绪探针。Readiness probe 用这个。

只有当 **storage 已连接** + **至少一个 Agent 已注册** + **至少一个 Skill 已加载** + **至少一个 MCP 工具已注册** 时才返回 200。

```bash
curl -s http://localhost:28000/ready
```

**响应 200（全部就绪）：**
```json
{
  "status": "ready",
  "checks": {
    "storage": {"ok": true, "detail": "PostgresSessionRepository connected"},
    "bridge": {"ok": true, "detail": "1 agent(s) registered: ['opencode-core']"},
    "skill_registry": {"ok": true, "detail": "3 skill(s) loaded"},
    "mcp_registry": {"ok": true, "detail": "2 tool(s) registered"}
  },
  "missing": [],
  "agents": ["opencode-core"],
  "skills_count": 3,
  "tools_count": 2
}
```

**响应 503（部分未就绪）：**
```json
{
  "status": "not_ready",
  "checks": {
    "bridge": {"ok": false, "detail": "no agents registered (set AGENT_SCHEDULER_AUTO_REGISTER_DEFAULTS=true or POST /agent/pool/register)"},
    "mcp_registry": {"ok": false, "detail": "0 tools registered (check AGENT_SCHEDULER_MCP_TOOLS_CONFIG)"}
  },
  "missing": ["bridge", "mcp_registry"],
  "reason": "missing components: bridge (no agents registered ...); mcp_registry (0 tools registered ...)"
}
```

---

## 2. 对话

### `POST /agent/chat`

发送消息并同步等待 Agent 完整回复。

**Request Body（`ChatRequest`）：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `message` | string | ✅ | 用户消息（≥1 字符） |
| `session_id` | string |   | 不传则创建新会话；传则继续已有会话 |
| `agent_name` | string |   | 指定 Agent 实例；不传则取 `bridge.list_agents()` 第一个 |
| `model` | string |   | 覆盖默认模型 |
| `system_prompt` | string |   | 系统提示词 |
| `timeout` | float |   | chat 超时秒数 |
| `skills` | string[] |   | 注入的技能名列表 |
| `tools` | string[] |   | 启用的 MCP 工具名列表 |

**示例：新建会话问一句**
```bash
curl -s -X POST http://localhost:28000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "帮我查一下从北京到上海的航班"
  }'
```

**示例：续接已有会话**
```bash
curl -s -X POST http://localhost:28000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "a1b2c3d4-1234-5678-9abc-def012345678",
    "message": "那成都呢？"
  }'
```

**示例：指定 Agent、模型、技能**
```bash
curl -s -X POST http://localhost:28000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "你是一个旅行助手",
    "agent_name": "opencode-core",
    "model": "claude-sonnet-4-5",
    "system_prompt": "你是一个旅行助手",
    "skills": ["weather", "calendar"],
    "tools": ["web_search"],
    "timeout": 60.0
  }'
```

**响应 200（`ChatResponse`）：**
```json
{
  "success": true,
  "session_id": "a1b2c3d4-1234-5678-9abc-def012345678",
  "agent_name": "opencode-core",
  "result": {
    "message": {
      "role": "assistant",
      "content": "已为你查询 2026-06-03 北京→上海航班，共找到 12 个班次。"
    },
    "tool_calls": [],
    "stop_reason": "end_turn"
  },
  "error": null,
  "duration": 1.234
}
```

**响应 400（参数错误）：**
```json
{"success": false, "error": "Invalid request body: ..."}
```

**响应 404（session 不存在）：**
```json
{"success": false, "error": "Session 'xxx' not found"}
```

---

### `POST /agent/chat/stream`

SSE 流式回复。每个事件以 `data: <json>\n\n` 形式推。

**Request Body：** 同 `/agent/chat`。

**示例：流式接收**
```bash
curl -N -s -X POST http://localhost:28000/agent/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "message": "讲个笑话",
    "session_id": "a1b2c3d4-1234-5678-9abc-def012345678"
  }'
```

**SSE 事件类型 (`type` 字段)：**

| type | data 字段 | 说明 |
|------|-----------|------|
| `session` | `session_id, agent_name` | 流开始，第一条 |
| `text` | `content` | 模型流式文本片段 |
| `reasoning` | `content` | 思考/推理片段（Claude 才有）|
| `tool_use` | `tool_name, input, tool_call_id` | 模型调用工具 |
| `tool_result` | `tool_name, output, tool_call_id` | 工具返回结果 |
| `done` | `stop_reason` | 流结束，最后一条 |
| `error` | `message, code` | 流中错误 |

**示例：服务端推的事件**
```
data: {"type":"session","data":{"session_id":"abc","agent_name":"opencode-core"}}

data: {"type":"text","data":{"content":"已"}}

data: {"type":"text","data":{"content":"为你查询"}}

data: {"type":"text","data":{"content":" 12 个班次。"}}

data: {"type":"done","data":{"stop_reason":"end_turn"}}
```

---

## 3. 会话管理

### `POST /agent/session`

创建新会话（或恢复指定 ID 的会话）。

**Request Body（`CreateSessionRequest`）：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `agent_name` | string | ✅ | 要绑定的 Agent 实例名 |
| `model` | string |   | 覆盖默认模型 |
| `system_prompt` | string |   | 会话级系统提示词 |
| `session_id` | string |   | 恢复已有会话的 ID（resumption） |

**示例：创建新会话**
```bash
curl -s -X POST http://localhost:28000/agent/session \
  -H "Content-Type: application/json" \
  -d '{
    "agent_name": "opencode-core",
    "model": "claude-sonnet-4-5"
  }'
```

**响应 201：**
```json
{
  "success": true,
  "session_id": "a1b2c3d4-1234-5678-9abc-def012345678",
  "agent_name": "opencode-core",
  "agent_base_url": "http://localhost:4096",
  "model": "claude-sonnet-4-5"
}
```

**示例：恢复指定 session_id**
```bash
curl -s -X POST http://localhost:28000/agent/session \
  -H "Content-Type: application/json" \
  -d '{
    "agent_name": "opencode-core",
    "session_id": "my-existing-session"
  }'
```

---

### `GET /agent/session/<session_id>`

查询会话元信息。

```bash
curl -s http://localhost:28000/agent/session/a1b2c3d4-1234-5678-9abc-def012345678
```

**响应 200：**
```json
{
  "success": true,
  "session_id": "a1b2c3d4-1234-5678-9abc-def012345678",
  "agent_name": "opencode-core",
  "agent_base_url": "http://localhost:4096",
  "model": "claude-sonnet-4-5"
}
```

**响应 404：**
```json
{"success": false, "error": "Session 'xxx' not found"}
```

---

### `GET /agent/session/<session_id>/messages`

查询会话历史消息。

```bash
curl -s http://localhost:28000/agent/session/a1b2c3d4-1234-5678-9abc-def012345678/messages
```

**响应 200：**
```json
{
  "success": true,
  "session_id": "a1b2c3d4-1234-5678-9abc-def012345678",
  "messages": [
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "你好！有什么可以帮您？"},
    {"role": "user", "content": "查一下天气"},
    {"role": "assistant", "content": "北京今天晴，25°C。"}
  ]
}
```

---

### `DELETE /agent/session/<session_id>`

删除会话及其所有历史消息。

```bash
curl -s -X DELETE http://localhost:28000/agent/session/a1b2c3d4-1234-5678-9abc-def012345678
```

**响应 200：**
```json
{"success": true, "session_id": "a1b2c3d4-1234-5678-9abc-def012345678"}
```

---

### `POST /agent/session/<session_id>/abort`

中止正在运行的 Agent 调用（打断当前 turn）。

```bash
curl -s -X POST http://localhost:28000/agent/session/a1b2c3d4-1234-5678-9abc-def012345678/abort
```

**响应 200：**
```json
{"success": true, "session_id": "a1b2c3d4-1234-5678-9abc-def012345678"}
```

---

## 4. 技能管理

### `GET /agent/skills`

列出所有已注册技能。

```bash
curl -s http://localhost:28000/agent/skills
```

**响应 200：**
```json
{
  "success": true,
  "skills": [
    {
      "name": "weather",
      "description": "查询天气",
      "version": "1.0.0",
      "triggers": ["weather", "天气"],
      "input_schema": {"city": "string"},
      "output_schema": {"temp": "number", "desc": "string"},
      "mcp_tools": [],
      "source": "/path/to/SKILL.md"
    }
  ]
}
```

### `POST /agent/skills`

动态注册一个新技能。

**Request Body：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | 技能唯一名称 |
| `description` | string |   | 描述 |
| `version` | string |   | 版本号（默认 `1.0.0`） |
| `triggers` | string[] |   | 触发关键词 |
| `input_schema` | object |   | 入参 JSON Schema |
| `output_schema` | object |   | 出参 JSON Schema |
| `prompt_template` | string |   | 提示词模板（注入到 system_prompt）|
| `mcp_tools` | string[] |   | 关联 MCP 工具名 |
| `source` | string |   | 来源标识（默认 `api`）|

**示例：注册天气技能**
```bash
curl -s -X POST http://localhost:28000/agent/skills \
  -H "Content-Type: application/json" \
  -d '{
    "name": "weather",
    "description": "查询天气",
    "version": "1.0.0",
    "triggers": ["weather", "天气"],
    "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}},
    "output_schema": {"type": "object", "properties": {"temp": {"type": "number"}, "desc": {"type": "string"}}},
    "prompt_template": "你是一个天气查询助手，根据用户提供的城市查询实时天气。",
    "mcp_tools": []
  }'
```

**响应 201：**
```json
{
  "success": true,
  "skill": {
    "name": "weather",
    "description": "查询天气",
    "version": "1.0.0",
    "triggers": ["weather", "天气"],
    "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}},
    "output_schema": {"type": "object", "properties": {"temp": {"type": "number"}, "desc": {"type": "string"}}},
    "mcp_tools": [],
    "source": "api"
  }
}
```

**响应 400：**
```json
{"success": false, "error": "name is required"}
```

---

## 5. MCP 工具管理

### `GET /agent/tools`

列出所有 MCP 工具。

```bash
curl -s http://localhost:28000/agent/tools
```

**响应 200：**
```json
{
  "success": true,
  "tools": [
    {
      "name": "web_search",
      "description": "Web 搜索",
      "input_schema": {"query": "string"},
      "remote_url": null,
      "remote_tool_name": null,
      "enabled": true
    }
  ]
}
```

### `POST /agent/tools`

注册一个新 MCP 工具。

**Request Body：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | 工具名 |
| `description` | string |   | 描述 |
| `input_schema` | object |   | 入参 JSON Schema |
| `handler` | object |   | 本地 handler 描述（仅在进程内注册，HTTP API 调用方通常传 `remote_url`）|
| `remote_url` | string |   | 远程 MCP 服务 URL |
| `remote_tool_name` | string |   | 远程工具名（默认同 `name`）|
| `enabled` | bool |   | 默认 `true` |

**示例：注册远程 Web 搜索工具**
```bash
curl -s -X POST http://localhost:28000/agent/tools \
  -H "Content-Type: application/json" \
  -d '{
    "name": "web_search",
    "description": "Web 搜索",
    "input_schema": {
      "type": "object",
      "properties": {"query": {"type": "string"}},
      "required": ["query"]
    },
    "remote_url": "https://mcp.example.com/v1/tools",
    "remote_tool_name": "search",
    "enabled": true
  }'
```

**响应 201：**
```json
{
  "success": true,
  "tool": {
    "name": "web_search",
    "description": "Web 搜索",
    "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    "remote_url": "https://mcp.example.com/v1/tools",
    "remote_tool_name": "search",
    "enabled": true
  }
}
```

### `PATCH /agent/tools/<name>/enabled`

启用或禁用一个工具（不会删除注册，只是临时屏蔽）。

**Request Body：**
```json
{"enabled": true}
```

**示例：禁用 web_search**
```bash
curl -s -X PATCH http://localhost:28000/agent/tools/web_search/enabled \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

**示例：重新启用**
```bash
curl -s -X PATCH http://localhost:28000/agent/tools/web_search/enabled \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'
```

**响应 200：**
```json
{
  "success": true,
  "tool": {
    "name": "web_search",
    "description": "Web 搜索",
    "input_schema": {...},
    "remote_url": "...",
    "remote_tool_name": "search",
    "enabled": false
  }
}
```

**响应 404（工具不存在）：**
```json
{"success": false, "error": "\"Tool 'xxx' not found in registry\""}
```

---

## 6. Agent Pool 管理

### `POST /agent/pool/register`

注册一个新的 Agent 实例到桥接器。

**Request Body：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | Agent 唯一名（绑定 session 时按这个路由） |
| `base_url` | string | ✅ | opencode serve URL（如 `http://192.168.1.101:4096`）|
| `sdk_type` | string |   | `opencode` (默认) 或 `claude_code` |
| `default_model` | string |   | 此 Agent 的默认模型 |

**示例：注册一个远程 opencode 实例**
```bash
curl -s -X POST http://localhost:28000/agent/pool/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "agent-shanghai",
    "base_url": "http://192.168.1.101:4096",
    "sdk_type": "opencode",
    "default_model": "claude-sonnet-4-5"
  }'
```

**示例：注册一个 Claude Code 实例**
```bash
curl -s -X POST http://localhost:28000/agent/pool/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "claude-bot",
    "base_url": "local",
    "sdk_type": "claude_code"
  }'
```

**响应 201：**
```json
{
  "success": true,
  "name": "agent-shanghai",
  "base_url": "http://192.168.1.101:4096",
  "sdk_type": "opencode",
  "status": "registered"
}
```

**响应 400：**
```json
{"success": false, "error": "name and base_url are required"}
```

或

```json
{"success": false, "error": "invalid sdk_type 'foo', must be 'opencode' or 'claude_code'"}
```

> 默认行为：服务启动时**自动注册一个 `opencode-core`**（指向 `AGENT_SCHEDULER_OPENCODE_BASE_URL`，默认 `http://localhost:4096`）。如果想关掉，启动时设 `AGENT_SCHEDULER_AUTO_REGISTER_DEFAULTS=false`。
>
> 如果想自定义默认 Agent 列表，设 `AGENT_SCHEDULER_DEFAULT_AGENTS_JSON='[{"name":"...","base_url":"...","sdk_type":"opencode"}]'`

### `DELETE /agent/pool/<name>`

注销 Agent 实例。**当前未实现，返回 501。**

```bash
curl -s -X DELETE http://localhost:28000/agent/pool/agent-shanghai
```

**响应 501：**
```json
{"success": false, "name": "agent-shanghai", "error": "Unregister not implemented via bridge"}
```

### `GET /agent/pool/stats`

获取当前已注册 Agent 的统计信息。

```bash
curl -s http://localhost:28000/agent/pool/stats
```

**响应 200：**
```json
{
  "total_agents": 2,
  "agents": {
    "opencode-core": {
      "name": "opencode-core",
      "base_url": "http://localhost:4096",
      "sdk_type": "opencode",
      "api_key": null,
      "username": null,
      "password": null,
      "default_model": null,
      "default_skills": [],
      "default_tools": [],
      "capabilities": []
    },
    "agent-shanghai": {
      "name": "agent-shanghai",
      "base_url": "http://192.168.1.101:4096",
      "sdk_type": "opencode",
      "api_key": null,
      "username": null,
      "password": null,
      "default_model": "claude-sonnet-4-5",
      "default_skills": [],
      "default_tools": [],
      "capabilities": []
    }
  }
}
```

---

## 7. Scenario 路由（P6）

> Scenario 子系统按 YAML 配置把请求路由到不同 Agent。完整概念见 `docs/scenarios/` 下的设计文档。

### `GET /agent/scenarios`

列出所有已注册的 scenario。

```bash
curl -s http://localhost:28000/agent/scenarios
```

**响应 200：**
```json
{
  "success": true,
  "scenarios": [
    {"name": "travel", "priority": 10, "matched_keywords": ["机票", "航班"]},
    {"name": "weather", "priority": 5, "matched_keywords": ["天气", "气温"]}
  ]
}
```

### `GET /agent/scenarios/<name>`

查询单个 scenario 的完整定义。

```bash
curl -s http://localhost:28000/agent/scenarios/travel
```

### `POST /agent/scenarios`

动态注册或覆盖一个 scenario（YAML 形式的 body 字段较复杂，详见 `scenario_controller.py` 的 `@body(...)` 定义）。

```bash
curl -s -X POST http://localhost:28000/agent/scenarios \
  -H "Content-Type: application/json" \
  -d @travel_scenario.json
```

### `DELETE /agent/scenarios/<name>`

注销一个 scenario。

```bash
curl -s -X DELETE http://localhost:28000/agent/scenarios/travel
```

### `POST /agent/scenarios/reload`

从所有 `scenario_paths` 目录重新加载 YAML。

```bash
curl -s -X POST http://localhost:28000/agent/scenarios/reload
```

**响应 200：**
```json
{"success": true, "reloaded": 5, "errors": []}
```

### `GET /agent/scenarios/<name>/validate`

校验单个 scenario 的语法（不注册）。

```bash
curl -s http://localhost:28000/agent/scenarios/travel/validate
```

**响应 200：**
```json
{"success": true, "valid": true, "errors": []}
```

### `POST /agent/scenarios/<name>/chat`

向指定 scenario 发起 chat（**当前为 stub**，未来用于 routing-log 复现）。

```bash
curl -s -X POST http://localhost:28000/agent/scenarios/travel/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "北京到上海"}'
```

### `POST /agent/scenarios/<name>/chat/stream`

流式版（同样 stub）。

```bash
curl -N -s -X POST http://localhost:28000/agent/scenarios/travel/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "北京到上海"}'
```

### `GET /agent/scenarios/routing-log`

导出 routing 决策的历史（stub）。

```bash
curl -s http://localhost:28000/agent/scenarios/routing-log
```

---

## 8. 错误响应统一格式

所有失败响应都是：

```json
{
  "success": false,
  "error": "<人类可读的错误描述>"
}
```

特殊字段：
- `code`：业务错误码（如 `ROUTING_FAILED`）
- `action`：建议的下一步操作（可选）
- `status`：HTTP 状态码
- `traceback`：仅 `settings.debug=True` 且 5xx 时出现

---

## 9. 通用示例

### 完整对话流程

```bash
# 1. 注册一个 Agent（如果没自动注册）
curl -s -X POST http://localhost:28000/agent/pool/register \
  -H "Content-Type: application/json" \
  -d '{"name":"opencode-core","base_url":"http://localhost:4096","sdk_type":"opencode"}'

# 2. 创建一个会话
SESSION_ID=$(curl -s -X POST http://localhost:28000/agent/session \
  -H "Content-Type: application/json" \
  -d '{"agent_name":"opencode-core"}' | jq -r '.session_id')
echo "Session: $SESSION_ID"

# 3. 发消息
curl -s -X POST http://localhost:28000/agent/chat \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"$SESSION_ID\",
    \"message\": \"你好\"
  }" | jq

# 4. 再发消息（续接上下文）
curl -s -X POST http://localhost:28000/agent/chat \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"$SESSION_ID\",
    \"message\": \"我刚才说什么了？\"
  }" | jq

# 5. 查看历史
curl -s http://localhost:28000/agent/session/$SESSION_ID/messages | jq

# 6. 流式版
curl -N -s -X POST http://localhost:28000/agent/chat/stream \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"$SESSION_ID\",
    \"message\": \"讲个笑话\"
  }"

# 7. 中止（如果在等流）
curl -s -X POST http://localhost:28000/agent/session/$SESSION_ID/abort

# 8. 删除
curl -s -X DELETE http://localhost:28000/agent/session/$SESSION_ID
```

### MCP 工具调用

```bash
# 1. 注册工具
curl -s -X POST http://localhost:28000/agent/tools \
  -H "Content-Type: application/json" \
  -d '{
    "name": "calculator",
    "description": "数学计算",
    "input_schema": {"type":"object","properties":{"expr":{"type":"string"}}},
    "remote_url": "http://mcp.local/calc",
    "remote_tool_name": "calc",
    "enabled": true
  }'

# 2. 列出
curl -s http://localhost:28000/agent/tools | jq '.tools[].name'

# 3. 在 chat 中使用
curl -s -X POST http://localhost:28000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "100 + 200 等于多少？",
    "tools": ["calculator"]
  }'

# 4. 临时禁用
curl -s -X PATCH http://localhost:28000/agent/tools/calculator/enabled \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

---

## 10. 调试技巧

### 看结构化日志（JSON 格式）

```bash
# 启动时设 AGENT_SCHEDULER_LOG_FORMAT=json，所有日志一行一条 JSON
tail -f logs.json | jq -c '. | {ts:.timestamp, level, event, ...}'
```

### 用 jq 提取 SSE 文本流

```bash
curl -N -s -X POST http://localhost:28000/agent/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"讲个故事"}' | grep '^data:' | sed 's/^data: //' | jq -r 'select(.type=="text") | .data.content'
```

### 看 OpenAPI 文档

服务跑起来后，访问 `http://localhost:28000/docs`（由 sanic-ext 自动生成）。

---

## 11. 配置参考

服务行为受 `.env` 文件里的 `AGENT_SCHEDULER_*` 前缀环境变量控制（完整列表见 `src/hermetic_agent/config/settings.py`）。最常用的：

| 变量 | 默认 | 说明 |
|------|------|------|
| `AGENT_SCHEDULER_HOST` | `0.0.0.0` | 监听地址 |
| `AGENT_SCHEDULER_PORT` | `8000` | 监听端口（前端用 `28000`） |
| `AGENT_SCHEDULER_LOG_FORMAT` | `json` | `json` 或 `text` |
| `AGENT_SCHEDULER_STORAGE_BACKEND` | `postgres` | `postgres` 或 `memory` |
| `AGENT_SCHEDULER_POSTGRES_DSN` | `postgresql://localhost:5432/hermetic_agent` | |
| `AGENT_SCHEDULER_OPENCODE_BASE_URL` | `http://localhost:4096` | 默认 Agent 指向的 opencode serve |
| `AGENT_SCHEDULER_AUTO_REGISTER_DEFAULTS` | `true` | 启动时自动注册默认 Agent |
| `AGENT_SCHEDULER_DEFAULT_AGENTS_JSON` | `[]` | 自定义默认 Agent 列表 |
| `AGENT_SCHEDULER_MCP_TOOLS_CONFIG` | `[]` | 启动时自动注册的 MCP 工具 |
| `AGENT_SCHEDULER_SKILL_PATHS` | `[]` | 启动时加载的 Skill 目录 |
| `AGENT_SCHEDULER_DEBUG` | `false` | 是否在 5xx 响应里暴露 traceback |
