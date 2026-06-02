# 前端 ↔ 后端联调说明（前端适配版）

> 本次提交只动前端，后端 `src/openagent/**` 完全保留。
> 验证：`pnpm exec tsc --noEmit` / `pnpm exec eslint .` / `pnpm exec vite build` 均通过。

## 1. 后端契约回顾（来源：`src/openagent/api/routes.py`、`streaming.py`）

| Method | Path | 用途 |
|--------|------|------|
| GET | `/health` | 健康探针 |
| GET | `/ready` | 就绪检查（含 storage / bridge / skill / tool / agents） |
| POST | `/agent/chat` | 同步聊天（保留兼容，主链路不再使用） |
| POST | `/agent/chat/stream` | **SSE 流式聊天** — 主入口 |
| POST | `/agent/session` | 创建会话 |
| GET | `/agent/session/{id}` | 会话元信息 |
| GET | `/agent/session/{id}/messages` | 拉取历史 |
| DELETE | `/agent/session/{id}` | 删除会话 |
| POST | `/agent/session/{id}/abort` | 中止进行中的运行 |
| GET / POST | `/agent/skills` | 技能列表 / 注册 |
| GET / POST | `/agent/tools` | 工具列表 / 注册 |
| PATCH | `/agent/tools/{name}/enabled` | 启停工具 |
| GET / POST | `/agent/pool/stats` / `/agent/pool/register` | Agent 池 |
| DELETE | `/agent/pool/{name}` | 注销 |

SSE 事件类型（`StreamEvent`，来自 `streaming.py`）：
`session` / `text` / `reasoning` / `tool_use` / `tool_result` / `done` / `error`。
前端统一以 `data: {type, data: {...}}` 一行 JSON 解析。

## 2. 前端新增结构

```
frontend/src
├── config/index.ts                 # 读取 VITE_API_BASE_URL，默认 '/api'
├── services/                       # 纯网络层
│   ├── http.ts                     # fetch 封装 + ApiError 归一化
│   ├── sse.ts                      # ReadableStream SSE 解析
│   ├── chat.ts                     # 同步 + 流式聊天
│   ├── session.ts                  # 会话 CRUD / abort
│   ├── skills.ts                   # 技能列表
│   ├── tools.ts                    # 工具列表 + 启停
│   ├── pool.ts                     # Agent 池
│   └── system.ts                   # /health + /ready
├── hooks/                          # React 状态机
│   ├── useChatStream.ts            # 核心：流式会话状态机
│   ├── useChatSession.ts           # sessionId 持久化 + 历史拉取
│   ├── useHealth.ts                # 后端健康轮询
│   ├── useSkills.ts / useTools.ts / usePool.ts
│   └── index.ts
└── types/
    ├── api.ts                      # ApiError / ApiResponse
    ├── domain.ts                   # SessionInfo / Skill / Tool / StreamEvent…
    ├── chat.ts / flight.ts / order.ts
    └── index.ts
```

## 3. 关键适配点

### 3.1 Vite 代理（开发态）

`vite.config.ts`：

```ts
proxy: {
  '/api': {
    target: process.env.VITE_BACKEND_URL || 'http://localhost:8000',
    changeOrigin: true,
    rewrite: (p) => p.replace(/^\/api/, ''),
    ws: false,
  },
},
```

`frontend/.env.example`：

```
VITE_API_BASE_URL=        # 留空走 /api 代理；生产环境填绝对地址
```

### 3.2 SSE 解析

`services/sse.ts` 用 `ReadableStream + TextDecoder` 增量消费，丢弃 `event:` / `id:` / 注释行，识别 `data:` 行
（允许多行 `data:` 拼接），按 `\n\n` 切分 record，最后做一次 `JSON.parse`。
未知 / 心跳帧直接跳过，`done` 事件触发 `for await` 退出。

### 3.3 流式聊天状态机（`useChatStream`）

