# Book-Flight HITL 设计方案：可中断 / 可恢复的 AI 订票对话

> 版本：v0.1  状态：**设计稿**  作者：Claude  最后更新：2026-06-02
> 关联：`docs/skill/book-flight-skill.md`（v0.1 13 状态机票预订 SKILL）
> 目标：在现有 **OpenCode / Claude Code 双 SDK** 之上，引入 **可中断 / 可恢复** 的对话执行模型，并让 Agent 能以 **声明式 UI 卡片** 主动向用户发起信息补充 / 确认请求。

---

## 0. 摘要

`book-flight-skill.md` 定义了 13 个状态，其中 5 个是「等待用户」状态（`S02 OD_PENDING`、`S04 DATE_PENDING`、`S08 PASSENGER_PENDING`、`S11 PRICE_CONFIRMED`、`S13 READY_TO_SUBMIT`），还有 1 个可恢复的等待分支 `F3 POLICY_MULTI_CONDITION`。这些状态需要 AI 在中途停下来，把决定权交回用户，等用户补全信息后再恢复执行。

当前架构（参见 CLAUDE.md）**没有这个能力**：

| 现状 | 缺口 |
|---|---|
| `Scheduler.run()` 一次性同步返回 | 无法「挂起」 |
| `StreamEvent` 只有 `text/reasoning/tool_use/tool_result/done/error` | 没有「请用户输入」事件 |
| `Skill` 只声明 `input_schema` / `mcp_tools` | 没有「UI 卡片」声明 |
| `Session` 持久化只存 message | 没有「业务上下文 + 检查点」 |
| 前端只渲染 `text` 流 | 不会渲染表单 / 卡片 / 决策按钮 |

**本文提出的方案**：在保持 OpenCode / Claude Code 双 SDK 兼容的前提下，新增 **AUIP（Agent-UI Interaction Protocol）** 协议层 + **SuspendableScheduler** 调度内核 + **AUIRenderer** 渲染器，把"AI 等待用户"变成一等公民。

---

## 1. 设计原则（Design Principles）

> 这些原则高于一切具体实现，是评审 PR 时的判断标准。

| 原则 | 含义 | 反例 |
|---|---|---|
| **P1：双 SDK 透明** | 同一套协议对 OpenCode 和 Claude Code 都要工作，Adapter 层只做事件映射，不参与挂起逻辑 | 在 OpenCodeAdapter 里写一套挂起逻辑、ClaudeCodeAdapter 里写另一套 |
| **P2：Agent 决定何时挂起，但框架决定如何挂起** | AI 通过调用 `ask_user` 工具表达"我要问用户"，但具体怎么把工具调用转成 UI 卡片、怎么落库、怎么恢复，全在框架 | 让 AI 自己拼接 JSON 卡片 |
| **P3：检查点是不可变事件流** | 每次状态变化都追加一条 `TurnEvent`；恢复时从最近一个 `SUSPEND` 后 replay | 改写历史消息 |
| **P4：UI 是声明式 schema，不是指令式动作** | AI 输出"我要个表单"，不输出"在这个 div 里插一个 input" | 嵌入式 HTML / 指令 |
| **P5：幂等优先于性能** | 任何挂起点允许用户刷新页面、关掉浏览器、过 5 分钟再回来；后端可以无副作用 replay | 一次性"窗口期" |
| **P6：向前兼容** | 旧 Skill（无 `ui:` 块）必须照常工作，自动降级为"等用户在聊天框打字" | 强制所有 Skill 升级 |
| **P7：业务 Skill 框架** | Skill 的状态机是**第一公民**，框架负责 **状态守卫 + 工具白名单 + 卡片契约**；Skill 作者只写 prompt | 让 Skill 作者手写状态机校验 |

---

## 2. 核心概念

### 2.1 Turn（轮次）

> 一次"用户问 → AI 答"可能跨**多个挂起点**，我们把整个跨度叫一个 **Turn**。

```
Turn
 ├─ Event 1  session
 ├─ Event 2  text         "好的，让我帮您预订"
 ├─ Event 3  tool_use     ask_user
 ├─ Event 4  suspend      { card: OD_INPUT, state: S02 }
 ├─  (waiting user, 5min)
 ├─ Event 5  user_input   { origin: "PEK", destination: "SHA" }
 ├─ Event 6  tool_result  ask_user → { ack }
 ├─ Event 7  text         "已查询航班..."
 ├─ Event 8  card         FLIGHT_LIST
 ├─ ... (continue)
 └─ Event N  done | error
```

`turn_id` 是 `Session` 下的二级标识。同一 Session 可有多个 Turn（如改机票、新一轮订餐）。

### 2.2 SuspendPoint（挂起点）

```python
@dataclass
class SuspendPoint:
    turn_id: str
    checkpoint_id: str                  # 用于 replay
    state: str                          # 业务状态，如 S02
    card: Card                          # 声明式 UI 卡片
    input_schema: dict                  # 用户提交内容的 JSON Schema
    timeout_at: datetime | None         # 过期时间
    correlation_id: str                 # 与原始 ask_user 工具调用的 id 对齐
```

### 2.3 Card（声明式 UI）

> 借鉴 **A2UI**（Agent-to-UI）的核心理念：**agent 输出结构化描述，宿主渲染**。但比 A2UI 更精简，因为我们已经知道业务域（机票）。

```jsonc
{
  "card_type": "form",                    // 参见 §5.2 卡片目录
  "schema_version": "1.0",
  "title": "请告诉我出发地 / 目的地",
  "body": { "message": "您刚才说『订机票』，我需要知道城市和日期" },
  "fields": [
    { "id": "origin", "label": "出发城市", "type": "city_picker", "required": true },
    { "id": "destination", "label": "目的城市", "type": "city_picker", "required": true },
    { "id": "depart_date", "label": "出发日期", "type": "date", "required": true }
  ],
  "actions": [
    { "id": "submit", "label": "确认", "style": "primary" },
    { "id": "cancel", "label": "取消", "style": "ghost", "confirm": true }
  ],
  "metadata": { "state": "S02", "skill": "book-flight" }
}
```

### 2.4 Checkpoint（检查点）

每次挂起前，框架把以下内容**原子写入 Postgres**：

```jsonc
{
  "turn_id": "...",
  "checkpoint_id": "uuid",
  "skill_name": "book-flight",
  "skill_version": "0.1.0",
  "state": "S02",
  "skill_ctx": { /* §5.2.2 of book-flight-skill.md */ },
  "messages": [/* 截至当前为止的所有 ChatMessage */],
  "open_tool_calls": [/* 还未收到 tool_result 的 tool_use */],
  "last_event_seq": 42,
  "created_at": "..."
}
```

> **不**直接把"我接下来要让用户选什么"写进 checkpoint —— 那是**下一次** `ask_user` 工具调用时由 AI 重新生成，框架不做业务决策。

### 2.5 Skill State Manifest（Skill 状态声明）

