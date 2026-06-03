# Scenario / Turn 端点参考

> **本文件覆盖**: 集成方案 (P6 + F2/F3) 新增的 14 个端点
> - 9 个 scenario 管理端点 (`/agent/scenarios/*`)
> - 5 个 turn 生命周期端点 (`/agent/turn/*`)
>
> 通用 chat / session / pool / skills / tools 端点见 [docs/api.md](api.md) 和 [openapi.json](../openapi.json)

---

## 1. Scenario 路由机制

请求进入 `/agent/chat` 或 `/agent/chat/stream` 之前, `ScenarioMiddleware` 会按 6 优先级路由到 1 个 scenario:

| 优先级 | 来源 | 配置开关 |
|---|---|---|
| 0 (最高) | URL path (`/agent/scenarios/{name}/chat`) | – |
| 1 | `X-Scenario` header | – |
| 2 | `body.scenario` | – |
| 3 | keyword 匹配 (`trigger_keywords`) | – |
| 4 | Intent 分类器 (LLM) | `settings.enable_intent_router=true` |
| 5 (最低) | `settings.default_scenario` | 默认 `_default` |

**6 个内置 scenario** (`work/scenarios/*.scenario.yaml`):

| 名称 | orchestration | tool_level | a2ui | progressive |
|---|---|---|---|---|
| `_generic` | single | safe | off | none |
| `_default` | single | safe | off | none |
| `flight_booking` | hitl | standard | on (8 cards) | on_demand (4k) |
| `expense_audit` | parallel | standard | off | all (6k) |
| `customer_service` | hitl | safe | on (2 cards) | on_demand (2k) |
| `code_review` | delegate | standard | off | all (6k) |

详见 [docs/design/integrated-orchestration-plan.md §6](../design/integrated-orchestration-plan.md)。

---

## 2. `/agent/chat` 与 `/agent/chat/stream` (F2 改造)

### 2.1 行为变化

`POST /agent/chat` 和 `POST /agent/chat/stream` 已经接入了 `ScenarioMiddleware` + `ScenarioInjector`:

- `body.scenario` / `X-Scenario` / keyword 命中后, 路由信息会注入 `request.ctx.scenario` 和 `request.ctx.injection`
- Controller 用 **`injection.final_system_prompt / final_skills / final_tools`** 调 `bridge.chat()`, **不再**用 caller 传的 `body.system_prompt / body.skills / body.tools`
- 客户端传越权 skill/tool → 注入器丢弃, 响应里 `routing.rejected_skills` 列出

### 2.2 `POST /agent/chat` 响应新增字段

```json
{
  "success": true,
  "session_id": "...",
  "agent_name": "claude-core",
  "result": { "message": { "role": "assistant", "content": "..." }, "tool_calls": [], "stop_reason": "end_turn" },
  "error": null,
  "duration": 1.234,
  "scenario": {                                // F2 新增
    "name": "flight_booking",
    "version": "1.2.0",
    "orchestration": "hitl",
    "matched_by": "body"
  },
  "routing": {                                 // F2 新增
    "matched_by": "body",
    "rejected_skills": ["evil_skill"],         // 越权被丢弃
    "rejected_tools": []
  }
}
```

### 2.3 `POST /agent/chat/stream` SSE 事件序列 (F2 新增 scenario 事件)

**普通场景** (single / parallel / delegate / chain):

```
event: scenario
data: {"type": "scenario", "data": {"name": "flight_booking", "version": "1.2.0", "matched_by": "body", "orchestration": "hitl"}}

event: session
data: {"type": "session", "data": {"session_id": "..."}}

event: text
data: {"type": "text", "data": {"content": "好的, 让我帮您..."}}

event: text
data: {"type": "text", "data": {"content": "查询中..."}}

event: done
data: {"type": "done", "data": {}}
```

**HITL 场景** (orchestration=hitl):

