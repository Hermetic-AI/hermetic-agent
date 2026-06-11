# OpenAgent API Reference

> **OpenAgent Agent Scheduler Hub** — OpenCode / Claude Code 双 SDK Agent 调度平台
>
> **完整 OpenAPI 规范**: [openapi.json](openapi.json) (26 paths, 8 tags, 12 错误码)
>
> **设计源文档**: [docs/design/integrated-orchestration-plan.md](design/integrated-orchestration-plan.md)

---

## 0. 快速开始

```bash
# 启动 server
python -m openagent.main

# 健康检查
curl http://localhost:8000/health
# {"status": "ok"}

# 就绪检查 (含 scenario/turn 子系统)
curl http://localhost:8000/ready
# {"ready": true, "checks": {...}}

# 发起 chat (指定 scenario)
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "帮我订明天北京到上海", "scenario": "flight_booking"}'

# 流式 chat (SSE, 含 scenario + HITL 事件)
curl -N -X POST http://localhost:8000/agent/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "帮我订机票", "scenario": "flight_booking"}'
```

---

## 1. 端点索引 (按 Tag 分组)

### 1.1 System (`/health` · `/ready`)

| 方法 | 路径 | 描述 |
|---|---|---|
| GET | `/health` | 进程存活探针 |
| GET | `/ready` | 聚合就绪检查 (storage / bridge / registry / scenario / turn_store / hitl) |

