# 持久化 WorkTrace + 右侧工作面板 — 设计方案

> 状态：v1 已批准 · 2026-06-30
> 目标读者：hermetic-agent 维护者 / 前端 / 评审
> 配套实施计划：`docs/superpowers/plans/2026-06-30-persistent-work-trace-plan.md`（待生成）

---

## 1. 目标与范围

- 复刻 Coze / Manus / opencode web 的「3-栏 + 实时工作面板」体验
- **每个 turn** 在执行中 + 执行后都能完整回放「agent 做了什么、怎么做的、产出什么」
- 历史 session 可翻看 turn 轨迹
- **0 行改动**既有模块签名；5 层依赖严格守住；不破「统一 chat 入口」

非目标（v1 不做）：
- 不做 turn 之间的「分支 / 对比」
- 不做产物文件托管（只存指针 + 重定向到源 / 临时上传）
- 不做实时协作（多人同时看同一 session）

---

## 2. 数据模型

新增 1 张表 `turn_work_trace`（1 行 / turn，events JSONB 存明细）：

| 字段 | 类型 | 含义 |
|---|---|---|
| `turn_id` | UUID PK | 1:1 对齐 `turn_store.turns.id` |
| `session_id` | UUID | 所属 session（索引） |
| `scenario` | TEXT | `flight_booking` / `code_review` / `_generic` |
| `started_at` | TIMESTAMPTZ | turn 开始 |
| `finished_at` | TIMESTAMPTZ | turn 结束 |
| `status` | TEXT | `running` / `suspended` / `done` / `error` |
| `summary` | JSONB | 聚合：tool 计数、文件 diff 计数、产物数、cost_estimate |
| `events` | JSONB | `TraceEvent[]` 数组，按 seq 升序 |

DDL：

```sql
CREATE TABLE turn_work_trace (
  turn_id         UUID         PRIMARY KEY,
  session_id      UUID         NOT NULL,
  scenario        TEXT,
  started_at      TIMESTAMPTZ  NOT NULL,
  finished_at     TIMESTAMPTZ,
  status          TEXT,
  summary         JSONB        NOT NULL DEFAULT '{}'::jsonb,
  events          JSONB        NOT NULL DEFAULT '[]'::jsonb,
  created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_turn_work_trace_session_started
  ON turn_work_trace (session_id, started_at DESC);
```

`TraceEvent` schema：

```python
class TraceEvent(TypedDict):
    seq: int
    at: str
    kind: Literal[
        'tool_io', 'state', 'todo', 'question',
        'scenario', 'card', 'suspend', 'product', 'error'
    ]
    payload: dict
```

每 kind payload：
- `tool_io`: `{id, name, phase, input, output_redacted, output_truncated?}`
- `state`: `{from, to, label?}`
- `todo`: `{items: [{content, status, priority}]}`
- `question`: `{id, status, prompt, options?}`
- `scenario`: `{name, version, matched_by}`
- `card`: `{card_id, card_type, title?}`
- `suspend`: `{checkpoint_id, reason?}`
- `product`: `{product_id, kind: 'file'|'url'|'text', path?, url?, mime?, size_bytes?}`
- `error`: `{code, message}`

---

## 3. 后端模块（全部新增，0 改既有签名）

| 层 | 文件 | 行数上限 | 职责 |
|---|---|---|---|
| L3 | `src/hermetic_agent/auip/work_trace_reducer.py` | ≤200 | 输入 `StreamEvent` → 输出 `TraceEvent[]`；含 redact + product 推断 |
| L5 | `src/hermetic_agent/store/work_trace_store.py` | ≤200 | `WorkTraceStorage` ABC + `PostgresWorkTraceStorage` + `MemoryWorkTraceStorage` |
| L5 | `src/hermetic_agent/store/dto/work_trace.py` | ≤200 | `AppendEventsRequest`, `GetTraceRequest`, Pydantic |
| L1 | `src/hermetic_agent/api/http/streaming/work_trace_listener.py` | ≤200 | 单向 sink；订阅 chat 流；每 event 调 reducer + store.append |
| L1 | `src/hermetic_agent/api/http/controllers/turn_work_trace_controller.py` | ≤200 | 4 个 GET 端点 |