```
event: scenario
data: {"type": "scenario", "data": {"name": "flight_booking", "matched_by": "body", "orchestration": "hitl"}}

event: session
data: {"type": "session", "data": {"session_id": "..."}}

event: state
data: {"type": "state", "data": {"state": "S02"}}

event: text
data: {"type": "text", "data": {"content": "好的, 让我帮您订机票"}}

event: tool_use
data: {"type": "tool_use", "data": {"id": "ask_user_xyz", "name": "ask_user", "input": {"card_type": "OD_INPUT", ...}}}

event: card
data: {"type": "card", "data": {"card_id": "c1", "card_type": "OD_INPUT", "card": {...}, "correlation_id": "ask_user_xyz"}}

event: suspend
data: {"type": "suspend", "data": {"checkpoint_id": "ckpt-1", "card": {...}, "correlation_id": "ask_user_xyz", "input_schema": {...}, "timeout_at": 1234567890.0}}

(流停)
```

**场景错误** (middleware 失败):

```
event: error
data: {"type": "error", "data": {"message": "[SCENARIO_NOT_FOUND] scenario 'xxx' not found", "code": "SCENARIO_NOT_FOUND"}}
```

**事件类型汇总** (12 种):

| `type` | 含义 | 关键 payload |
|---|---|---|
| `scenario` | Scenario 路由结果 | `{name, version, matched_by, orchestration}` |
| `session` | 会话已建 | `{session_id}` |
| `text` | AI 增量文本 | `{content, delta?}` |
| `reasoning` | AI 思考 | `{content}` |
| `tool_use` | 工具调用 | `{id, name, input}` |
| `tool_result` | 工具结果 | `{id, output, is_error}` |
| `card` | 渲染 UI 卡片 (AUIP) | `{card_id, card_type, card, correlation_id}` |
| `state` | 业务状态切换 | `{state, note?}` |
| `suspend` | Turn 挂起 (HITL) | `{checkpoint_id, card, correlation_id, input_schema, timeout_at}` |
| `resume` | Turn 恢复 | `{checkpoint_id}` |
| `done` | 流结束 | `{stop_reason?}` |
| `error` | 错误 | `{message, code}` |

---

## 3. `/agent/scenarios/*` 9 端点

### 3.1 `GET /agent/scenarios` — 列出全部

```bash
$ curl http://localhost:8000/agent/scenarios?tag=travel
{
  "success": true,
  "total": 6,
  "scenarios": [
    {"name": "flight_booking", "version": "1.2.0", "description": "...", "enabled": true, "tags": ["travel","booking","prod"], "owner": "team-travel-ai", "tier": "gold", "source": "yaml"},
    ...
  ]
}
```

`?tag=travel` 过滤 `tags` 包含 `travel` 的 scenario。

### 3.2 `GET /agent/scenarios/{name}` — 查询单个

```bash
$ curl http://localhost:8000/agent/scenarios/flight_booking
{
  "success": true,
  "scenario": {  // 完整 ScenarioConfig
    "name": "flight_booking", "version": "1.2.0",
    "routing": {...}, "execution": {...}, "security": {...},
    "workspace": {...}, "a2ui": {...}, "progressive_skill": {...},
    "resource_dirs": {...}, "resources": {...}, "metadata": {...}
  }
}
```

`name` 不存在 → `404 SCENARIO_NOT_FOUND`。

### 3.3 `POST /agent/scenarios` — 注册/覆盖

```bash
$ curl -X POST http://localhost:8000/agent/scenarios \
  -H "Content-Type: application/json" \
  -d @new_scenario.json
```

Body 是 ScenarioConfig dict (字段见 [openapi.json §components.schemas](../openapi.json) 或 §3.3 schema)。

`201 {success, scenario, source: "api"}` · `400 SCENARIO_VALIDATION_FAILED` · `400 SCENARIO_WORKSPACE_FORBIDDEN` · `503 SCENARIO_RESOURCE_UNAVAILABLE`。

### 3.4 `DELETE /agent/scenarios/{name}` — 注销

```bash
$ curl -X DELETE http://localhost:8000/agent/scenarios/old
{"success": true, "name": "old"}
```

不存在的 scenario → `404 SCENARIO_NOT_FOUND`。

