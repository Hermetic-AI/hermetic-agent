# SKILL-INDEX — flight-query 一页导航

> **给 LLM 的一页 cheat sheet**。先看这张图,再决定读哪个文件。
> 不知道读什么 / 上下文紧张时,**只看本文件**就够开干。

---

## 1. 文件树(本 skill 自包含)

```
work/shared/skills/flight-query/         ← 你在这里
├── SKILL.md                              ← 核心层(必读,~250 行)
│                                          · 入口契约 · 路由决策 · 城市翻译速查 · 错误 · 铁律 · 真实样本速查
├── SKILL-INDEX.md                        ← 本文件(导航)
├── tools/                                ← 工具接口 + 真实响应
│   ├── README.md                         · 文件说明 + 刷新流程
│   ├── flight-mcp.json                   · MCP tools/list 真实响应(权威源,15 个工具)
│   ├── flight-mcp.live.json              · 同上(本次实时抓的备份)
│   └── samples/                          · 4 份真实调用样本(用真实 token 抓)
│       ├── req.*.json                    · 请求体
│       └── queryFlightBasic.*.json       · 响应(全量/最便宜/筛选空结果/往返业务错误)
├── examples/                             ← 5 个真实可跑 curl 模板
│   ├── README.md
│   ├── 01-oneway-full.sh
│   ├── 02-oneway-cheapest.sh
│   ├── 03-oneway-filtered.sh
│   ├── 04-roundtrip-recommended.sh
│   └── 05-filter-on-loaded.sh
├── flight-query.query_flight_basic/      ← 子 skill:深度 schema
│   └── SKILL.md                          · 完整 input/output schema + NL 映射 + 6 个 use case
└── flight-query.iata_icao_codes/         ← 子 skill:IATA 翻译
    └── SKILL.md                          · 30+ 城市 IATA+ICAO 对照 + 模糊处理
```

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
  │  → ❌ 走 flight-booking skill(本 skill **不**接)
  │
  ▼
读 SKILL.md(必读)
  │
  ▼
用户说 IATA / ICAO / 机场名?
  │  是 → 加载子 skill flight-query:iata_icao_codes
  │  否 → 城市直接用中文
  │
  ▼
准备调 queryFlightBasic?
  │  是 → 加载子 skill flight-query:query_flight_basic
  │       (input schema / output schema / NL 映射 / 真实样本字段)
  │
  ▼
拼 JSON-RPC envelope, 用 Bash + curl 调 MCP
  │  · 端到端模板直接抄 examples/01~05.sh
  │  · MCP_TOKEN 从 <runtime-context> 块取(系统注入),不瞎编
  │
  ▼
解析响应
  │  · isError=true → 业务错误,按 errorMsg 提示用户
  │  · flightList=[] → 提示放宽(换日期/换舱等/换 OD)
  │  · 正常 → 用 legs[].depTime/arrTime + flightList[].lowestPrice/lowestCabinName 渲染 Markdown 表
  │
  ▼
需要"飞机大小/飞行时长"二次筛选?
  │  是 → 调 filterFlightList(planeSize / maxDuration),不重调 TMS
  │
  ▼
要"选航班/选舱/下单"?
  │  是 → 引导用户走 flight-booking skill
  │       本 skill 只展示 flightList 顶层信息(航班号/航司/时刻/价格/舱等)
  │       **不**渲染舱位详情/退改规则/行李额(`notIncluded` 字段明示)
```

---

## 3. 30 秒速记(LLM 必背)

| 字段 | 值 |
|---|---|
| 端点 | `https://traveldev.feiheair.com/api/mcp` |
| 协议 | JSON-RPC 2.0 over HTTP |
| Auth header | `token: <v>` 或 `Authorization: Bearer <v>` 任选 |
| 响应路径 | `.result.content[0].text` → JSON 字符串 → 二次 parse |
| 业务错误标志 | `.result.isError === true` + `text` 是错误消息 |
| 主工具 | `queryFlightBasic`(TMS 调上游) |
| 次工具 | `filterFlightList`(内存筛选,planeSize/maxDuration) |
| 城市入参 | **中文原话**(不接受 IATA 码) |
| 日期格式 | `yyyy-MM-dd`,月日必须补零 |
| 铁律 | 改 OD/日期/舱等 → **重调** queryFlightBasic,不调 filterFlightList |
| 不接 | 选舱/填人/核价/下单/订单 → `flight-booking` skill |

---

## 4. 真实样本快速索引(LLM 调工具前后必读)

| 想做什么 | 读哪个样本 |
|---|---|
| 拼请求体 / 看顶层 envelope | `tools/samples/req.*.json` |
| 看全量返回结构(193 条) | `queryFlightBasic.北京-上海.oneway.full.json` |
| 看 cheapest=true 怎么推导 searchType | `queryFlightBasic.上海-深圳.oneway.cheapest.json` |
| 看 filteredCount=0 时长啥样 | `queryFlightBasic.北京-上海.oneway.filtered.json` |
| 看业务错误长啥样 | `queryFlightBasic.北京-上海.roundtrip.recommended.json` |

---

## 5. 子 skill 加载时机速查

| LLM 此刻在... | 加载哪个子 skill |
|---|---|
| 准备调 `queryFlightBasic` | `flight-query:query_flight_basic`(输入输出 + 真实字段) |
| 用户说 "BJS / PEK / 浦东" | `flight-query:iata_icao_codes`(翻译) |
| 用户说 "选第一个" / "下单" | **不**加载任何子 skill — 引导走 `flight-booking` skill |
| 报错 "请求航信超时" | **不**加载 — 父 skill §4 已写处置 |

---

## 6. 与 flight-booking 的边界

| 本 skill 负责 | flight-booking 负责 |
|---|---|
| 搜航班(OD+日期+筛选) | 选航班(chooseFlight) |
| 渲染顶层 flightList 信息(航班号/航司/时刻/价格) | 渲染舱位详情(cabinList) |
| 内存二次筛选(planeSize / maxDuration) | 退改规则详情 / 行李额 / 乘机人档案 |
| 改条件重查 / 业务错误兜底 | 核价 / 差标决策 / 订单预览 / 下单 / 订单详情 |

`notIncluded` 字段(`tools/samples/*.json` 里都有)明示了边界 — 严格遵守,**不**越界。