> 把 `book-flight-skill.md` 里的"13 状态 + 工具白名单 + 入口守卫"做成**机器可读**的 manifest，注入到 system prompt **和**框架侧双重校验。

```yaml
# book-flight.skill.yaml
name: book-flight
version: 0.1.0
description: 飞鹤 AI 订票助手
triggers: [订票, 买机票, 订机票]

# 业务状态机
states:
  - id: S02
    description: 出发/返程城市未确认
    card: OD_INPUT                       # 等待时渲染的卡片
    allowed_tools: []                    # 等待态只允许 ask_user
    timeout: 5m
  - id: S11
    description: 价格/差标变价
    card: POLICY_DECISION
    allowed_tools: [record_policy_user_decision]
    timeout: 10m
  # ... 完整 13 状态

# UI 卡片目录
ui:
  cards: [OD_INPUT, FLIGHT_LIST, CABIN_LIST, PASSENGER_FORM, OAT_BINDING,
          PRICE_VERIFY, POLICY_DECISION, ORDER_CONFIRM, ORDER_SUCCESS,
          CANNOT_ORDER, CHAT_FALLBACK]

# 关联 MCP 服务
mcp_servers: [domestic-booking-mcp]

# 模型偏好
preferred_provider: claude_code
fallback_provider: opencode
```

**SKILL.md 的 prose 部分**仍然保留（作为人类可读文档 + prompt 模板），但**机器可读的状态契约**下沉到 `*.skill.yaml`，二者通过 CI 校验一致性。

---

## 3. 整体架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Frontend  (React + TS + Vite)                      │
│                                                                       │
│   ┌─────────────────┐  ┌──────────────────┐  ┌───────────────────┐  │
│   │  <ChatStream/>  │  │  <AUIRenderer/>  │  │   <TurnState/>    │  │
│   │  text/reasoning │  │  card → React    │  │   idle|running|   │  │
│   │  SSE consumer   │  │  8 catalog types │  │   suspended|done  │  │
│   └────────┬────────┘  └────────┬─────────┘  └──────┬────────────┘  │
│            │                    │                    │                │
│            └─────────►  turnStore (Zustand)  ◄──────┘                │
└──────────────────────────┬───────────────────────────────────────────┘
                           │  HTTP + SSE
┌──────────────────────────┴───────────────────────────────────────────┐
│                Sanic  (api/app.py + api/routes.py)                    │
│                                                                       │
│   POST   /agent/turn                       创建 Turn                  │
│   POST   /agent/turn/<id>/resume            提交用户输入并恢复         │
│   GET    /agent/turn/<id>                   查询 Turn 状态            │
│   GET    /agent/turn/<id>/events?after=N    SSE 增量事件              │
│   POST   /agent/turn/<id>/cancel            取消 Turn                 │
│   POST   /agent/turn/<id>/heartbeat         延长挂起超时               │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
┌──────────────────────────┴───────────────────────────────────────────┐
│           core.SuspendableScheduler  (新)                             │
│                                                                       │
│   run_turn(prompt)              ─►  AsyncIterator[TurnEvent]         │
│   resume(turn_id, user_input)   ─►  AsyncIterator[TurnEvent]         │
│   cancel(turn_id)                                                       │
│   get_state(turn_id)                                                    │
│                                                                       │
│   • 维护 turn ↔ provider 映射                                            │
│   • 拦截 ask_user 工具调用 → SuspendPoint                               │
│   • 在每个 state transition 写 checkpoint                                │
│   • 双 SDK 事件统一归一化                                                │
└──────┬──────────────────┬──────────────────┬─────────────────────────┘
       │                  │                  │
       │                  │                  │
┌──────┴───────┐  ┌───────┴────────┐  ┌──────┴──────────┐
│ skill.       │  │ providers.     │  │ store.          │
│ runtime      │  │ AgentBridge    │  │ TurnStore       │
│              │  │ (opencode |    │  │ (Postgres)      │
│ • Loader     │  │  claude_code)  │  │                 │
│ • StateGuard │  │                │  │  + SkillContext │
│ • CardBinder │  │  + event_map   │  │    (Redis)      │
│ • PrompBuild │  │                │  │                 │
└──────┬───────┘  └────────┬───────┘  └─────────────────┘
       │                   │
       │                   │
       └────────┬──────────┘
                │
                ▼
        AI Engines
   ┌────────┐   ┌────────────┐
   │OpenCode│   │Claude Code │
   │  serve │   │    CLI     │
   └────────┘   └────────────┘
