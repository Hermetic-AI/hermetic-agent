# SKILL-INDEX — flight-query-v3 一页导航

> **v3 一页 cheat sheet**。先看这张图,再决定读哪个文件。
> 不知道读什么 / 上下文紧张时,**只看本文件**就够开干。

---

## 1. 文件树(本 skill 自包含)

```
work/shared/skills/flight-query-v3/         ← 你在这里
├── SKILL.md                                ← 核心层(必读,~280 行)
│                                            · 业务规则 · 工具清单 · 卡片规范 · 铁律 · 边界
├── SKILL-INDEX.md                          ← 本文件(导航)
├── CHANGELOG.md                            ← v2 → v3 变更记录
└── flight-query-v3.iata_icao_codes/        ← 子 skill:IATA 翻译
    └── SKILL.md                            · 30+ 城市 IATA+ICAO 对照 + 模糊处理
```

> **v3 不再有 `tools/*.json` / `examples/*.sh` / `query_flight_basic/` 子 skill**。
> opencode 加载 MCP server 时会自动把工具的 `inputSchema` / `outputSchema` 注入 LLM context,LLM 直接读 schema 拼参数。
> 协议层(URL / header / token)在 `work/mcp/servers.json`,LLM 看不见。

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
读 SKILL.md(必读,~280 行)
  │
  ▼
用户说 IATA / ICAO / 机场名?
  │  是 → 加载子 skill flight-query-v3:iata_icao_codes
  │  否 → 城市直接用中文
  │
  ▼
准备调 queryFlightBasic?
  │  是 → 工具描述里有 inputSchema / outputSchema
  │       (opencode 加载 MCP server 时已自动注入 LLM context)
  │       LLM 拼 JSON 参数 → opencode 调原生工具
  │
  ▼
解析响应
  │  · isError=true → 业务错误,按 errorMsg 推 CANNOT_ORDER 卡片
  │  · flightList=[] → 推 CANNOT_ORDER 卡片
  │  · 正常 → 用 §5.2 字段映射表 整理 FLIGHT_RESULT 卡片
  │
  ▼
需要"飞机大小/飞行时长"二次筛选?
  │  是 → 调 filterFlightList(planeSize / maxDuration),不重调 TMS
  │
  ▼
要"选航班/选舱/下单"?
  │  是 → 引导用户走 flight-booking skill
  │       本 skill 只展示 flightList 顶层信息(航班号/航司/时刻/价格/舱等)
  │       **不**渲染舱位详情/退改规则/行李额
```

---

## 3. 30 秒速记(LLM 必背)

| 字段 | 值 |
|---|---|
| 主工具 | `queryFlightBasic`(TMS 调上游) |
| 次工具 | `filterFlightList`(内存筛选,planeSize/maxDuration) |
| 工具入参 | **中文原话**(不接受 IATA 码) |
| 日期格式 | `yyyy-MM-dd`,月日必须补零 |
| 铁律 | 改 OD/日期/舱等 → **重调** queryFlightBasic,不调 filterFlightList |
| 不接 | 选舱/填人/核价/下单/订单 → `flight-booking` skill |
| 协议在哪 | `work/mcp/servers.json`(LLM **不要**关心,只调工具) |
| 卡片 | `ask_user` 工具推 `FLIGHT_RESULT` / `CANNOT_ORDER` |

---

## 4. 与 flight-booking 的边界

| 本 skill 负责 | flight-booking 负责 |
|---|---|
| 搜航班(OD+日期+筛选) | 选航班(chooseFlight) |
| 渲染顶层 flightList 信息(航班号/航司/时刻/价格) | 渲染舱位详情(cabinList) |
| 内存二次筛选(planeSize / maxDuration) | 退改规则详情 / 行李额 / 乘机人档案 |
| 改条件重查 / 业务错误兜底 | 核价 / 差标决策 / 订单预览 / 下单 / 订单详情 |

---

## 5. 子 skill 加载时机速查

| LLM 此刻在... | 加载哪个子 skill |
|---|---|
| 用户说 "BJS / PEK / 浦东" | `flight-query-v3:iata_icao_codes`(翻译) |
| 用户说 "选第一个" / "下单" | **不**加载任何子 skill — 引导走 `flight-booking` skill |
| 报错 "请求航信超时" | **不**加载 — 父 skill §3 已写处置 |
| 准备调 `queryFlightBasic` | **不**加载 — 工具 `inputSchema` 已被 opencode 注入 LLM context |

---

## 6. 与 v2 的核心差异(LLM / 工程师速记)

| 项 | v2 (legacy) | v3 |
|---|---|---|
| LLM 调 MCP 的方式 | 自己写 `Bash` + `curl` | opencode 原生工具调用 |
| Token 怎么传 | LLM 从 `<runtime-context>` 块取 | opencode 读 `servers.json` 的 `headers` |
| Skill 里有 URL 吗 | ✅ `https://traveldev.feiheair.com/api/mcp` | ❌ **不**写 |
| Skill 里有 `Authorization` 吗 | ✅ | ❌ **不**写 |
| Skill 里有 `JSON-RPC` / `envelope` 吗 | ✅ | ❌ **不**写 |
| 改 MCP 端点 | 改 skill + 改 launch | 改 `servers.json`(skill 一字不动) |
| 工具 schema 来源 | skill 内嵌 `tools/*.json` | opencode `tools/list` 自动注入 |
| 输出卡片 | ✅ `FLIGHT_RESULT` | ✅ `FLIGHT_RESULT`(内容一致) |

---

**最后更新**:2026-06-05
**对应 scenario**:`work/scenarios/flight_query_v3.scenario.yaml`
**MCP 配置**:`work/mcp/servers.json`
