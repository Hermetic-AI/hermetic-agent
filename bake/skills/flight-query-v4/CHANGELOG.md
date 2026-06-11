# CHANGELOG — flight-query-v4 vs flight-query-v3

> 本目录是 v4, 父目录 `work/shared/skills/flight-query-v3/` 是 v3 (仍保留作为对比/回滚).
> 本文档记录 v3 → v4 的变更及原因.

---

## 0. TL;DR(30 秒读懂)

v3 的核心痛点: **LLM 在 4 步推理上花 5-10s** (解析需求 + 调工具 + 整理字段 + 设计方案).
v4 的核心做法: **把"LLM 整理"固化为 backend 模板** — LLM 只填最少的 `Query` + `plan_kind`, 剩下 backend 1ms 出卡片.

```diff
- [LLM 解析用户需求 (1-2s)]
- [LLM 调 queryFlightBasic (1-2s)]
- [LLM 按 §5.2 字段映射表 24 行逐字段翻译 (1-2s)]
- [LLM 按 §5.3 7 种偏好设计 3 方案 (0.5-1s)]
- [LLM 调 ask_user 推完整 FLIGHT_RESULT 卡片 (1s)]
+ [LLM 解析用户需求 (1-2s)]            ← LLM 仍然做这一步
+ [LLM 调 queryFlightBasic (1-2s)]       ← MCP 工具调用不变
+ [LLM 调 ask_user, 只填 plan_kind + flightList (0.3s)]   ← **砍掉 2 步**
+ [backend _build_plans() 1ms 生成完整 plans[] + flights[]]  ← **新: 模板化**
```

**端到端**: 5-10s → **2-3s** (砍 60%)

---

## 1. 详细差异表

### 1.1 LLM 必填字段 (大幅减少)

| 项 | v3 | v4 |
|---|---|---|
| LLM 填 `plans[]` 数组 | ✅ 必填 1-3 个 | ❌ **不填** |
| LLM 填 `flights[]` 内每个字段 | ✅ 必填 12 字段 (airline/departure/arrival/...) | ❌ **不填** |
| LLM 填 `summary.totalCount` | ✅ 必填 | ❌ backend 算 |
| LLM 填 `summary.filteredCount` | ✅ 必填 | ❌ backend 算 |
| LLM 填 `summary.searchType` | ✅ 必填 (3 选 1) | ❌ backend 按 plan_kind 推 |
| LLM 填 `summary.weather` | ❌ 可选 | ❌ backend 不填 (后续接入) |
| LLM 填 `plan_kind` (新字段) | — | ✅ 必填 (`default`/`cheapest`/`fastest`/`comfortable`/`user_explicit`) |
| LLM 填 `flightList` (MCP 原样) | — | ✅ **必填** (后端从这里抽字段) |
| LLM 填 `missing[]` (ASK_QUERY 卡片) | — | ✅ 必填 (v4 新卡片类型) |

### 1.2 卡片协议 (新增 1 种 + 简化 3 种)

| card_type | v3 | v4 |
|---|---|---|
| `FLIGHT_RESULT` | 必填 30+ 字段 (summary + plans + flights) | 必填 2 字段: `plan_kind` + `flightList` |
| `CANNOT_ORDER` | LLM 写 message | 必填 2 字段: `reason` + `fallback` |
| `ASK_QUERY` (新) | — | 必填 `missing: string[]`, 让用户填表单 |
| `CHAT_FALLBACK` | 兜底 | 必填 `message` |

### 1.3 SKILL.md 行数 (大幅减少)

| 章节 | v3 | v4 |
|---|---|---|
| §1 工具总览 | 5 行 + 路由决策 ASCII 图 (15 行) | 5 行 (删除路由决策图) |
| §2 城市翻译 | 引用子 skill | 引用子 skill (不变) |
| §3 错误处理 | 6 行表格 | 7 行表格 (极简) |
| §4 铁律 | 9 条 | **3 条** (砍 60%) |
| §5 输出格式 + 卡片规范 | 100+ 行 (含字段映射表 24 行 + 方案分组 7 种) | **模板化到独立文件** (`templates/flask_payload.json` + `plan_rules.md`) |
| §6 Skill ↔ MCP 边界 | 9 行表格 | 移到 CHANGELOG |
| §7 子 skill | 1 行 | 1 行 (不变) |
| **总行数** | **273 行** | **~110 行** (砍 60%) |