**关键不变量**：
- `work_trace_listener` 是**单向 sink**，不修改 stream 内容、不改 yield 顺序
- listener 抛错 → try/except 隔离，**chat 流必须继续**
- reducer 是**纯函数**（`StreamEvent, ctx → TraceEvent[]`），易测

**5 层依赖**：
- L1 listener → L3 reducer + L5 store ✅
- L3 reducer → L5 store ✅
- 不动既有层间关系

---

## 4. Reducer 推断规则

| SSE event | TraceEvent kind | 推断动作 |
|---|---|---|
| `scenario` | `scenario` | 直传 |
| `state` | `state` | 直传 |
| `card` | `card` | 直传 |
| `suspend` / `resume` | `suspend` | 直传 |
| `tool_use` | `tool_io` (phase=call) | `input` 全量；`name` → `tool_name` |
| `tool_result` | `tool_io` (phase=result) | `output` redact ≤ 4KB；超长 → `output_truncated=true` + 推断 `product` |
| `question_asked` | `question` | 直传 + `product` 候选（prompt 含 URL） |
| `question_replied` / `question_rejected` | `question` (update) | 合并到同 id |
| `todo_updated` | `todo` | 直传 |
| `error` | `error` | 直传 |

**product 推断规则**：
- 工具名匹配 `^(write|edit|create|notebook_edit)$`（含各种别名）→ `product {kind: 'file', path}`
- 工具名匹配 `^(bash|command|shell)$` 且 `output` 含 `/path/to/file` → `product {kind: 'file', path}`
- `output` 看起来是 HTML（`<!DOCTYPE|<html`）→ `product {kind: 'file', mime: 'text/html'}`
- `output` 看起来是 URL（`https?://...`）→ `product {kind: 'url', url}`

**redact 规则**：
- `output` 超过 4096 字节 → 截断 + `output_truncated: true`
- 含 `BEGIN PRIVATE KEY` / `sk-` / `ghp_` / `Bearer ` → `***REDACTED***`
- `input` 同样规则

---

