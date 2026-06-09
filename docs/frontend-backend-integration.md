# 前端 ↔ 后端联调说明

> 本次只动前端 (`frontend/src/**`)，后端 `src/openagent/**` 完全保留。
> 验证: `pnpm exec tsc --noEmit` / `pnpm exec eslint .` / `pnpm exec vite build` 均通过。

## 1. 关键变更 (本次)

按 `docs/api/scenarios.md` §2.3 升级 SSE 事件协议 (12 种 event type)，并接入 AUIP 卡片与 HITL 挂起/恢复。

| 类别 | 新增 / 变更 |
|---|---|
| **路由头** | `POST /agent/chat/stream` 增加 `X-Scenario` header 与 `body.scenario` 字段 |
| **MCP 凭证** | 请求自动加 `X-MCP-Token: <VITE_MCP_TOKEN>` 头 (per-tenant) |
| **SSE 事件** | 新增 `scenario` / `card` / `state` / `suspend` / `resume` 5 种 (共 12 种) |
| **工具事件** | `tool_use` / `tool_result` payload 从 `tool_name/tool_call_id` 改为 `name/id` (向后兼容旧字段) |
| **AUIP 卡片** | `card` 事件携带 `card_type` + `card` + `correlation_id`；前端按 11 种 catalog 渲染 |
| **HITL** | 后端 `suspend` 事件 → 前端 `isSuspended=true`；用户点提交 → `POST /agent/turn/{turn_id}/resume` 携带 `{correlation_id, user_input, action_id}` |
| **心跳** | 挂起期间前端每 60s 调 `POST /agent/turn/{turn_id}/heartbeat` 防超时 |
| **Turn 取消** | 暴露 `cancelTurn()`，调 `POST /agent/turn/{turn_id}/cancel` |

## 2. 后端契约 (来源 `src/openagent/api/controllers/chat_controller.py` + `docs/api/scenarios.md`)

### 2.1 路由优先级 (ScenarioMiddleware)

```
0  URL path  /agent/scenarios/{name}/chat         (前端未使用)
1  X-Scenario header                              (前端发送)
2  body.scenario                                  (前端同时发送, 兜底)
3  trigger_keywords
4  intent classifier
5  settings.default_scenario
```

### 2.2 SSE 事件 payload (12 种)

| type | 关键 payload | 前端处理 |
|---|---|---|
| `scenario` | `{name, version, matched_by, orchestration}` | 顶部条幅 + 气泡内的 scenario pill |
| `session` | `{session_id}` | 持久化到 `localStorage` |
| `text` | `{content}` | 增量追加到 assistant 气泡 |
| `reasoning` | `{content}` | 折叠区 (Claude 才有) |
| `tool_use` | `{id, name, input}` | 折叠区 (向后兼容 `tool_name`) |
| `tool_result` | `{id, name, output, is_error}` | 折叠区 |
| `card` | `{card_id, card_type, card, correlation_id}` | 渲染 AUIP 卡片 (按 `card_type` 分发) |
| `state` | `{state, note}` | 气泡 + 顶部业务状态 pill |
| `suspend` | `{checkpoint_id, card, correlation_id, input_schema, timeout_at}` | 标记 `isSuspended=true` + 启动心跳 |
| `resume` | `{checkpoint_id}` | 清空 pending card |
| `done` | `{stop_reason}` | 流结束 |
| `error` | `{message, code}` | 错误提示 |

### 2.3 Turn 端点 (HITL)

```
GET   /agent/turn/{turn_id}                  查询状态
GET   /agent/turn/{turn_id}/events?after=N   SSE 补拉
POST  /agent/turn/{turn_id}/resume           提交用户输入 (SSE)
POST  /agent/turn/{turn_id}/heartbeat        延长挂起超时
POST  /agent/turn/{turn_id}/cancel           取消
```

## 3. 前端新增 / 变更

### 3.1 目录结构