### 3.5 `POST /agent/scenarios/reload` — 热重载

从 `settings.scenario_paths` 重新加载所有 YAML, DB 优先 (admin UI 编辑过的不会被 YAML 覆盖)。

```bash
$ curl -X POST http://localhost:8000/agent/scenarios/reload
{"success": true, "loaded": 6}
```

### 3.6 `GET /agent/scenarios/{name}/validate` — 校验

不注册, 仅校验 (主要给 CI / dry-run 用)。返回 `{valid, scenario, errors}`。

### 3.7-3.8 `POST /agent/scenarios/{name}/chat[/stream]` — Stub

当前返回 `501 Not Implemented`。**推荐改用 `/agent/chat?scenario=flight_booking`** (F2 已支持)。

### 3.9 `GET /agent/scenarios/routing-log` — Stub

`501`, 未来 P9 阶段会接 Postgres 持久化。

---

## 4. `/agent/turn/*` 5 端点 (HITL)

> **前提**: `request.app.ctx.turn_store` 和 `request.app.ctx.hitl_factory` 必须已初始化 (由 `lifecycle._init_turn_subsystem` 启动时挂载)。

### 4.1 `GET /agent/turn/{turn_id}` — 查询 Turn 状态

```bash
$ curl http://localhost:8000/agent/turn/turn-abc123
{
  "success": true,
  "turn": {
    "session_id": "sess-1",
    "skill_name": "flight_booking",
    "skill_version": "1.0.0",
    "status": "suspended",  // running | suspended | done | error | cancelled
    "created_at": "2026-06-02T10:30:00Z"
  }
}
```

### 4.2 `GET /agent/turn/{turn_id}/events?after=N` — 补拉事件 (SSE)

```bash
$ curl "http://localhost:8000/agent/turn/turn-abc123/events?after=5"
data: {"type": "card", "data": {"card_id": "c1", "card_type": "OD_INPUT", ...}}
data: {"type": "suspend", "data": {"checkpoint_id": "ckpt-1", ...}}
data: {"type": "done", "data": {"reason": "replay_end", "replayed": 2}}
```

`?after=N` 跳过 seq ≤ N 的事件。最后以 `done (reason=replay_end)` 结束。

### 4.3 `POST /agent/turn/{turn_id}/resume` — 恢复挂起的 Turn (SSE)

```bash
$ curl -X POST http://localhost:8000/agent/turn/turn-abc123/resume \
  -H "Content-Type: application/json" \
  -d '{
    "correlation_id": "ask_user_xyz",
    "user_input": {"origin": "PEK", "destination": "SHA", "depart_date": "2026-06-03"},
    "action_id": "submit"
  }'

data: {"type": "resume", "data": {"checkpoint_id": "ckpt-1"}}
data: {"type": "tool_result", "data": {"id": "ask_user_xyz", "output": {"user_input": {...}, "action_id": "submit"}}}
data: {"type": "state", "data": {"state": "S02", "transition": "resume"}}
data: {"type": "done", "data": {"stop_reason": "end_turn"}}
```

错误: 推一个 `error` 事件 (code: `TURN_NOT_FOUND` / `SCENARIO_NOT_FOUND` / `HITL_NOT_READY`)。

### 4.4 `POST /agent/turn/{turn_id}/heartbeat` — 延长挂起超时

```bash
$ curl -X POST http://localhost:8000/agent/turn/turn-abc123/heartbeat
{"success": true, "turn_id": "turn-abc123", "status": "suspended", "ts": 1234567890.123}
```

前端每 60s 调一次, 防止 5min 挂起超时。

### 4.5 `POST /agent/turn/{turn_id}/cancel` — 取消

```bash
$ curl -X POST http://localhost:8000/agent/turn/turn-abc123/cancel
{"success": true, "turn_id": "turn-abc123", "status": "cancelled"}
```

已 suspend 的 turn 不会再被 resume。

---

## 5. 错误码 (12 个, F2/F3 全覆盖)