```
idle ─send()──▶ sending
sending ─event:session──▶ streaming
streaming ─event:text──▶ streaming (+append text)
        ─event:tool_use/result──▶ streaming (+record)
        ─event:error──▶ error
        ─event:done / abort / network close──▶ idle
```

- `AbortController` 由 hook 持有 → 用户停止 / 组件卸载都会调用 `abort()`。
- 收到 `session` 事件时把 `session_id` 写回父组件 → 持久化到 `localStorage` (`openagent.session_id`)。
- `text` 事件按 chunk 追加到当前 assistant 气泡，光标 `▍` 持续闪烁。
- `tool_use` / `tool_result` 成对渲染，折叠区可展开 JSON。

### 3.4 会话持久化（`useChatSession`）

- session id 写入 `localStorage`（`openagent.session_id`），刷新后自动续接。
- `loadHistory(id)` 调 `GET /agent/session/{id}/messages`，把 `{role,content}` 转成本地 `ChatMessage`。
- 404 时自动清空本地 id，避免无限重试。

### 3.5 健康/就绪指示

- `useHealth(20s)` 轮询 `/health` + `/ready` → 输出四态：`unknown | healthy | degraded | unreachable`。
- 侧边栏底部显示色点（绿/橙/红/灰）。
- Chat 顶部条幅显示「已连接 · agent · xxxxxxxx」或连接失败提示。

### 3.6 Settings 面板

侧边栏「设置」按钮 → `SettingsPanel` 模态，4 个 Tab：

- **概览**：后端状态、storage/bridge/skills/tools 计数。
- **技能**：拉取 `/agent/skills`，展示 name/desc/triggers。
- **工具**：拉取 `/agent/tools`，提供实时启停（`PATCH /agent/tools/{name}/enabled`）。
- **Agent**：拉取 `/agent/pool/stats`，展示 name/sdk_type/base_url/default_model。

### 3.7 「问 AI」跨页跳转

后端暂无机票查询/订单支付的专属接口 → 保留前端 mock 数据作为视觉演示。
新增 `onAskAI` 回调：SearchPage / OrdersPage 点击「让 AI 帮我查 / 去支付 / 取消」时构造 prompt，
由 `App.tsx` 切到 chat Tab 并通过 `pendingPrompt` prop 注入到 ChatPage；ChatPage 在空闲时自动发送并清空该 prop。

## 4. 验证步骤

```bash
# 1) 启动后端（不要 run_in_background，由用户手动执行）
#    参考 CLAUDE.md 常用命令
python -m openagent.main          # http://localhost:8000

# 2) 启动 opencode serve（如使用 opencode 适配）
#    opencode serve --port 4096 --hostname 127.0.0.1

# 3) 启动前端（用户手动）
cd frontend
pnpm install        # 首次需要
pnpm dev            # http://localhost:3000

# 4) 联调检查清单
# [ ] 侧边栏底部出现绿色「后端 已连接」色点
# [ ] Chat 顶部条幅显示「已连接 · <agent> · xxxxxxxx」
# [ ] 输入问题 → 看到流式文字逐字出现
# [ ] 工具调用时折叠面板可展开
# [ ] 停止按钮可中断流
# [ ] 刷新页面后 session 续接
# [ ] 设置 → 技能/工具/Agent 三个 Tab 数据正常
# [ ] 机票查询/订单页点「让 AI 帮我查/去支付」会跳回 Chat 并自动发送
```

## 5. 已知边界

- 后端 `messages` 接口返回 `[{role, content}]`，尚未支持 `tool_calls` 还原 → 历史回放只渲染文本气泡。
- `POST /agent/pool/{name}` 在后端标记为未实现（501）→ 前端未在 UI 暴露注销按钮（仅 stats / register）。
- `SearchPage` 仍是 mock 数据，未对接后端的「机票」业务 Skill；如需真实航班数据，请在后端侧注册一个查询 Skill，前端无改动。
- Vite 代理仅在 dev 生效；生产构建请设置 `VITE_API_BASE_URL=https://api.example.com`。