```
frontend/src
├── config/
│   └── index.ts                          # 读取 VITE_API_BASE_URL + VITE_MCP_TOKEN
├── services/
│   ├── chat.ts                           # /agent/chat + /agent/chat/stream (scenario + X-MCP-Token)
│   ├── turn.ts                           # /agent/turn/* 5 端点 (含 SSE resume 流)
│   ├── scenarios.ts                      # /agent/scenarios 列表 / 详情
│   ├── sse.ts                            # ReadableStream 解析 (12 事件)
│   ├── session.ts / skills.ts / tools.ts / pool.ts / system.ts
│   ├── http.ts                           # fetch 封装 + ApiError
│   └── index.ts                          # barrel
├── hooks/
│   ├── useChatStream.ts                  # 核心: 12 事件 + 挂起/恢复 + 心跳
│   ├── useChatSession.ts                 # sessionId 持久化
│   ├── useHealth.ts                      # /health + /ready 轮询
│   ├── useScenarios.ts                   # scenario 列表 (selector 用)
│   └── useSkills.ts / useTools.ts / usePool.ts
├── types/
│   ├── domain.ts                         # 12 SSE 事件 + Card + Turn + Scenario
│   ├── chat.ts / flight.ts / order.ts / api.ts
│   └── index.ts
└── components/
    ├── chat/                             # ChatPage / MessageList / ChatBubble / ChatInput / WelcomeMessage
    ├── layout/                           # MainLayout / Sidebar (含 scenario selector) / SettingsPanel
    ├── flight/                           # SearchPage
    ├── order/                            # OrdersPage / OrderCard / OrderDetail / Tabs / RulesPage
    ├── common/                           # Button / Card / Input / Modal / Empty / Skeleton / Badge
    └── aui/                              # ⭐ 新增
        ├── AUIRenderer.tsx               # 卡片分发器
        ├── CardShell.tsx                 # 公共卡片外壳
        ├── CardShell.css
        └── cards/
            ├── FormCard.tsx              # OD_INPUT / PASSENGER_FORM / OAT_BINDING
            ├── SelectionListCard.tsx     # FLIGHT_LIST / CABIN_LIST
            ├── PriceVerifyCard.tsx       # PRICE_VERIFY
            ├── PolicyDecisionCard.tsx    # POLICY_DECISION
            ├── OrderConfirmCard.tsx      # ORDER_CONFIRM
            ├── OrderSuccessCard.tsx      # ORDER_SUCCESS
            ├── CannotOrderCard.tsx       # CANNOT_ORDER
            └── ChatFallbackCard.tsx      # CHAT_FALLBACK (旧 Skill 降级)
```

### 3.2 Scenario + MCP Token 配置

`frontend/.env`:

```
VITE_API_BASE_URL=                              # 留空 → 走 /api 代理
VITE_MCP_TOKEN=a6lo2skom9tb8cfa9bpn             # 透传为 X-MCP-Token
```

`vite.config.ts` (已存在) 代理 `/api/*` → `http://localhost:18000`。

### 3.3 12 SSE 事件分发 (`useChatStream`)

状态机：

```
idle ──send()──▶ sending ──event:session──▶ streaming
                                          ├─ event:text ──────────────▶ streaming (追加 content)
                                          ├─ event:reasoning ──────────▶ streaming
                                          ├─ event:tool_use/result ────▶ streaming
                                          ├─ event:scenario ───────────▶ streaming (顶部条幅)
                                          ├─ event:card ────────────────▶ streaming (渲染 AUIP)
                                          ├─ event:state ───────────────▶ streaming
                                          ├─ event:suspend ─────────────▶ suspended (启动心跳)
                                          ├─ event:resume ──────────────▶ resuming
                                          ├─ event:done / abort ────────▶ idle
                                          └─ event:error ───────────────▶ error
suspended ──resumeTurn(userInput, actionId)──▶ resuming (POST /agent/turn/{id}/resume)
```

关键点：
- `suspend` 事件同时填 `pendingCard` (UI 渲染用) 与 `pendingRef` (回调用)；
- `resume` 后清空 `pendingRef`，让 `card` 事件可再次填充；
- 60s 心跳仅在 `suspended` 状态运行；
- 组件卸载时同时 `abort()` 取消 SSE 与 `clearInterval` 停心跳。

### 3.4 AUIP 卡片渲染

`AUIRenderer` 接收 1 个 `CardDescriptor` + `(suspended | submitted | onSubmit)` props，
纯组件、**不发起任何 HTTP**。所有提交都通过 `onSubmit(userInput, actionId)` 冒泡
到 `useChatStream.resumeTurn()`，再调 `POST /agent/turn/{turn_id}/resume`。

11 种 card_type → 组件映射 (`aui/AUIRenderer.tsx`)：

```
OD_INPUT / PASSENGER_FORM / OAT_BINDING    → FormCard
FLIGHT_LIST / CABIN_LIST                   → SelectionListCard
PRICE_VERIFY                               → PriceVerifyCard
POLICY_DECISION                            → PolicyDecisionCard
ORDER_CONFIRM                              → OrderConfirmCard
ORDER_SUCCESS                              → OrderSuccessCard
CANNOT_ORDER                               → CannotOrderCard
CHAT_FALLBACK                              → ChatFallbackCard
unknown                                    → CardShell + 占位
```

