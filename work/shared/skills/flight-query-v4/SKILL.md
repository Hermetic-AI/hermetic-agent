---
name: flight-query-v4
description: "国内机票查询。v4 核心:把 LLM 多步推理固化为 backend 模板 — LLM 只做 PARSE,ENRICH/PRESENT 全在 backend。目标:端到端 2-3s。"
version: 4.0.0
allowed-tools:
  - Read
argument-hint: "[OD] [日期] [舱等] [筛选]"
---

# Flight Query v4 — Fixed Pipeline

> **v3 → v4 核心转变**:v3 让 LLM 解析需求 + 调工具 + 整理字段 + 设计方案 (4 步), 耗时 5-10s;
> v4 让 LLM **只填结构化表单**, 剩下 backend 全自动。目标: 端到端 2-3s, 砍掉 60% 推理。
>
> **关键**:你(LLM)看到的 ask_user schema 极简, 只填 `plan_kind` + `flightList`; 后端会用
> `templates/flask_payload.json` + `plan_rules.md` 自动生成完整 AUIP 卡片。**不要**自己
> 编 plans / flights 字段, 全交给 backend。

---

## 1. 必做 3 步 (固定流程, 不允许跳步)

1. **PARSE** — 把用户原话转成 `Query` JSON, 见 §2
2. **CALL** — 调 `queryFlightBasic` MCP 工具, 传 `Query`
3. **CARD** — 调 `ask_user` 工具, card_type=`FLIGHT_RESULT`, **只填** `plan_kind` + `flightList` (原样透传)

## 2. Query Schema (必填)

| 字段 | 必填 | 说明 |
|---|---|---|
| `origin` | ✅ | 中文原话 (例 "北京"). 接受 IATA 码但 backend 会查表翻译 |
| `destination` | ✅ | 同上 |
| `departDate` | ✅ | `yyyy-MM-dd`, **月日必须补零** (`2026-06-05`, 不是 `2026-6-5`) |
| `returnDate` | ❌ | 仅用户说"往返/双程"才追问; 不说 = `null` |
| `cabin` | ❌ | 默认 `ECONOMY`; 用户说"公务舱/头等舱"才覆盖 |
| `filters[]` | ❌ | 仅当用户明说"只要东航/直飞/含行李/早班"才填, 例 `[{key:"airline", value:"CA"}, {key:"nonStop":true}]` |

> 缺 `origin` / `destination` / `departDate` 任一 → **不**调工具, 推 `ASK_QUERY` 卡片 (见 §3).

## 3. 卡片协议 (极简, 4 种 card_type)

| card_type | 何时用 | 必填字段 | 完整模板 |
|---|---|---|---|
| `FLIGHT_RESULT` | 工具返回 flightList | `plan_kind` + `flightList` (原样) | `templates/flask_payload.json#flight_result` |
| `CANNOT_ORDER` | 工具返回空 / isError=true | `reason` + `fallback` | `templates/flask_payload.json#cannot_order` |
| `ASK_QUERY` (v4 新) | 用户输入缺字段 | `missing: string[]` | `templates/flask_payload.json#ask_query` |
| `CHAT_FALLBACK` | 兜底, LLM 拿不到工具结果 | `message` | `templates/flask_payload.json#chat_fallback` |

> ⚠️ `plan_kind` 枚举: `default` (3 方案 最快/最便宜/直飞首选) / `cheapest` / `fastest` / `comfortable` / `user_explicit` (用户已说"挑一个", 1 方案)
> **不**填 plans 数组, **不**填 flights 字段 — backend 用 plan_rules.md 自动生成。

## 4. 工具清单 (本 skill 调 1-2 个)

| MCP 工具 | 何时用 |
|---|---|
| `queryFlightBasic` | **唯一**查票工具. 改 OD/日期/舱等 → **重调**. 城市用中文, IATA 先翻译. |
| `filterFlightList` | 仅当用户**追加** TMS 不支持条件 (`planeSize` / `maxDuration`). 改 OD/日期 → **不**调本工具, 重调 `queryFlightBasic`. |

## 5. 城市翻译 (子 skill)

用户说 IATA/ICAO/机场名 (例 "PEK" / "ZSPD" / "浦东") → **加载** `flight-query-v4:iata_icao_codes` 子 skill (30+ 城市对照表, 1-2s 翻译).

## 6. 铁律 (3 条, 不允许违反)

1. **缺字段不编造** — origin/destination/departDate 缺哪个 → 推 `ASK_QUERY` 卡片, 让用户填
2. **改 OD/日期/舱等 → 重调** `queryFlightBasic`, **不**在 `filterFlightList` 上做客户端过滤
3. **本 skill 只查票** — 选舱/填人/核价/下单/订单状态 → **引导** 用户走 `flight-booking` skill, **不**调本 skill 范围外的 MCP 工具

## 7. 错误处置 (极简, 全部走 CANNOT_ORDER 卡片)

| 现象 | `reason` 字段 |
|---|---|
| `flightList=[]` 且 `filteredCount=0` | "暂无符合条件的航班" |
| `isError=true` | 用 `errorMsg` 原话 |
| 4xx/5xx (连续 2 次) | "机票查询服务暂时不可用, 请稍后重试" |

> 不需要重试逻辑, 不需要 fallback URL — **直接**推 `CANNOT_ORDER` 卡片即可。

## 8. 业务边界 (不接)

| 本 skill 负责 | `flight-booking` 负责 |
|---|---|
| 查票 + 推 3 方案 (default) / 1 方案 (user_explicit) | 选舱 / 填人 / 核价 / 下单 / 订单详情 |
| 内存二次筛选 (`planeSize` / `maxDuration`) | 退改 / 行李额 / 差标 |
| 改条件重查 | 订单生命周期 |

---

**对应 scenario**: `work/scenarios/flight_query_v4.scenario.yaml`
**AUIP 模板**: `templates/flask_payload.json` (4 种 card_type 完整 JSON 范例)
**方案规则**: `plan_rules.md` (backend 用, 你**不要**手写 plans)
**MCP 配置**: `work/mcp/servers.json`