### 1.4 Backend 新增代码

| 模块 | 路径 | 行为 |
|---|---|---|
| `_build_plans()` | `auip/flight_query_presenter.py` (L3, 新) | `plan_kind` + `flightList` → 完整 `plans[]` |
| `_flight_to_auip()` | 同上 | MCP `flightList[i]` → AUIP `FlightSegment` (1:1 字段映射) |
| `_derive_tags()` | 同上 | 派生 "最便宜"/"最快"/"大飞机直飞" 等标签 |
| `ASK_QUERY` 卡片渲染 | auip/cards.py + CardShell | v3 没有, v4 新增 |

### 1.5 错误处理 (v3 错误码逐条 → v4 极简表)

| 现象 | v3 处置 | v4 处置 |
|---|---|---|
| 工具返回 `isError=true` | LLM 按 `errorMsg` 写 message | 推 `CANNOT_ORDER`, `reason=errorMsg` |
| 工具返回空 `flightList=[]` | 推 `CANNOT_ORDER` 卡片 | 推 `CANNOT_ORDER`, `reason="暂无符合条件的航班"` |
| 4xx/5xx (连续 2 次) | 推 `CANNOT_ORDER` 卡片 | 推 `CANNOT_ORDER`, `reason="机票查询服务暂时不可用, 请稍后重试"` |
| 用户输入缺字段 | LLM 自己组织追问话术 | 推 `ASK_QUERY` 卡片, `missing=["destination", "departDate"]` |

### 1.6 LLM 决策点 (砍 6 → 0)

| LLM 决策 | v3 | v4 |
|---|---|---|
| 哪些字段填入 `plans[]` | ✅ | ❌ backend 算 |
| 哪些字段填入 `flights[]` | ✅ | ❌ backend 算 |
| 3 方案怎么排序 | ✅ | ❌ backend 按 `plan_kind` 算 |
| 哪些 tag 派生 | ✅ | ❌ backend 按规则算 |
| summary 怎么写 | ✅ | ❌ backend 算 |
| cabinClass 怎么映射 | ✅ | ❌ backend 算 |

---

## 2. 兼容性 / 迁移

| 客户端 | 兼容性 | 说明 |
|---|---|---|
| `FlightResultCard` 前端组件 | ✅ 完全兼容 | 卡片 payload 仍是 AUIP `FLIGHT_RESULT` 完整结构 |
| `ask_user` 工具 schema | ⚠️ **不兼容** | LLM 入参从 `summary+plans+flights` 改为 `plan_kind+flightList`. 老 LLM (v3) 发的卡片会被 backend 拒收, 提示 schema 错误. |
| MCP server (TMS) | ✅ 完全兼容 | `queryFlightBasic` / `filterFlightList` 入参/出参不变 |
| `work/mcp/servers.json` | ✅ 完全兼容 | 配置不动 |
| opencode config | ✅ 完全兼容 | 工具 schema 不变 |

### 2.1 路由切换

`work/scenarios/flight_query_v4.scenario.yaml` 用关键词 `[查机票v4, flight query v4, ...]` 触发, 跟 v3 不冲突.
生产切换: 把前端"Ask AI"按钮的 `X-Scenario` 头从 `flight_query_v3` 改为 `flight_query_v4`, 或
直接灰度: 50% v3 + 50% v4 (scenario router 按 priority + 随机选).

---

## 3. 测试覆盖

- `tests/test_scenario_loader.py` — 加载 v4 yaml, 校验必填字段
- `tests/test_auip_flight_query.py` (新) — `_build_plans()` / `_flight_to_auip()` / `_derive_tags()` 单元测试
- `tests/test_ask_query_card.py` (新) — ASK_QUERY 卡片 schema 校验

---

**最后更新**:2026-06-05
**对应 scenario**:`work/scenarios/flight_query_v4.scenario.yaml`
**父 skill**:`work/shared/skills/flight-query-v3/SKILL.md` (legacy 对照)
