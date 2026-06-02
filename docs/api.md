# Agent Scheduler Hub API 文档

> 基础 URL: `http://localhost:8000`

---

## 目录

- [健康检查](#健康检查)
- [Agent 管理](#agent-管理)
- [会话管理](#会话管理)
- [聊天](#聊天)

---

## 健康检查

### GET /health

健康检查端点

```bash
curl http://localhost:8000/health
```

**响应示例**
```json
{
  "status": "ok"
}
```

---

### GET /ready

就绪检查（检查 Agent 池状态）

```bash
curl http://localhost:8000/ready
```

**响应示例**
```json
{
  "status": "ready",
  "pool": {
    "total": 1,
    "idle": 1,
    "busy": 0,
    "unhealthy": 0
  }
}
```

---

## Agent 管理

### POST /agent/pool/register

注册新 Agent 实例

```bash
curl -X POST http://localhost:8000/agent/pool/register \
  -H "Content-Type: application/json" \
  -d '{"name": "agent-shanghai", "base_url": "http://192.168.1.101:4096"}'
```

**请求体**
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | Agent 实例名称 |
| base_url | string | 是 | Agent 服务地址 |

**响应示例 (201)**
```json
{
  "success": true,
  "name": "agent-shanghai",
  "base_url": "http://192.168.1.101:4096",
  "status": "idle"
}
```

---

### DELETE /agent/pool/{name}

注销 Agent 实例

```bash
curl -X DELETE http://localhost:8000/agent/pool/agent-shanghai
```

**响应示例**
```json
{
  "success": true,
  "name": "agent-shanghai"
}
```

---

### GET /agent/pool/stats

获取实例池统计信息

```bash
curl http://localhost:8000/agent/pool/stats
```

**响应示例**
```json
{
  "total": 2,
  "idle": 1,
  "busy": 1,
  "unhealthy": 0
}
```

---

## 会话管理

### POST /agent/session

创建新会话

```bash
curl -X POST http://localhost:8000/agent/session \
  -H "Content-Type: application/json" \
  -d '{
    "agent_name": "default",
    "model": "claude-3-sonnet",
    "system_prompt": "你是一个有帮助的助手"
  }'
```

**请求体**
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| agent_name | string | 是 | Agent 实例名称 |
| model | string | 否 | 指定模型 |
| system_prompt | string | 否 | 系统提示词 |
| session_id | string | 否 | 指定会话 ID（用于恢复） |

**响应示例 (201)**
```json
{
  "success": true,
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "agent_name": "default",
  "agent_base_url": "http://192.168.1.101:4096",
  "model": "claude-3-sonnet"
}
```

---

### GET /agent/session/{session_id}

获取会话信息

```bash
curl http://localhost:8000/agent/session/550e8400-e29b-41d4-a716-446655440000
```

**响应示例**
```json
{
  "success": true,
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "agent_name": "default",
  "agent_base_url": "http://192.168.1.101:4096",
  "model": "claude-3-sonnet"
}
```

---

### GET /agent/session/{session_id}/messages

获取会话历史消息

```bash
curl http://localhost:8000/agent/session/550e8400-e29b-41d4-a716-446655440000/messages
```

**响应示例**
```json
{
  "success": true,
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "messages": [
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "你好！有什么可以帮助你的吗？"}
  ]
}
```

---

### DELETE /agent/session/{session_id}

删除会话

```bash
curl -X DELETE http://localhost:8000/agent/session/550e8400-e29b-41d4-a716-446655440000
```

**响应示例**
```json
{
  "success": true,
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

### POST /agent/session/{session_id}/abort

中止运行中的会话

```bash
curl -X POST http://localhost:8000/agent/session/550e8400-e29b-41d4-a716-446655440000/abort
```

**响应示例**
```json
{
  "success": true,
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

## 聊天

### POST /agent/chat

发送消息并获取回复（自动创建新会话）

```bash
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "你好，请介绍一下你自己",
    "agent_name": "default",
    "model": "claude-3-sonnet",
    "timeout": 60
  }'
```

**请求体**
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| message | string | 是 | 用户消息 |
| session_id | string | 否 | 会话 ID，不提供则创建新会话 |
| agent_name | string | 否 | 指定 Agent 实例 |
| model | string | 否 | 指定模型 |
| system_prompt | string | 否 | 系统提示词 |
| timeout | float | 否 | 超时时间（秒） |

**响应示例**
```json
{
  "success": true,
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "agent_name": "default",
  "result": "你好！我是...",
  "error": null,
  "duration": 2.35
}
```

---

### POST /agent/chat（继续会话）

在已有会话中继续发送消息

```bash
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "继续上一个问题",
    "session_id": "550e8400-e29b-41d4-a716-446655440000"
  }'
```

---

## 错误响应

所有接口的错误响应格式：

```json
{
  "success": false,
  "error": "错误描述信息"
}
```

**状态码**
| 状态码 | 说明 |
|--------|------|
| 400 | 请求参数错误 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |
| 503 | 服务不可用（如无可用 Agent） |