详见 [openapi.json §/health, //ready](openapi.json)。

### 1.2 Chat (`/agent/chat` · `/agent/chat/stream`) — **F2 改造**

| 方法 | 路径 | 描述 |
|---|---|---|
| POST | `/agent/chat` | 同步 chat; 响应新增 `scenario` + `routing` 字段; 用 `injection.final_*` 调 bridge |
| POST | `/agent/chat/stream` | SSE 流; 开头 emit `scenario` 事件; HITL 走 SuspendableScheduler 推 `card` + `suspend` |

**完整事件序列 + 5 个 book-flight 剧本示例**: [api/scenarios.md §2](api/scenarios.md)

### 1.3 Session (`/agent/session`)

| 方法 | 路径 | 描述 |
|---|---|---|
| POST | `/agent/session` | 创建新会话 |
| GET | `/agent/session/{id}` | 查询会话元信息 |
| GET | `/agent/session/{id}/messages` | 会话历史消息 |
| DELETE | `/agent/session/{id}` | 删除会话 |
| POST | `/agent/session/{id}/abort` | 中止运行中的会话 |

### 1.4 Turn (`/agent/turn/*`) — **F3 新增 HITL**

5 个端点，覆盖挂起 / 恢复 / 状态查询 / 补拉事件 / 心跳 / 取消。

**完整文档**: [api/scenarios.md §4](api/scenarios.md)

### 1.5 Skills (`/agent/skills`)

| 方法 | 路径 | 描述 |
|---|---|---|
| GET | `/agent/skills` | 列出已注册 skill |
| POST | `/agent/skills` | 注册/覆盖一个 skill |

### 1.6 Tools (`/agent/tools`)

| 方法 | 路径 | 描述 |
|---|---|---|
| GET | `/agent/tools` | 列出 MCP 工具 |
| PATCH | `/agent/tools/{name}/enabled` | 启用/禁用 |

### 1.7 Pool (`/agent/pool/*`)

| 方法 | 路径 | 描述 |
|---|---|---|
| GET | `/agent/pool/stats` | Agent 实例池统计 |
| POST | `/agent/pool/register` | 注册 Agent 实例 |
| DELETE | `/agent/pool/{name}` | 注销 |

### 1.8 Scenarios (`/agent/scenarios/*`) — **P6 新增**

9 个端点：list / get / register / delete / reload / validate / chat / chat-stream / routing-log

**完整文档**: [api/scenarios.md §3](api/scenarios.md)

---

## 2. 通用数据结构

### 2.1 请求公共字段 (`ChatRequest`)

```json
{
  "message": "用户消息 (必填)",
  "session_id": "可选, 继续已有会话",
  "agent_name": "可选, 指定 Agent",
  "model": "可选, 指定模型 (MiniMax-M2.7-highspeed 等)",
  "system_prompt": "可选, 但 scenario 注入会覆盖",
  "skills": ["可选", "但会被 scenario 白名单过滤"],
  "tools": ["可选", "但会被 scenario 白名单过滤"],
  "timeout": "可选, 秒",
  "scenario": "可选, 显式指定 scenario (URL/Header 也可)"
}
```

### 2.2 响应公共字段 (`ChatResponse`)

```json
{
  "success": true,
  "session_id": "...",
  "agent_name": "claude-core",
  "result": {
    "message": {"role": "assistant", "content": "..."},
    "tool_calls": [...],
    "stop_reason": "end_turn"
  },
  "error": null,
  "duration": 1.234,
  "scenario": {              // F2 新增
    "name": "flight_booking", "version": "1.2.0",
    "orchestration": "hitl", "matched_by": "body"
  },
  "routing": {               // F2 新增
    "matched_by": "body",
    "rejected_skills": [],
    "rejected_tools": []
  }
}
```

### 2.3 SSE 事件通用格式 (12 种事件)

所有 SSE 事件都是 `data: {<envelope>}\n\n` 格式, envelope:

```json
{
  "type": "scenario" | "session" | "text" | "reasoning" | "tool_use" | "tool_result" |
         "card" | "state" | "suspend" | "resume" | "done" | "error",
  "data": { ... }
}
```

**完整事件契约**: [api/scenarios.md §2.3](api/scenarios.md) 和 [openapi.json](openapi.json)。

---

## 3. 错误码 (12 个)

| HTTP | code | 含义 |
|---|---|---|
| 400 | `SCENARIO_NOT_FOUND` | scenario 不存在 |
| 400 | `SCENARIO_DISABLED` | scenario 被禁用 |
| 400 | `SCENARIO_VALIDATION_FAILED` | YAML schema 校验失败 |
| 503 | `SCENARIO_RESOURCE_UNAVAILABLE` | 物理资源缺失 |
| 503 | `SCENARIO_WORKSPACE_FORBIDDEN` | workspace cwd 是 / 或 ~ |
| 400 | `SKILL_NOT_ALLOWED` | 越权 skill |
| 400 | `TOOL_NOT_ALLOWED` | 越权 tool |
| 400 | `POLICY_VIOLATION` | path/command/network 违规 |
| 400 | `SKILL_BUDGET_EXCEEDED` | progressive_skill 超 budget |
| 422 | `YAML_PLACEHOLDER_UNRESOLVED` | `${...}` 未注入 |
| 500 | `LAUNCH_FAILED` | 引擎启动失败 |
| 500 | `ROUTING_FAILED` | 无 default 兜底 |

**详细 + action 字段**: [api/scenarios.md §5](api/scenarios.md) 和 [openapi.json §components.ERROR_CODES](openapi.json)。

---

## 4. 6 个内置 Scenario

| 名称 | orchestration | tool_level | a2ui | progressive |
|---|---|---|---|---|
| `_generic` | single | safe | off | none |
| `_default` | single | safe | off | none |
| `flight_booking` | hitl | standard | on (8 cards) | on_demand (4k) |
| `expense_audit` | parallel | standard | off | all (6k) |
| `customer_service` | hitl | safe | on (2 cards) | on_demand (2k) |
| `code_review` | delegate | standard | off | all (6k) |

**配置 + 修改**: 编辑 `work/scenarios/*.scenario.yaml`, 然后 `POST /agent/scenarios/reload` 热重载。

---

## 5. 文档索引

| 文件 | 主题 |
|---|---|
| **[openapi.json](openapi.json)** | 完整 OpenAPI 3.0 规范 (26 paths, 8 tags) |
| **[api/scenarios.md](api/scenarios.md)** | Scenario / Turn 端点 + 事件契约 + 5 剧本示例 |
| [docs/design/integrated-orchestration-plan.md](design/integrated-orchestration-plan.md) | 集成方案总设计 (P0-P7) |
| [docs/skill/book-flight-skill.md](skill/book-flight-skill.md) | 飞鹤 AI 订票业务 SKILL (13 状态状态机) |
| [docs/design/scenario-routing-proposal.md](design/scenario-routing-proposal.md) | 场景化路由设计源 |
| [docs/design/agent-sandbox-plan.md](design/agent-sandbox-plan.md) | 沙箱 + 工具权限分层设计源 |
| [docs/design/book-flight-hitl-design.md](design/book-flight-hitl-design.md) | HITL / A2UI 协议设计源 |
| [CLAUDE.md](../.ai/CLAUDE.md) | 项目工程规范 (5 层代码分层 / 命名约定 / 质量约束) |

---

## 6. 重新生成 OpenAPI

设计源 (`@doc_summary` / `@body` / `@response` 等) 改了之后, 跑:

```bash
python scripts/export_openapi.py
```

会启 server 3s 抓 `/openapi/spec.json`, 失败时回落到 `docs/openapi.json` 内手写 26 paths (覆盖所有真实路由 + Scenario/Turn + 12 错误码)。