```

### 3.1 与现状的对应关系

| 现有组件 | 角色 | 新增/扩展 |
|---|---|---|
| `core/scheduler.py` `Scheduler` | 一次性任务执行 | **保留**为 `LegacyScheduler`；新增 `SuspendableScheduler` |
| `core/agent_pool.py` | Agent 实例健康检查 | **保留**；`SuspendableScheduler` 通过它选实例 |
| `providers/base.py` | SDK 适配器接口 | 新增方法 `chat_stream(..., interrupt_aware=True)` |
| `providers/agent_bridge.py` | SDK 路由 | 不变（已能路由到任一 adapter） |
| `streaming.py` `StreamEvent` | 流式事件 | 扩展为 `TurnEvent`（见 §5.1） |
| `skills/registry.py` | Skill 注册 | 扩展：加载 `*.skill.yaml` 状态 manifest |
| `mcp/registry.py` | 工具注册 | 新增 `register_synthetic_tool('ask_user', ...)` |
| `store/base.py` | 持久化 | 新增 `TurnStore` / `SkillContextStore` |
| `api/routes.py` | REST | 新增 `/agent/turn/*` 路由族 |
| `frontend/` | React UI | 新增 `<AUIRenderer/>` + 卡片组件目录 |

---

## 4. 协议层：AUIP（Agent-UI Interaction Protocol）

> 这是本文最重要的产出物。**AUIP 是骨架，book-flight 是第一个用例**。

### 4.1 事件目录（Server → Client，SSE）

> 全部事件共用同一 envelope：

```jsonc
{
  "seq": 42,                          // 严格递增，客户端按 seq 排序、断点续传
  "ts": 1717350000.123,
  "turn_id": "...",
  "type": "card",                      // 事件类型
  "data": { ... }                      // 类型相关 payload
}
```

| `type` | 含义 | 关键 payload |
|---|---|---|
| `session` | Turn 已创建 | `{ session_id, turn_id, agent_name, model }` |
| `text` | AI 增量文本 | `{ delta, accumulated }` |
| `reasoning` | AI 思考 | `{ content }` |
| `tool_use` | AI 调用工具 | `{ id, name, input }` |
| `tool_result` | 工具结果 | `{ id, output, is_error }` |
| `card` | 渲染 UI 卡片 | `{ card_id, card_type, schema, actions, dismissible }` |
| `state` | 业务状态切换 | `{ state, allowed_tools[], note }` |
| `suspend` | Turn 进入挂起 | `{ checkpoint_id, card, input_schema, timeout_at, correlation_id }` |
| `resume` | Turn 恢复执行 | `{ checkpoint_id }` |
| `done` | Turn 正常结束 | `{ stop_reason, stats }` |
| `error` | Turn 异常 | `{ code, message, recoverable }` |

### 4.2 客户端 → 服务端（HTTP）

#### 4.2.1 创建 Turn

```
POST /agent/turn
{
  "session_id": "...",                  // 可选；不传则新建
  "prompt": "帮我订明天北京到上海的机票",
  "skill_hint": "book-flight",          // 可选；不传则框架根据 trigger 推断
  "agent_name": "agent-bj",
  "model": "claude-sonnet-4-6",
  "metadata": { "user_id": "u123" }
}
```

响应：SSE 流，从 `session` 事件开始。

#### 4.2.2 恢复 Turn（核心）

```
POST /agent/turn/<turn_id>/resume
{
  "correlation_id": "ask_user_xyz123",  // 与 suspend 事件对齐
  "user_input": {                       // 类型由 input_schema 决定
    "origin": "PEK",
    "destination": "SHA",
    "depart_date": "2026-06-03"
  },
  "action_id": "submit"                 // 哪个按钮触发的；表单则填 "submit"
}
```

> **关键**：恢复请求**不能**直接传一个 "user message"，而是传**结构化 user_input**。这避免了"AI 让你选航班，用户回了一句话 '第二个'，框架怎么把第二个映射成 flightId"的歧义。

如果客户端是**纯聊天模式**（旧前端 / 旧 Skill），可以传：

```json
{
  "correlation_id": "ask_user_xyz123",
  "user_input": { "_text": "第二个" }    // 框架转成 { _text: "..." } 注入
}
```

AI 收到后自行 NLU 解析。

#### 4.2.3 其他

- `GET /agent/turn/<id>/events?after=<seq>`：补拉漏掉的事件
- `POST /agent/turn/<id>/heartbeat`：延长挂起超时（前端定时器每 60s 调一次）
- `POST /agent/turn/<id>/cancel`：取消

### 4.3 关键事件流

```
Server                                  Client
  │  POST /agent/turn                   │
  │ ◄──────────────────────────────────  │
  │                                     │
  │  event: session                     │
  │  event: text "好的，让我…"            │  ─►  <ChatStream/> 追加
  │  event: tool_use ask_user           │  ─►  <ChatStream/> 提示"AI 在等你"
  │  event: state S02                   │  ─►  <TurnState/> → suspended
  │  event: card OD_INPUT               │  ─►  <AUIRenderer/> 渲染表单
  │  event: suspend                     │  ─►  <TurnState/> 锁表单
  │  (stop streaming, hold turn)        │
  │                                     │
  │              user fills form, clicks  │
  │  POST /resume                       │
  │ ◄──────────────────────────────────  │
  │                                     │
  │  event: resume                      │  ─►  <TurnState/> → running
  │  event: tool_result ask_user        │  ─►  <ChatStream/> 标灰"已收到"
  │  event: tool_use query_flight_basic │  ─►  <ChatStream/> 调 MCP
  │  event: tool_result [...]           │
  │  event: card FLIGHT_LIST            │  ─►  <AUIRenderer/> 渲染航班列表
  │  event: suspend                     │
  │  ... (loop) ...                     │
  │  event: done                        │
  │                                     │
  ▼                                     ▼
```

### 4.4 卡片目录 v1

| `card_type` | 用途 | 关键字段 | 触发状态（Sxx） |
|---|---|---|---|
| `CHAT_FALLBACK` | 旧 Skill 降级，纯文本问 | `{ prompt }` | 任意 |
| `OD_INPUT` | 出发/返程城市+日期 | `fields: [origin, destination, depart_date, return_date?]` | S02 / S04 |
| `FLIGHT_LIST` | 航班列表可点选 | `flights[]: {flightId, flightNo, dep, arr, price, tags[]}` | S05 |
| `CABIN_LIST` | 舱位列表可点选 | `cabins[]: {cabId, name, price, policyCompliance, refundRules}` | S06 |
| `PASSENGER_FORM` | 乘机人录入/选择 | `passengers[]: {idType, idNo, name, mobile}` | S08 |
| `OAT_BINDING` | 出差单/成本中心绑定 | `tripApplications[]`, `costCenters[]`, `defaultContact{}` | S09 |
| `PRICE_VERIFY` | 价格/差标确认 | `totalPrice`, `currentPrice`, `originalPrice`, `priceDiff`, `policyOverrun` | S10 / S11 |
| `POLICY_DECISION` | 差标决策按钮 | `decisionButtons[]: {code, label, surcharge?, policyHint}` | S11 / F3 |
| `ORDER_CONFIRM` | 订单预览确认 | `orderSummary`, `submitPayload`, `riskHints[]` | S12 / S13 |
| `ORDER_SUCCESS` | 下单成功 | `orderId`, `orderNo`, `payUrl?`, `payDeadline?` | F1 |
| `CANNOT_ORDER` | 无法下单 | `reason`, `fallback`, `actions[]` | F2 |

> 每个卡片**至少**含 `card_id`（幂等键）、`schema_version`（兼容性）、`dismissible`（是否可关闭）、`analytics`（埋点）。

### 4.5 卡片 JSON Schema（节选 `POLICY_DECISION`）

```jsonc
{
  "$id": "auip.cards.policy_decision.v1",
  "type": "object",
  "required": ["card_type", "schema_version", "title", "decision_buttons"],
  "properties": {
    "card_type": { "const": "POLICY_DECISION" },
    "schema_version": { "const": "1.0" },
    "title": { "type": "string" },
    "body": { "type": "object" },
    "context": {
      "type": "object",
      "properties": {
        "current_price": { "type": "number" },
        "policy_limit": { "type": "number" },
        "surcharge": { "type": "number" },
        "policy_overrun": { "type": "boolean" }
      }
    },
    "decision_buttons": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["id", "code", "label"],
        "properties": {
          "id": { "type": "string" },
          "code": {
            "enum": [
              "PAY_SURCHARGE", "PAY_NOW", "CONTINUE_BOOKING",
              "CHOOSE_LOW_PRICE_ALTERNATIVE", "ABORT"
            ]
          },
          "label": { "type": "string" },
          "style": { "enum": ["primary", "secondary", "danger", "ghost"] },
          "surcharge": { "type": "number" },
          "policy_hint": { "type": "string" }
        }
      }
    }
  }
}
```

> **每个 card_type 在 `src/openagent/auip/schemas/` 下放一份 JSON Schema**，框架在 emit 前用 jsonschema 校验。

### 4.6 AUIP 与 A2UI / OpenAI Apps SDK 的取舍

| 维度 | A2UI（Google） | OpenAI Apps SDK | **本文 AUIP** |
|---|---|---|---|
| 渲染目标 | 通用宿主 | ChatGPT 内 | 自家 React 前端 |
| 协议粒度 | HTML 子集 | MCP Resources + UI | 纯 JSON，**业务领域化** |
| 状态归属 | 客户端 | 服务端 | **服务端**（checkpoints） |
| 表达力 | 中（HTML 限制） | 高 | 高（业务元数据多） |
| 学习曲线 | 中 | 高 | 低（已有 skill 上下文） |
| 跨引擎 | 设计中立 | ChatGPT only | **双 SDK 透明** |

> 不直接抄 A2UI 的 HTML 子集，因为**我们已经知道 UI 是 8 类卡片**（book-flight + 未来差旅/打车/报销场景），不需要"全图灵完备"。如果未来要做通用宿主，再升级到 A2UI 也不晚。

---

## 5. Skill 状态机扩展

### 5.1 把 `book-flight-skill.md` 编译成机器可读

新增 `src/openagent/auip/skill_compiler.py`：

```python
def compile_skill(md_path: Path) -> SkillManifest:
    """Parse book-flight-skill.md → SkillManifest.

    Source of truth remains the .md; the YAML is generated by LLM + reviewed by human.
    """
```

CI 流程：

1. `book-flight-skill.md` 是人类编辑源
2. PR 时跑 `skill_compiler.py --check` 校验：所有状态、工具白名单、卡片引用都齐
3. LLM 辅助把 prose 转成 `*.skill.yaml` 初稿（可选）

### 5.2 状态机运行时

`src/openagent/skill_runtime/state_guard.py`：

```python
class StateGuard:
    def __init__(self, manifest: SkillManifest, ctx: SkillContext):
        self._manifest = manifest
        self._ctx = ctx

    def can_call_tool(self, tool_name: str) -> tuple[bool, str]:
        """校验 AI 在当前 state 是否允许调 tool_name。"""
        state = self._manifest.states[self._ctx.current_state]
        if tool_name == "ask_user":
            return True, "ok"        # 框架级工具永远允许
        if tool_name not in state.allowed_tools:
            return False, f"state {state.id} 不允许 {tool_name}, 允许 {state.allowed_tools}"
        return True, "ok"

    def can_transition(self, new_state: str) -> bool:
        return new_state in self._manifest.transitions.get(self._ctx.current_state, set())
```

**两阶段校验**：

1. **Pre-call（快路径）**：AI 调 `query_flight_basic` → 框架查 `StateGuard.can_call_tool` → 拒绝/允许
2. **Post-call（语义路径）**：调成功返回后，AI 给出 `new_state`，框架查 `can_transition`；违反则写 ERROR 事件，**不强行改 state**，让 AI 自纠

> 这正是 book-flight-skill.md §3.3 「Stage ↔ Tool 双向校验」的机器化版本。

### 5.3 Skill Prompt 模板

框架自动拼装 system prompt：

```
<system>
[OpenAgent AUIP runtime]
- 你是 {agent_name}，使用模型 {model}
- 用户正在使用 skill: {skill.name} v{skill.version}
- 当前业务状态: {state.id} — {state.description}
- 允许的 MCP 工具: {state.allowed_tools}
- 当你需要向用户提问时，调用 ask_user 工具并提供 card_type

[Skill: book-flight v0.1]
{skill.prompt_template from book-flight-skill.md §0-§5}

[Card catalog]
- 你的可用 card_type 列表：{skill.ui.cards}
- 卡片 JSON Schema 在 {skill.ui.card_schemas_path}

[Conversation so far]
{messages}
</system>
```

**优点**：业务侧（book-flight）完全不感知 AUIP 存在，只要 prompt 写"想跟用户确认价格时调 ask_user"。

---

## 6. 后端改造详细设计

### 6.1 文件清单

| 新增文件 | 行数上限 | 职责 |
|---|---|---|
| `src/openagent/auip/__init__.py` | 30 | 协议常量 |
| `src/openagent/auip/events.py` | 200 | `TurnEvent` 类型 + `EventBus` |
| `src/openagent/auip/cards.py` | 200 | `Card` 模型 + JSON Schema 校验 |
| `src/openagent/auip/schemas/*.json` | – | 8 个卡片 JSON Schema |
| `src/openagent/auip/skill_compiler.py` | 200 | MD → manifest |
| `src/openagent/auip/prompt_builder.py` | 200 | 拼装 system prompt |
| `src/openagent/core/suspendable_scheduler.py` | 300 | `SuspendableScheduler` |
| `src/openagent/skill_runtime/state_guard.py` | 200 | 状态机校验 |
| `src/openagent/skill_runtime/manifest.py` | 200 | `SkillManifest` dataclass |
| `src/openagent/store/turn_store.py` | 300 | 持久化 Turn / Checkpoint |
| `src/openagent/store/skill_context_store.py` | 200 | 业务 ctx（Redis） |
| `src/openagent/api/turn_routes.py` | 300 | `/agent/turn/*` 路由 |
| `tests/test_auip_*.py` | – | 协议 + 状态机单测 |
| `tests/e2e/test_book_flight_hitl.py` | – | 端到端剧本 |

> 总增量 ~2500 行，远小于一个独立的"工作流引擎"项目。

### 6.2 `SuspendableScheduler` 核心

```python
class SuspendableScheduler:
    def __init__(
        self,
        bridge: AgentBridge,
        skill_registry: SkillRegistry,
        turn_store: TurnStore,
        ctx_store: SkillContextStore,
        state_guard_factory: Callable[[SkillManifest, SkillContext], StateGuard],
    ):
        ...

    async def run_turn(
        self, prompt: str, *, session_id: str | None = None,
        skill_hint: str | None = None, **kwargs
    ) -> AsyncIterator[TurnEvent]:
        """
        创建 Turn → 加载 skill → 拼 prompt → 调 bridge → yield events
        """
        turn = await self._turn_store.create(prompt, skill_hint=skill_hint)
        manifest = self._skill_registry.match(skill_hint or prompt)
        ctx = await self._ctx_store.load_or_init(turn)

        async for event in self._drive_turn(turn, manifest, ctx, prompt):
            yield event

    async def resume(
        self, turn_id: str, *, correlation_id: str,
        user_input: dict, action_id: str | None = None
    ) -> AsyncIterator[TurnEvent]:
        """从最近 SuspendPoint 恢复。"""
        turn = await self._turn_store.get(turn_id)
        manifest = self._skill_registry.get(turn.skill_name, turn.skill_version)
        ctx = await self._ctx_store.load(turn)

        # 把 user_input 包装成 tool_result，注入消息流
        tool_use_id = correlation_id
        resume_msg = ChatMessage(
            role="user",
            content="",                               # 内容在 tool_result 里
            tool_call_id=tool_use_id,
            tool_name="ask_user",
            metadata={"action_id": action_id, "user_input": user_input},
        )
        await self._append_message(turn, resume_msg)
        yield TurnEvent.resume(checkpoint_id=turn.last_checkpoint_id)

        # 从断点继续
        async for event in self._drive_turn(turn, manifest, ctx, resume=True):
            yield event
```

### 6.3 `_drive_turn` 内部

```python
async def _drive_turn(self, turn, manifest, ctx, *, prompt=None, resume=False):
    # 1. State machine hook: state → system_prompt
    state = manifest.states[ctx.current_state]
    system_prompt = self._prompt_builder.build(
        manifest, ctx, self._bridge.get_messages(turn.session_id)
    )

    # 2. Inject ask_user synthetic tool
    tools = self._collect_tools(manifest, ctx) + [ASK_USER_TOOL_DEF]

    # 3. Checkpoint before driving
    checkpoint = await self._turn_store.checkpoint(turn, ctx)

    # 4. Stream events from provider
    iterator = await self._bridge.chat(
        session_id=turn.session_id,
        messages=self._build_messages(prompt, resume, ctx),
        system_prompt=system_prompt,
        tools=tools,
        stream=True,
    )

    # 5. Process events
    open_ask_user = None
    async for raw in iterator:
        event = self._event_mapper.map(raw)
        if event.type == "tool_use" and event.data["name"] == "ask_user":
            open_ask_user = event
            continue                           # 不立即 yield, 等 card 来
        if event.type == "card":
            # AI 在 tool_use 后又吐了 card 事件（在我们这个映射层）
            open_ask_user = None
        yield event

        if open_ask_user is not None and event.type == "tool_result":
            # ask_user 的 tool_result 是 synthetic, AI 已经知道怎么继续
            open_ask_user = None

    # 6. AI 决定挂起: 调 ask_user, 不再吐 card
    if open_ask_user is not None:
        # 验证 StateGuard 允许 ask_user
        guard = self._state_guard_factory(manifest, ctx)
        ok, reason = guard.can_call_tool("ask_user")
        if not ok:
            yield TurnEvent.error(code="STATE_VIOLATION", message=reason)
            return

        # 推 card
        card = Card.from_tool_input(open_ask_user.data["input"])
        yield TurnEvent.card(card_id=card.card_id, card=card)
        yield TurnEvent.suspend(
            checkpoint_id=checkpoint.id,
            card=card,
            correlation_id=open_ask_user.id,
            timeout_at=state.timeout,
        )
        # 不再 stream, 等 resume
```

### 6.4 双 SDK 的 event 映射差异

**OpenCode**（HTTP，SSE 推 part）：

```
part: tool_use name=ask_user → 我们捕获
```

**Claude Code**（本地 CLI，JSON line）：

```
{"type":"assistant","message":{"content":[{"type":"tool_use","name":"ask_user",...}]}}
                  ↑ 同样捕获
```

两者都通过 `providers/agent_bridge.py` → 各 adapter → 统一归一化为 `TurnEvent`。**adapter 唯一新增的负担**：识别 `ask_user` 这个工具名，标记为 `interrupt_aware=True`。

### 6.5 持久化模型

#### `turn_store.py`（Postgres）

```sql
CREATE TABLE turn (
    turn_id        UUID PRIMARY KEY,
    session_id     UUID NOT NULL,
    skill_name     TEXT NOT NULL,
    skill_version  TEXT NOT NULL,
    state          TEXT NOT NULL,
    status         TEXT NOT NULL,         -- running | suspended | done | error | cancelled
    created_at     TIMESTAMPTZ DEFAULT now(),
    updated_at     TIMESTAMPTZ DEFAULT now(),
    metadata       JSONB
);
CREATE INDEX idx_turn_session ON turn(session_id, created_at DESC);
CREATE INDEX idx_turn_status  ON turn(status) WHERE status IN ('running','suspended');

CREATE TABLE turn_event (
    turn_id        UUID NOT NULL,
    seq            BIGINT NOT NULL,
    type           TEXT NOT NULL,
    data           JSONB NOT NULL,
    ts             TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (turn_id, seq)
);

CREATE TABLE turn_checkpoint (
    checkpoint_id  UUID PRIMARY KEY,
    turn_id        UUID NOT NULL,
    state          TEXT NOT NULL,
    ctx            JSONB NOT NULL,         -- SkillContext 序列化
    open_tool_calls JSONB NOT NULL,
    created_at     TIMESTAMPTZ DEFAULT now()
);
```

#### `skill_context_store.py`（Redis）

```
booking:ctx:{session_id}   →  JSON 字符串, TTL 7d
```

跟 book-flight-skill.md §3.1 R-03 完全对齐。

### 6.6 双 SDK 透明性证明

> 为什么不需要在 OpenCode / Claude Code 两边各写一套？

| 关注点 | OpenCode | Claude Code | **统一做法** |
|---|---|---|---|
| 工具调用格式 | `{type: tool_use, name, input}` | `{type: tool_use, id, name, input}` | adapter normalize |
| 流式事件 | SSE | stdout JSONL | adapter normalize |
| 中断能力 | 客户端断开 | `claude --abort` | 框架侧 `bridge.abort()` |
| 历史回放 | 重新发 `messages[]` | 同上 | 框架统一控制 `messages[]` |
| ask_user 工具 | 同其他 tool 一样注册 | 同上 | 框架注册为 synthetic tool |

**唯一差异**：`claude-agent-sdk` 走本地 CLI，部分事件（reasoning）需要从 `--verbose` 输出解析。框架在 `claude_code_adapter.py` 已经做了 event mapping，AUIP 只需复用。

---

## 7. 前端架构详细设计

### 7.1 目录结构

```
frontend/src/
├── components/
│   ├── chat/
│   │   ├── ChatStream.tsx           # 文本流
│   │   ├── TurnStateBar.tsx         # 显示当前 turn 状态
│   │   └── MessageItem.tsx
│   ├── aui/                          # ⭐ 新增
│   │   ├── AUIRenderer.tsx          # 递归渲染入口
│   │   ├── cards/
│   │   │   ├── FormCard.tsx
│   │   │   ├── FlightListCard.tsx
│   │   │   ├── CabinListCard.tsx
│   │   │   ├── PassengerFormCard.tsx
│   │   │   ├── OATBindingCard.tsx
│   │   │   ├── PriceVerifyCard.tsx
│   │   │   ├── PolicyDecisionCard.tsx
│   │   │   ├── OrderConfirmCard.tsx
│   │   │   ├── OrderSuccessCard.tsx
│   │   │   ├── CannotOrderCard.tsx
│   │   │   └── ChatFallbackCard.tsx
│   │   ├── fields/                  # 表单域类型
│   │   │   ├── CityPickerField.tsx
│   │   │   ├── DateField.tsx
│   │   │   ├── PassengerField.tsx
│   │   │   └── ...
│   │   └── actions/
│   │       └── ActionButton.tsx
│   └── ...
├── services/
│   ├── auiClient.ts                  # SSE 客户端
│   └── turnService.ts
├── store/
│   └── turnStore.ts                  # Zustand
├── types/
│   ├── auip.ts                       # ⭐ 新增（与后端同步生成）
│   └── ...
└── hooks/
    ├── useTurn.ts                    # ⭐ 新增
    └── useAUICard.ts
```

### 7.2 `<AUIRenderer/>` 核心

```tsx
export function AUIRenderer({ card, onSubmit, suspended }: {
    card: Card;
    onSubmit: (input: any, actionId: string) => void;
    suspended: boolean;
}) {
    const CardComp = CARD_CATALOG[card.card_type];
    if (!CardComp) {
        return <ErrorCard message={`Unknown card_type: ${card.card_type}`} />;
    }
    return (
        <CardShell card={card} suspended={suspended}>
            <CardComp card={card} onSubmit={onSubmit} disabled={suspended} />
        </CardShell>
    );
}

const CARD_CATALOG: Record<string, React.FC<any>> = {
    CHAT_FALLBACK: ChatFallbackCard,
    OD_INPUT: FormCard,                  // 同一 FormCard 渲染不同 field 组合
    FLIGHT_LIST: FlightListCard,
    CABIN_LIST: CabinListCard,
    PASSENGER_FORM: PassengerFormCard,
    OAT_BINDING: OATBindingCard,
    PRICE_VERIFY: PriceVerifyCard,
    POLICY_DECISION: PolicyDecisionCard,
    ORDER_CONFIRM: OrderConfirmCard,
    ORDER_SUCCESS: OrderSuccessCard,
    CANNOT_ORDER: CannotOrderCard,
};
```

> **关键设计**：卡片**仅消费 props，不发起任何 HTTP**。所有"提交"都通过 `onSubmit(input, actionId)` 冒泡到 `useTurn` hook 统一处理。

### 7.3 `useTurn` 状态机

```tsx
type TurnStatus = 'idle' | 'running' | 'suspended' | 'resuming' | 'done' | 'error' | 'cancelled';

export function useTurn(turnId: string | null) {
    const [status, setStatus] = useState<TurnStatus>('idle');
    const [events, setEvents] = useState<TurnEvent[]>([]);
    const [pendingCard, setPendingCard] = useState<Card | null>(null);
    const [correlationId, setCorrelationId] = useState<string | null>(null);

    const sseClient = useSSEClient();

    useEffect(() => {
        if (!turnId) return;
        const stream = sseClient.connect(`/agent/turn/${turnId}/events`);
        stream.on('state', (e) => setStatus(e.data.status));
        stream.on('text', (e) => setEvents(es => appendText(es, e)));
        stream.on('card', (e) => {
            setPendingCard(e.data.card);
            setCorrelationId(e.data.correlation_id);
        });
        stream.on('suspend', () => setStatus('suspended'));
        stream.on('resume', () => { setStatus('running'); setPendingCard(null); });
        stream.on('done',  () => setStatus('done'));
        stream.on('error', (e) => setStatus('error'));
        return () => stream.close();
    }, [turnId]);

    const submit = useCallback(async (input: any, actionId: string) => {
        if (!turnId || !correlationId) return;
        setStatus('resuming');
        const resp = await fetch(`/agent/turn/${turnId}/resume`, {
            method: 'POST',
            body: JSON.stringify({ correlation_id: correlationId, user_input: input, action_id: actionId }),
        });
        // 服务端会再发 SSE, hook 已经订阅
    }, [turnId, correlationId]);

    return { status, events, pendingCard, submit };
}
```

### 7.4 乐观更新与回滚

`submit` 时不立即清空卡片，先把卡片标记为 `submitting`，等服务端发回 `tool_result` 事件才移除。这样：

- 网络慢时用户看到"提交中…"状态
- 服务端报错时卡片回退到可编辑态
- 不需要复杂的客户端状态机

### 7.5 心跳

```tsx
useEffect(() => {
    if (status !== 'suspended') return;
    const t = setInterval(() => {
        fetch(`/agent/turn/${turnId}/heartbeat`, { method: 'POST' });
    }, 60_000);
    return () => clearInterval(t);
}, [status, turnId]);
```

> 框架默认挂起超时 5min（S11/F3 是 10min），前端每 60s 心跳延长；用户关闭页面超时后下次进入会看到"会话已过期"提示。

### 7.6 客户端 type 与服务端同步

`frontend/src/types/auip.ts` 用 `json-schema-to-typescript` 从 `src/openagent/auip/schemas/*.json` 生成，CI 校验一致性。

---

## 8. 数据流：典型剧本

### 8.1 Happy Path（订明天北京到上海）

```
T+0s     用户: "帮我订明天北京到上海的机票"
T+0.1s   POST /agent/turn
         ↓
         SuspendableScheduler.run_turn
         → 加载 book-flight skill v0.1
         → 拼 system prompt
         → 注入 MCP tools + ask_user
         → bridge.chat(stream=True)
         ↓
T+0.5s   event: session {turn_id}
T+0.6s   event: state S01
T+0.7s   event: text "好的, 让我帮您查询北京到上海明天的航班"
T+1.2s   event: tool_use query_flight_basic
T+1.8s   event: tool_result {flights: [...12 条...]}
T+2.0s   event: state S05
T+2.1s   event: card FLIGHT_LIST
T+2.2s   event: suspend {correlation_id, timeout: 5m}
         ↓ (前端渲染航班列表, 等用户点)
T+45s    用户: 点击 "CA1501 09:00 出发"
T+45s    POST /agent/turn/abc/resume
         { correlation_id, user_input: {flightId: "CA1501-20260603-0900"}, action_id: "select" }
         ↓
T+45.1s  event: resume
T+45.2s  event: tool_result ask_user {ack: "selected"}
T+45.3s  event: tool_use choose_flight
T+46s    event: tool_use get_cabins
T+47s    event: card CABIN_LIST
T+47.1s  event: suspend
         ↓
T+90s    用户: 选经济舱, 张三
T+90s    POST /resume
         ↓
T+95s    event: card PASSENGER_FORM  (询问手机号/证件)
T+95.1s  event: suspend
         ↓
T+120s   用户: 提交手机号
T+120s   POST /resume
         ↓
T+125s   event: card OAT_BINDING
T+125.1s event: suspend
         ↓
T+150s   用户: 选 OAT-2025-001 + 成本中心 001
T+150s   POST /resume
         ↓
T+155s   event: tool_use validate_booking_info
T+158s   event: tool_result {priceChanged: false, policyOverrun: false}
T+159s   event: state S10
T+160s   event: card PRICE_VERIFY (展示 totalPrice)
T+160.1s event: suspend
         ↓
T+180s   用户: 确认下单
T+180s   POST /resume
         ↓
T+185s   event: tool_use build_order_preview
T+187s   event: card ORDER_CONFIRM
T+187.1s event: suspend
         ↓
T+210s   用户: 点 "确认下单"
T+210s   POST /resume {action_id: "submit"}
         ↓
T+215s   event: tool_use submit_order
T+218s   event: tool_use confirm_order
T+220s   event: card ORDER_SUCCESS
T+220.1s event: done
```

> 6 次挂起 / 恢复, 总耗时 220s, 但**实际只用了 ~25s 算力**；其余 195s 在等用户。每次挂起都有 checkpoint, 用户关掉浏览器再回来能续上。

### 8.2 Crash Recovery

```
T+150s   框架正在 build_order_preview
         突然 Sanic OOM, 进程挂掉
T+200s   用户回来, GET /agent/turn/abc
         → 200 { status: "suspended", last_checkpoint: "ckpt-7", state: "S12" }
T+201s   前端自动 POST /resume { user_input: {resume: true} }
         → 框架读 ckpt-7 重放 messages
         → 从 "S12 build_order_preview" 之后继续
T+205s   event: card ORDER_CONFIRM  ← 用户继续走流程
```

---

## 9. 错误处理与边界

### 9.1 错误分类

| 类别 | 示例 | 处理 |
|---|---|---|
| `STATE_VIOLATION` | S08 调 `submit_order` | 拒绝 + ERROR 事件 + 提示 AI 回到 S08 |
| `CARD_SCHEMA_INVALID` | AI 输出的 card 不符合 JSON Schema | 拒绝 card, 推 `CHAT_FALLBACK` 让 AI 重新组织 |
| `USER_INPUT_INVALID` | 用户提交缺字段 | 前端校验, 不发请求；发请求后服务端再校验兜底 |
| `MCP_TIMEOUT` | query_flight_basic 超时 | 框架重试 3 次, 失败 → ERROR + 兜底话术 |
| `SUSPEND_TIMEOUT` | 用户 5min 不响应 | 推 `CANNOT_ORDER` + 结束 Turn |
| `SDK_DISCONNECTED` | OpenCode/ClaudeCode 挂掉 | checkpoint 保留, 提示用户重试；后端切换 provider |
| `SKILL_VERSION_MISMATCH` | resume 时 skill 升级了 | 拒绝 resume, 让用户重开 Turn (or LLM 适配) |

### 9.2 死循环防护

- 同一 `(turn_id, state)` 最多连续挂起 3 次；超过则强制转 `F2 CANNOT_ORDER`
- 工具调用总次数上限 50（按 turn 累计）
- 单 Turn 总时长上限 1h（管理员可配）

### 9.3 并发安全

- `turn_id` 上加 `SELECT ... FOR UPDATE`，避免两个 resume 并发
- 状态转换用乐观锁：`UPDATE turn SET state=? WHERE turn_id=? AND state=?` 失败则 ERROR
- 卡片 dedup：`card_id` 是 UUID, 重复事件去重

### 9.4 隐私与脱敏

- `PRICE_VERIFY` 卡片**不展示**完整价格给前端日志
- `PASSENGER_FORM` 证件号前端显示 `110***********0023`
- 框架在 SSE 出口对 `idNo` / `phone` 做 PII 脱敏（开关）

---

## 10. 安全与权限

| 风险 | 缓解 |
|---|---|
| 用户在表单里塞 SQL/XSS | 卡片 JSON Schema 强类型 + 前端 react 自动转义 |
| 任意调 MCP 工具 | StateGuard 强校验 + MCP Gateway RBAC |
| 跨租户泄漏 Turn | Turn 持久化时带 `user_id`, 路由层 `tenant_id` 校验 |
| 重放攻击 | 每次 ask_user 生成新 `correlation_id`, 旧 id 服务端拒绝 |
| 超长 turn 占资源 | TTL + 心跳 + 上限 |

---

## 11. 测试策略

### 11.1 单元

- `tests/test_auip_events.py`：event envelope 序列化、seq 严格递增
- `tests/test_auip_cards.py`：每个 card_type JSON Schema 校验（合法/非法用例）
- `tests/test_skill_compiler.py`：book-flight-skill.md → manifest 双向一致性
- `tests/test_state_guard.py`：13 状态 × 12 工具白名单矩阵
- `tests/test_turn_store.py`：checkpoint 原子写入、并发恢复

### 11.2 集成

- `tests/integration/test_suspend_resume.py`：mock AI，模拟"先调 ask_user 再发 card"，验证 SUSPEND 事件 + checkpoint 落库
- `tests/integration/test_skill_runtime.py`：跑完整剧本 A（Happy Path），不实际调 MCP（mock），验证 6 次挂起点

### 11.3 端到端

- `tests/e2e/test_book_flight_hitl.py`：用真实 Claude Code + mock MCP server + Playwright 跑剧本 A-E
  - A: 单程经济舱 happy path
  - B: 往返 RECOMMENDED
  - C: 核价变价 → 用户决策
  - D: 代订权限缺失 → F2
  - E: 差标超标 → F3 → 决策 → F1

### 11.4 故障注入

- 随机 kill Sanic, 验证 checkpoint 恢复
- 网络断 5s, 验证 SSE 重连 + `?after=<seq>` 补拉
- 用户连发 10 次 submit, 验证幂等

---

## 12. 实施路线图

> 总工期 ~4-5 周，1 个后端 + 1 个前端 + 0.5 个测试。

### Phase 1：协议地基（5d）

- [ ] `auip/events.py` + `auip/cards.py` + 8 个 JSON Schema
- [ ] `store/turn_store.py` (Postgres DDL + 增删改查)
- [ ] `store/skill_context_store.py` (Redis)
- [ ] `tests/test_auip_*.py` 单测覆盖

### Phase 2：Skill Runtime（5d）

- [ ] `skill_runtime/manifest.py` + `state_guard.py`
- [ ] `skill_compiler.py` 把 `book-flight-skill.md` 编译成 `book-flight.skill.yaml`
- [ ] `prompt_builder.py` 拼 system prompt
- [ ] `tests/test_state_guard.py` 矩阵校验

### Phase 3：SuspendableScheduler（5d）

- [ ] `core/suspendable_scheduler.py`
- [ ] providers adapter 增加 `ask_user` 拦截
- [ ] `api/turn_routes.py` 5 个端点
- [ ] `tests/integration/test_suspend_resume.py`

### Phase 4：前端 AUIRenderer（5d）

- [ ] `types/auip.ts` 自动生成
- [ ] `<AUIRenderer/>` + 8 个卡片组件
- [ ] `useTurn` hook + SSE 客户端
- [ ] 接入现有 `<ChatStream/>`

### Phase 5：book-flight 剧本 E2E（3d）

- [ ] 跑剧本 A-E，录制视频
- [ ] 性能基准（6 次挂起的 P95 < 5s 首字节）

### Phase 6：加固（3d）

- [ ] 心跳 + 超时 + 重连
- [ ] 错误码 + 兜底话术
- [ ] 埋点 + 监控（Prometheus）

---

## 13. 风险与未决问题

| 风险 | 影响 | 缓解 |
|---|---|---|
| **AI 不按规范调 ask_user** | 整个协议失效 | system prompt 强约束 + 失败回退到 CHAT_FALLBACK |
| **Claude Code SDK 不支持精细中断** | resume 时丢上下文 | 每次 checkpoint 都把 messages 落库, resume 时 replay |
| **OpenCode SSE part 顺序不稳定** | 事件乱序 | seq 由框架侧分配, 不信 provider 顺序 |
| **card schema 频繁变化** | 前端要常改 | schema_version 强校验, 旧版前端兼容新版后端（只渲染支持的字段） |
| **多人协作编辑同一 turn** | 状态冲突 | 暂不支持, 同一 session 同时刻只允许一个 active turn |
| **PII 落库合规** | 隐私 | 加密字段 + 审计日志 + TTL 7d |
| **book-flight 的 MCP 还没接入** | Phase 5 跑不通 | 优先推动 MCP 接入, 或先用 mock server 跑 E2E |

### 未决问题

1. **多轮 Turn 内是否允许 AI 切换 Skill？**（订完机票再叫车）当前设计不允许，需 Phase 7 扩展。
2. **卡片能否被嵌入到普通消息气泡里？**（如 "价格已变动" + 决策按钮）。当前卡片总是占整行，可扩展为 inline 模式。
3. **是否需要服务端渲染兜底 HTML？**（邮件场景）暂不做，未来可加。
4. **审计回放**：是否把 Turn 完整 replay 给运营查？需要 AUI 事件 + MCP tool_result 都落库。

---

## 14. 附录 A：关键类型汇总

### 14.1 后端

```python
# auip/events.py
class TurnEventType(str, Enum):
    SESSION = "session"
    TEXT = "text"
    REASONING = "reasoning"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    CARD = "card"
    STATE = "state"
    SUSPEND = "suspend"
    RESUME = "resume"
    DONE = "done"
    ERROR = "error"

@dataclass
class TurnEvent:
    seq: int
    turn_id: str
    type: TurnEventType
    data: dict
    ts: float

# auip/cards.py
class CardType(str, Enum):
    CHAT_FALLBACK = "CHAT_FALLBACK"
    OD_INPUT = "OD_INPUT"
    FLIGHT_LIST = "FLIGHT_LIST"
    CABIN_LIST = "CABIN_LIST"
    PASSENGER_FORM = "PASSENGER_FORM"
    OAT_BINDING = "OAT_BINDING"
    PRICE_VERIFY = "PRICE_VERIFY"
    POLICY_DECISION = "POLICY_DECISION"
    ORDER_CONFIRM = "ORDER_CONFIRM"
    ORDER_SUCCESS = "ORDER_SUCCESS"
    CANNOT_ORDER = "CANNOT_ORDER"

@dataclass
class Card:
    card_id: str
    card_type: CardType
    schema_version: str
    title: str
    body: dict
    fields: list[Field] | None = None
    options: list[Option] | None = None
    actions: list[Action] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    dismissible: bool = False

# core/suspendable_scheduler.py
@dataclass
class Turn:
    turn_id: str
    session_id: str
    skill_name: str
    skill_version: str
    status: Literal["running", "suspended", "done", "error", "cancelled"]
    state: str
    last_checkpoint_id: str | None
    created_at: datetime
    metadata: dict
```

### 14.2 前端

```ts
// types/auip.ts（自动生成）
export type CardType =
  | 'CHAT_FALLBACK' | 'OD_INPUT' | 'FLIGHT_LIST' | 'CABIN_LIST'
  | 'PASSENGER_FORM' | 'OAT_BINDING' | 'PRICE_VERIFY'
  | 'POLICY_DECISION' | 'ORDER_CONFIRM' | 'ORDER_SUCCESS' | 'CANNOT_ORDER';

export interface TurnEvent<T = unknown> {
    seq: number;
    turn_id: string;
    type: 'session' | 'text' | 'reasoning' | 'tool_use' | 'tool_result'
        | 'card' | 'state' | 'suspend' | 'resume' | 'done' | 'error';
    data: T;
    ts: number;
}

export interface Card {
    card_id: string;
    card_type: CardType;
    schema_version: string;
    title: string;
    body: Record<string, unknown>;
    fields?: Field[];
    options?: Option[];
    actions: Action[];
    metadata: Record<string, unknown>;
    dismissible: boolean;
}
```

---

## 15. 附录 B：与现有 OpenCode / Claude Code SDK 适配点的最小改动

| 适配器 | 改动 | 原因 |
|---|---|---|
| `providers/base.py` `AgentProvider` | 新增 `interrupt_aware` 参数到 `chat()`；新增 `emit_event()` 让 adapter 把 `ask_user` 标记为 synthetic | 让上层能识别并拦截 |
| `providers/opencode_adapter.py` | 把 OpenCode `tool_use name=ask_user` 转换为 `TurnEvent` 而非直接 yield 给前端 | 框架拦截 |
| `providers/claude_code_adapter.py` | 同上，针对 CLI 的 JSONL | 框架拦截 |
| `providers/agent_bridge.py` | 注册 `ask_user` synthetic tool 到 `mcp_registry` 时跳过 `to_claude_code_format` 的某些检查 | tool schema 注入 |

> **不改任何 SDK 内部**。我们只在外层 adapter 加 hook。

---

## 16. 附录 C：术语对照

| 术语 | 含义 | 类比 |
|---|---|---|
| Turn | 一次"用户问 → AI 答"的总跨度，可跨多次挂起 | Temporal Workflow |
| SuspendPoint | Turn 暂停等待用户 | Temporal Activity.await |
| Checkpoint | 挂起前的全量状态 | Temporal Event History |
| Card | 声明式 UI 描述 | A2UI / OpenAI Apps SDK UIResource |
| StateGuard | 状态机守卫 | Guard in statechart |
| Skill Manifest | Skill 的机器可读契约 | OpenAPI spec |
| AUIP | 本协议 | gRPC / GraphQL |
| ask_user tool | Agent 表达"我要问用户"的工具 | (无标准对应) |

---

## 17. 总结

本文给出的不是"加一个 chat 弹窗"那么简单，而是一套**完整的可中断 Agent 执行模型**：

1. **协议层**：AUIP 把"AI 问用户"变成有 schema、有 sequence、有 checkpoint 的一等公民事件
2. **状态机**：把 `book-flight-skill.md` 的 13 状态编译成机器可读的 manifest，框架 + Skill 双重校验
3. **调度器**：`SuspendableScheduler` 在不破坏 OpenCode / Claude Code 适配的前提下，新增挂起 / 恢复能力
4. **前端**：`<AUIRenderer/>` + 8 个业务卡片，schema-driven，新场景只需写新 schema
5. **持久化**：turn + checkpoint + skill_ctx 三层存储，crash-safe，支持 7 天恢复
6. **可演进**：未来差旅 / 报销 / 叫车场景复用同一套 AUIP，只需要写新 Skill + 新卡片 schema

> **下一步建议**：先把本文 12.1（Phase 1 协议地基）实现，落地后再回头校验本设计是否需要调整。**不要**一口气把全部 2500 行写完再 review —— 协议层和状态机层都值得在第 1 周结束时 review 一次。