## 5. 新 API 端点（4 个 GET，全只读，不破统一 chat 入口）

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/agent/turns/{turn_id}/work-trace` | 单 turn 完整 trace JSON |
| GET | `/agent/turns/{turn_id}/work-trace/stream` | SSE 实时跟踪 running turn（可选） |
| GET | `/agent/turns/{turn_id}/work-trace/products/{product_id}` | 拉单个产物（重定向到源 / inline 文本） |
| GET | `/agent/sessions/{session_id}/work-traces?limit=20` | session 下最近 N 个 turn trace 索引 |

**约束验证**：`scripts/check_unified_chat_entry.py` 正则只禁 `/agent/scenarios/[^/]+/chat`，新路径在 `/agent/turns/...` 下 ✅

**错误码**：复用既有 12 个；新场景仅复用 `SCENARIO_RESOURCE_UNAVAILABLE`（产物文件丢失）

---

## 6. 前端架构

3-栏布局：

```
┌─────────┬──────────────────┬──────────────────┐
│ Sidebar │   MessageList    │   WorkPanel (新) │
│         │   (text+reason)  │   ┌────────────┐ │
│ session │                  │   │ Activity   │ │
│ list    │   ChatInput      │   ├────────────┤ │
│         │                  │   │ Files      │ │
│         │                  │   ├────────────┤ │
│         │                  │   │ Plan/Q&A   │ │
│         │                  │   └────────────┘ │
└─────────┴──────────────────┴──────────────────┘
```

**SSE 共享策略**：
- 新增 `frontend/src/services/stream.ts`：`createStreamSource(req, signal): AsyncIterable<StreamEvent>`
- 改 `chatService.sendStream` 内部调 `createStreamSource()`，对每个消费者返回独立 AsyncIterable（共享同一 fetch + ReadableStream 句柄）
- `useChatStream` 和 `useWorkPanel` **各自独立消费** AsyncIterable

**新前端文件**：

| 文件 | 行数估算 | 职责 |
|---|---|---|
| `services/stream.ts` | ~80 | `createStreamSource` 抽 SSE 解析 |
| `services/chat.ts` | 改 ~20 | 重构 sendStream 用 createStreamSource |
| `hooks/useChatStream.ts` | 改 ~30 | 业务逻辑保留，订阅方式改 |
| `hooks/useWorkPanel.ts` (新) | ~150 | 订阅同源 SSE，累积 TraceEvent |
| `hooks/usePastTrace.ts` (新) | ~80 | 拉历史 turn trace |
| `components/layout/WorkPanel.tsx` (新) | ~80 | 右栏容器 + Tab 切换 |
| `components/work/ActivityFeed.tsx` (新) | ~120 | 工具调用滚动 |
| `components/work/FilesTab.tsx` (新) | ~100 | 文件 diff 列表 |
| `components/work/DiffViewer.tsx` (新) | ~150 | 行级 diff（`diff` npm 包） |
| `components/work/PlanTab.tsx` (新) | ~120 | Q&A + Todo + 状态条 |
| `components/work/ProductList.tsx` (新) | ~80 | 产物链接 |
| `components/layout/MainLayout.tsx` | 改 ~10 | 加 WorkPanel slot + 折叠按钮 |

**新增 npm 依赖**：`diff`（5.x），`diff2html`（5.x）

---

## 7. 实施切片（4 个独立 Phase）

| Phase | 内容 | 验证 | 工时 |
|---|---|---|---|
| **P1 数据地基** | DDL migration + `WorkTraceStorage` (Postgres+Memory) + DTO + 单测 | `pytest tests/test_work_trace_store.py` | 2 天 |
| **P2 reducer + listener** | `work_trace_reducer.py` (8 kind 推断) + `stream_listener.py` (注入 chat_controller 尾部) + 端到端单测 | `pytest tests/test_work_trace_reducer.py` + 手动 curl | 3 天 |
| **P3 API + 前端读路径** | 4 个 GET 端点 + `services/stream.ts` 重构 + `useWorkPanel` 骨架 + `WorkPanel` + `ActivityFeed` | `pytest tests/test_turn_work_trace_api.py` + 浏览器手测 | 4 天 |
| **P4 完整 UI + diff** | `FilesTab` + `DiffViewer` + `PlanTab` + `ProductList` + MainLayout 集成 + 历史回放 | 手动 e2e + 截图 | 3 天 |

**总工作量 ≈ 12 工作日（2.5 周）**。任意 Phase 失败可独立 rollback（只新增，不改既有 chat 行为；trace 写入失败由 listener try/except 隔离）。

---

## 8. 测试矩阵

| 类型 | 覆盖 | 文件 |
|---|---|---|
| 单元 | reducer 各 kind 推断、redact 规则 | `tests/test_work_trace_reducer.py` |
| 集成 | Postgres + Memory store CRUD | `tests/test_work_trace_store.py` |
| API | 4 个 GET 端点 + 错误码 | `tests/test_turn_work_trace_api.py` |
| E2E | 真实 turn → 落库 → API 拉回 | `tests/test_e2e_work_trace.py`（默认 skip） |
| 前端 | `createStreamSource` 双消费 + `useWorkPanel` 累积 | `frontend/src/__tests__/` |

---

## 9. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| `tool_result.output` 体积大撑爆字段 | 中 | 高 | redact 上限 4KB + `output_truncated` + product 引用 |
| 双消费 SSE 拉 2 份流量 | 中 | 中 | `createStreamSource` 单 fetch 句柄多 consumer |
| listener 抛错拖垮 chat 流 | 低 | 高 | try/except 隔离 |
| 两 engine tool output 格式不一致 | 中 | 中 | 双匹配 + fallback 仅存 raw |
| `events[]` 数组单 turn 体积 | 低 | 中 | 软上限 1000 条 + 标记 truncated |
| 翻历史 turn 时 trace 未写完 | 中 | 低 | SSE stream 端点 + 前端轮询 |

---

## 10. 依赖与约束检查

- **5 层架构**：新模块均符合 `L1→L3,L5` / `L3→L5` 规则
- **统一 chat 入口**：新端点全在 `/agent/turns/...` 下，`check_unified_chat_entry.py` 通过
- **既有签名**：0 行改动 `streaming.py` / `chat_controller.py` / `providers/*.py` / `skills/registry.py` / `mcp/registry.py` / `core/scheduler.py`
- **错误码 12 个**：复用既有 12 个；新场景用 `SCENARIO_RESOURCE_UNAVAILABLE`
- **文件大小**：所有新文件 ≤ 200 行（L1/L5 限额），L3 reducer ≤ 200 行
- **CI 校验**：`python scripts/ci_check.py` + `python scripts/check_unified_chat_entry.py` 必须通过
- **测试**：`pytest tests/test_work_trace_*.py` ≥ 80% 覆盖

---

## 11. 交付物清单

| 项 | 形态 |
|---|---|
| 设计 spec | `docs/superpowers/specs/2026-06-30-persistent-work-trace-design.md` |
| 实施 plan | `docs/superpowers/plans/2026-06-30-persistent-work-trace-plan.md`（由 writing-plans 技能生成） |
| DDL migration | `migrations/2026-06-30-turn_work_trace.sql` |
| 前端依赖更新 | `frontend/package.json`（+`diff`, `diff2html`），`requirements.txt` 同步 |
| Docker 镜像 | `docker build hermetic-agent`（P3 引入 `diff2html` 时需 rebuild） |
| 文档 | `docs/work-trace.md`（用户侧使用说明）+ 更新 `docs/architecture-and-flow.md` §3.3 提一句 SSE 副作用 |

---

## 12. 附录：与现有模块的集成点

| 集成点 | 当前状态 | 改造 |
|---|---|---|
| `chat_controller.stream_chat` | 单 SSE yield 循环 | 在 yield 循环外层包 listener sink（不改 yield 顺序） |
| `providers/streaming.py` | 16 种 StreamEvent | **不改** — listener 直接消费既有事件 |
| `frontend/services/sse.ts` | `parseSSE(response)` 解析器 | 抽出共享逻辑到 `stream.ts`；`sse.ts` 保留为底层 |
| `turn_store.turns` | 1 行 / turn | turn_id 作为 work_trace 的 PK 1:1 引用 |
| `PostgresStorage` | 已有 | work_trace 走独立 store 类，不污染既有 CRUD |

---

## 13. 附录：示例 trace（一次 flight_booking turn）

```json
{
  "turn_id": "0190a8e1-...",
  "session_id": "0190a8c0-...",
  "scenario": "flight_booking",
  "status": "done",
  "started_at": "2026-06-30T08:00:01Z",
  "finished_at": "2026-06-30T08:00:14Z",
  "summary": {
    "tool_calls": 4,
    "files_changed": 1,
    "products": 1,
    "questions_asked": 2,
    "todos_completed": "3/5"
  },
  "events": [
    {"seq": 1, "at": "...", "kind": "scenario", "payload": {"name": "flight_booking", "version": "1.2.0", "matched_by": "keyword"}},
    {"seq": 2, "at": "...", "kind": "state", "payload": {"from": "S00", "to": "S01"}},
    {"seq": 3, "at": "...", "kind": "todo", "payload": {"items": [{"content": "查航班", "status": "in_progress", "priority": "high"}]}},
    {"seq": 4, "at": "...", "kind": "tool_io", "payload": {"id": "t1", "name": "query_flight_basic", "phase": "call", "input": {"from": "北京", "to": "上海"}}},
    {"seq": 5, "at": "...", "kind": "tool_io", "payload": {"id": "t1", "name": "query_flight_basic", "phase": "result", "output_redacted": "[10 flights]", "output_truncated": false}},
    {"seq": 6, "at": "...", "kind": "question", "payload": {"id": "q1", "status": "asked", "prompt": "选哪个航班？", "options": ["CA1501", "MU5102"]}},
    {"seq": 7, "at": "...", "kind": "question", "payload": {"id": "q1", "status": "replied", "answer": ["CA1501"]}},
    {"seq": 8, "at": "...", "kind": "product", "payload": {"product_id": "p1", "kind": "url", "url": "https://booking.example/orders/R-9X", "mime": "text/html"}},
    {"seq": 9, "at": "...", "kind": "state", "payload": {"from": "S11", "to": "S13"}},
    {"seq": 10, "at": "...", "kind": "done", "payload": {}}
  ]
}
```

---

## 14. 审查 checklist（提交评审时勾选）

- [ ] 数据模型合理（events 数组 vs 多表）
- [ ] 4 个 Phase 切分粒度合适
- [ ] 风险接受度（`tool_result.output` redact 4KB 阈值 + product 推断召回率）
- [ ] 错误码复用 vs 新增
- [ ] 前端 npm 依赖（`diff` + `diff2html`）OK
- [ ] 与现有 `streaming.py` / `chat_controller.py` 0 改动承诺可守住