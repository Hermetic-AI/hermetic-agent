# SKILL-INDEX — flight-query-v4 一页导航

> **v4 一页 cheat sheet**。先看这张图,再决定读哪个文件。
> 不知道读什么 / 上下文紧张时, **只看本文件**就够开干。

---

## 1. 文件树(本 skill 自包含)

```
work/shared/skills/flight-query-v4/         ← 你在这里
├── SKILL.md                                ← 核心层 (必读, ~110 行)
│                                            · 3 步固定流程 · Query schema · 卡片协议 · 铁律 · 错误 · 边界
├── SKILL-INDEX.md                          ← 本文件 (导航)
├── CHANGELOG.md                            ← v3 → v4 变更记录
├── plan_rules.md                           ← backend 用, LLM **不要**读
│                                            · plan_kind → plans[] 自动生成
│                                            · FlightSegment 字段映射 1:1
│                                            · tags 派生规则
├── templates/
│   └── flask_payload.json                  ← 4 种 card_type 完整 JSON 模板
│                                            · FLIGHT_RESULT / CANNOT_ORDER / ASK_QUERY / CHAT_FALLBACK
└── flight-query-v4.iata_icao_codes/        ← 子 skill: IATA 翻译 (按需加载)
    └── SKILL.md                            · 30+ 城市 IATA+ICAO 对照表
```

> **v4 与 v3 关键差异**:LLM **不再手填** `plans[]` / `flights[]` 字段 — 只传 `plan_kind` + `flightList` (原样),
> backend 用 `plan_rules.md` + `templates/flask_payload.json` 1ms 渲染完整 AUIP 卡片。
> 节省 LLM 推理 ~2s/轮。

---

## 2. 决策树(LLM 怎么用本 skill)

```
收到用户查询
  │
  ▼
是不是本 skill 的范围?
  │  "查票/搜航班/有哪些/最便宜/含行李/直飞/某航司"
  │  → ✅ 走本 skill
  │  "选舱/下单/填人/核价/订单状态/退改"
  │  → ❌ 走 flight-booking skill (本 skill **不**接)
  │
  ▼
读 SKILL.md (必读, ~110 行)
  │
  ▼
用户说 IATA / ICAO / 机场名?
  │  是 → 加载子 skill flight-query-v4:iata_icao_codes
  │  否 → 城市直接用中文
  │
  ▼
解析用户需求, 检查必填字段 (origin / destination / departDate)
  │  缺任一 → 调 ask_user 推 ASK_QUERY 卡片 (v4 新增, 让用户填表单)
  │  全部齐 → 调 queryFlightBasic 工具
  │
  ▼
工具返回 flightList
  │  空 / 错误 → 调 ask_user 推 CANNOT_ORDER 卡片
  │  正常 → 调 ask_user 推 FLIGHT_RESULT 卡片
  │           · plan_kind: "default" (3 方案) / "cheapest" / "fastest" / "comfortable" / "user_explicit"
  │           · flightList: 原样透传 (MCP 返回的 dict[] 数组)
  │           · **不**填 plans / flights 字段 — backend 自动生成
  │
  ▼
需要"飞机大小/飞行时长"二次筛选?
  │  是 → 调 filterFlightList (planeSize / maxDuration), 不重调 TMS
  │
  ▼
要"选航班/选舱/下单"?
  │  是 → 引导用户走 flight-booking skill
  │       本 skill 只展示 flightList 顶层信息
  │       **不**渲染舱位详情/退改规则/行李额
```

---

## 3. 30 秒速记(LLM 必背)

| 字段 | 值 |
|---|---|
| 主工具 | `queryFlightBasic` (TMS 调上游) |
| 次工具 | `filterFlightList` (内存筛选, planeSize/maxDuration, **改 OD 不调**) |
| 工具入参 | **中文原话** (不接受 IATA 码) |
| 日期格式 | `yyyy-MM-dd`, 月日必须补零 |
| 必填字段 | `origin` / `destination` / `departDate` |
| 卡片 | `ask_user` 工具推 `FLIGHT_RESULT` / `CANNOT_ORDER` / `ASK_QUERY` |
| plan_kind | `default`(3 方案) / `cheapest` / `fastest` / `comfortable` / `user_explicit` |
| 铁律 | 改 OD/日期/舱等 → **重调** queryFlightBasic, 不调 filterFlightList |
| 不接 | 选舱/填人/核价/下单/订单 → `flight-booking` skill |
| 协议在哪 | `work/mcp/servers.json` (LLM **不要**关心, 只调工具) |
| **不填** | `plans[]` / `flights[]` 字段 (backend 用 `plan_rules.md` 自动生成) |

---

## 4. 与 flight-booking 的边界

| 本 skill 负责 | flight-booking 负责 |
|---|---|
| 搜航班 (OD+日期+筛选) | 选航班 (chooseFlight) |
| 渲染顶层 flightList 信息 (航班号/航司/时刻/价格) | 渲染舱位详情 (cabinList) |
| 内存二次筛选 (planeSize / maxDuration) | 退改规则详情 / 行李额 / 乘机人档案 |
| 改条件重查 / 业务错误兜底 | 核价 / 差标决策 / 订单预览 / 下单 / 订单详情 |

---

## 5. 子 skill 加载时机速查

| LLM 此刻在... | 加载哪个子 skill |
|---|---|
| 用户说 "BJS / PEK / 浦东" | `flight-query-v4:iata_icao_codes` (翻译) |
| 用户说 "选第一个" / "下单" | **不**加载任何子 skill — 引导走 `flight-booking` skill |
| 报错 "请求航信超时" | **不**加载 — 父 skill §7 已写处置 |
| 准备调 `queryFlightBasic` | **不**加载 — 工具 `inputSchema` 已被 opencode 注入 LLM context |

---

## 6. v3 → v4 核心差异(LLM / 工程师速记)

| 项 | v3 | v4 |
|---|---|---|
| LLM 填 `plans[]` / `flights[]` | ✅ 必填 (24 行字段映射表) | ❌ **不填** — backend 1ms 生成 |
| 方案分组 (3 方案 / 1 方案) | LLM 自己决策 (7 种偏好) | LLM 传 `plan_kind` 枚举, backend 按 `plan_rules.md` 生成 |
| 字段映射 | LLM 按 §5.2 表逐字段翻译 | backend `_flight_to_auip()` 函数 1ms 完成 |
| 错误卡片构造 | LLM 写 message | LLM 填 `reason` / `fallback`, 模板渲染 |
| 缺字段追问 | LLM 自己组织自然语言 | LLM 推 `ASK_QUERY` 卡片, 让用户填表单 (前端自动渲染) |
| SKILL.md 行数 | 273 行 | **~110 行** (砍 60%) |
| 端到端耗时 | 5-10s | **2-3s** (砍 60%) |

---

**最后更新**:2026-06-05
**对应 scenario**:`work/scenarios/flight_query_v4.scenario.yaml`
**MCP 配置**:`work/mcp/servers.json`
**设计文档**:`work/shared/skills/flight-query-v4/plan_rules.md` (LLM 不读)