### 3.5 跨页 prompt (`onAskAI`)

`SearchPage` 「让 AI 帮我查」 → `App.handleAskAI(prompt, hintScenario?)` → 切到 chat + 注入 `pendingPrompt`。
`hintScenario` 现在会一并传给 `App.setScenario(...)`，确保路由命中预期 scenario。

```ts
// SearchPage.tsx
const handleAskAI = () => {
  onAskAI?.(
    `帮我查 ${date} 从 ${departure} 到 ${arrival} 的机票…`,
    hintScenario ?? 'flight_query',
  );
};

// OrdersPage.tsx
const handlePay = (order: Order) => {
  onAskAI?.(`帮我支付订单 ${order.orderNo}`, hintScenario ?? 'flight_booking');
};
```

### 3.6 侧边栏 Scenario 切换器

`Sidebar` 现在渲染一个下拉 (`auto | flight_query | flight_booking`)，用户可手动覆盖路由器决策。
`App` 把选中的 `scenario` 透传给 `ChatPage` 与跨页跳转。

### 3.7 顶部状态条幅

`MessageList` 在已有消息后渲染一个横幅：

- `scenario` (e.g. `flight_query` v1.0.0 / hitl)
- `currentState` (Sxx 业务状态) + 切换次数
- `turnId` (前 6 位)
- `isSuspended` 时额外高亮 + 「AI 在等您输入」徽标 + 「取消本轮」按钮

## 4. 验证步骤

```bash
# 1) 启动后端 (用户手动) — 必须设置 scenario_paths
AGENT_SCHEDULER_PORT=18000 \
AGENT_SCHEDULER_SCENARIO_PATHS='["work/scenarios"]' \
AGENT_SCHEDULER_SKILL_PATHS='["work/shared/skills"]' \
  python -m openagent.main

# 2) 启动 opencode serve (可选, 真实 LLM 用; mock 模式可跳过)

# 3) 启动前端 (用户手动)
cd frontend
pnpm install        # 首次
pnpm dev            # http://localhost:3000

# 4) 联调检查清单
# [ ] 顶部状态条: 显示 "已连接 · flight_query · opencode-core · xxxxxxxx"
# [ ] 侧边栏底部: 绿色色点 + 场景切换器
# [ ] 机票查询页: 点 "让 AI 帮我查" → 跳到 chat, 自动发送 prompt + 切到 flight_query
# [ ] chat: 文本流式出现 + 工具调用折叠区 + 业务状态 pill
# [ ] 挂起态: AI 触发 OD_INPUT / FLIGHT_LIST 等卡片 → 横幅变橙 + 卡片可填
# [ ] 提交卡片: 调 /agent/turn/{id}/resume, 后续 stream 接到新事件
# [ ] 错误码: 后端 SCENARIO_NOT_FOUND 等会在 error 事件里出现, 显示在气泡内
# [ ] 心跳: 挂起期间 Network 面板能看到每 60s 一次的 /heartbeat 调用
# [ ] 取消: 侧边栏「取消本轮」按钮调 /cancel
# [ ] token: 未设置 VITE_MCP_TOKEN 时顶部条幅出现 "⚠ 未配置 MCP Token" 徽标
```

## 5. 已知边界

- **历史回放**: `GET /agent/session/{id}/messages` 仍只返 `{role, content}`，tool_use / card / state 不会被还原；刷新后只看到文本。
- **流式 / 同步切换**: 仍只暴露 SSE 入口 (`/agent/chat/stream`)；`/agent/chat` 同步端点保留兼容但 ChatPage 不用。
- **card schema 演进**: 当前前端按 11 种已知 card_type 渲染；遇到未知类型降级为带 `card_type` 名称的占位卡片。
- **`VITE_MCP_TOKEN`**: 仅前端占位；上线前请用公司 SSO 颁发的 per-tenant token，并通过 Vite build pipeline 注入。
- **生产构建**: 必须设置 `VITE_API_BASE_URL=https://api.example.com`（不要走 /api 代理）。
- **ChatInput 锁定**: 挂起态禁用输入框，提示「请在上方卡片中填写信息以继续…」；这是有意为之 (HITL 期间用户输入应走卡片)。
- **轮询**: scenario 列表只在挂载时拉一次，编辑器模式 (`/admin`) 重新加载需用户手动操作或刷新。