| HTTP | code | 含义 | 典型 action 字段 |
|---|---|---|---|
| 400 | `SCENARIO_NOT_FOUND` | 引用的 scenario 不存在 | `Available: [_generic, _default, ...]` |
| 400 | `SCENARIO_DISABLED` | scenario 被禁用 | `Enable via PATCH /agent/scenarios/{name}` |
| 400 | `SCENARIO_VALIDATION_FAILED` | YAML schema 校验失败 | 列出失败字段名 |
| 503 | `SCENARIO_RESOURCE_UNAVAILABLE` | 物理资源缺失 | 列出缺失路径, 提示创建 |
| 503 | `SCENARIO_WORKSPACE_FORBIDDEN` | cwd 是 / | `Use ${PROJECT_DIR}` |
| 400 | `SKILL_NOT_ALLOWED` | 越权 skill | `Reduce caller_skills` |
| 400 | `TOOL_NOT_ALLOWED` | 越权 tool | (同 injector) |
| 400 | `POLICY_VIOLATION` | path/command/network 违规 | 描述如何放行 |
| 400 | `SKILL_BUDGET_EXCEEDED` | progressive_skill 片段超 budget | `Reduce load_on_state or raise budget` |
| 422 | `YAML_PLACEHOLDER_UNRESOLVED` | `${...}` 占位符未注入 | `Inject from auth middleware` |
| 500 | `LAUNCH_FAILED` | 引擎启动失败 | `opencode serve failed at cwd {cwd}: {stderr}` |
| 500 | `ROUTING_FAILED` | 无 default 兜底 | (router 内部, 列出所有候选 + 拒绝原因) |

所有错误响应都是结构化的:

```json
{
  "success": false,
  "code": "SCENARIO_RESOURCE_UNAVAILABLE",
  "error": "Scenario 'flight_booking' has missing resources",
  "action": "Create the missing files or fix resource_dirs.cards in the scenario YAML",
  "detail": {
    "missing": ["/work/scenarios/flight_booking/cards/OD_INPUT.card.yaml"]
  }
}
```

---

## 6. 完整调用示例: 5 个 book-flight 剧本

### 6.1 剧本 A: 单程经济舱 happy path (6 次挂起)

```bash
# 1. 发起 chat
curl -N -X POST http://localhost:8000/agent/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "帮我订明天北京到上海", "scenario": "flight_booking"}'

# 收: scenario → session → state(S01) → text → tool_use(query_flight) → 
#     tool_result → state(S05) → card(FLIGHT_LIST) → suspend

# 2. 用户选航班
curl -N -X POST http://localhost:8000/agent/turn/turn-X/resume \
  -H "Content-Type: application/json" \
  -d '{"correlation_id": "...", "user_input": {"flightId": "CA1501-20260603-0900"}, "action_id": "select"}'

# 收: resume → tool_result → state(S06) → tool_use(choose_cabin) → 
#     tool_result → card(CABIN_LIST) → suspend

# 3-6. 类似: 选舱 / 选乘机人 / 选 OAT / 选成本中心 / 确认价 / 预览 / 下单
# ... 共 6 次挂起 / 恢复 ...

# 最后一次: card(ORDER_SUCCESS) → done
```

### 6.2 剧本 C: 核价变价 → 用户决策

```
S10 validate_booking_info → priceChanged=true
   ↓
state S11
   ↓
card POLICY_DECISION (with surcharge, decision_buttons)
   ↓
suspend
   ↓
用户选 "差额补现"
   ↓
resume
   ↓
tool_result → record_policy_user_decision(PAY_SURCHARGE)
   ↓
state S10 (回退) → 继续
```

### 6.3 剧本 D: 代订权限缺失 → F2

```
S08 fill_passenger("李四") → unresolvedNames=["李四"]
   ↓
立即转 F2 CANNOT_ORDER (不再推进)
   ↓
card CANNOT_ORDER (reason: 无代订权限)
   ↓
suspend → done
```

完整状态机见 [docs/skill/book-flight-skill.md §2](../skill/book-flight-skill.md)。
