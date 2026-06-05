---
name: flight-query-v3
description: "通过 MCP 工具查询国内航班(单程/往返)。v3 全新设计:Skill 只说业务规则,不教 LLM 调协议。MCP 端点 / header / JSON-RPC 全在 work/mcp/servers.json 里,opencode 启动时原生加载 queryFlightBasic / filterFlightList 给 LLM 直接调,无需 curl / Bash。输出走 AUIP 卡片(card_type=FLIGHT_RESULT / CANNOT_ORDER)。选舱/填人/核价/下单走 flight-booking skill。"
version: 3.0.0
allowed-tools:
  - Read
  - Grep
  - Glob
argument-hint: "[出发地] [到达地] [出发日期] [可选: 返程日期] [可选: 筛选条件]"
---

# Flight Query Agent Skill (v3) — Pure Business Logic

> **v3 核心转变**:**Skill 不再管协议**。本文档**只教业务**:
> - 什么时候调哪个 MCP 工具
> - 工具的入参怎么从用户话里抽
> - 工具返回的 `flightList` 怎么解析
> - 怎么用 AUIP 卡片把结果推给前端
>
> **本文档不会写**:
> - ❌ endpoint URL
> - ❌ HTTP header
> - ❌ JSON-RPC envelope
> - ❌ curl / Bash 命令
> - ❌ token 透传
>
> 以上 wire-level 细节**全部**在 `work/mcp/servers.json` 里(见 `work/mcp/README.md`)。
> LLM 拿到工具描述后,直接调原生工具,opencode runtime 负责协议。

---

## 1. 工具总览(本 skill 调 2 个)

| MCP 工具 | 何时用 | 备注 |
|---|---|---|
| `queryFlightBasic` | **首调 / 改条件重调** — 改 OD/日期/舱等/航司/限价/直飞/排序/时段/含餐/退改/差标**任何一个** → 必重调本工具 | 工具描述会注明完整入参 schema;LLM 实际调时按 schema 拼 JSON |
| `filterFlightList` | **次调(内存筛选)** — 在已加载的 `flightList` 上做 TMS 不支持的维度二次筛选(飞机大小、飞行时长) | 改 OD/日期/舱等 → **不**调本工具,重调 `queryFlightBasic` |

> **完整入参 schema / 输出字段**:opencode 加载 MCP server 时会调 `tools/list` 拿到所有工具的 schema 并注入 LLM context;LLM 直接读工具描述拼参数。**Skill 不重复 schema**。

### 1.1 路由决策(LLM 行为)

```
用户: "明天北京到上海最便宜的,只要东航,含行李,上午走"
   │
   ▼ 解析:OD=北京→上海 / 明天 / 舱等=经济 / 航司=东航 / 行李=是 / 时段=MORNING / cheapest=true
   │
   ▼ 这些条件都是 queryFlightBasic 一次能查的 → 调一次 queryFlightBasic
   │
   ▼ 返回 flightList
   │
   ▼ 用户追加: "只要大飞机的" → planeSize 不在 queryFlightBasic 里
   │
   ▼ 调 filterFlightList(内存筛选, 不调 TMS)
```

> **铁律**:改 OD/日期/舱等/航司/限价/直飞/排序 → **重调** `queryFlightBasic`,**不**在 `filterFlightList` 上做客户端过滤。
> `filterFlightList` **仅**用于 TMS 不支持的维度(`planeSize` / `maxDuration`)或用户追加简单条件。

### 1.2 不可用工具(本 skill 不接)

`buildOrderPreview` / `fillPassenger` / `validateBookingInfo` / `getDefaultContact` / `bindCostCenter` / `listCostCenters` / `getOrderDetail` / `listTripApplications` / `recordPolicyUserDecision` / `resetBookingSession` / `getTripApplicationDetail` / `getWeather` / `read_skill` → 13 个其他工具本 skill **不接**,归 `flight-booking` skill。
LLM 看到用户要"选舱/下单/查订单" → **不**调本 skill 范围,引导走 `flight-booking`。

---

## 2. 城市/机场代码

`queryFlightBasic.departureCity` / `.arrivalCity` 接受**中文城市原话**(如 `"北京"`、`"上海"`)。
**不接受** IATA 码 / ICAO 码 / 机场名(给 IATA/ICAO 码 LLM 要先翻译成中文)。

| 用户原话 | 工具入参 | 备注 |
|---|---|---|
| 北京 / BJS / PEK / PKX / 首都 / 大兴 | `北京` | 城市码 BJS 含首都+大兴;LLM 不强制区分机场 |
| 上海 / SHA / PVG / 虹桥 / 浦东 | `上海` | 城市码 SHA 含虹桥+浦东 |
| (其他) | **加载 `flight-query-v3:iata_icao_codes` 子 skill 查表翻译** | 表里没有 → 主动问用户 |

完整 IATA/ICAO 对照 → 加载 `flight-query-v3:iata_icao_codes` 子 skill。

---

## 3. 错误处理

| 现象 | 处置 |
|---|---|
| 工具返回 `isError=true` + 业务级 `errorMsg`(如"请求航信超时") | 按 `errorMsg` 提示用户;走 §5.1.4 推 `CANNOT_ORDER` 卡片 |
| 工具返回 `flightList=[]` 或 `filteredCount=0` | 推 `CANNOT_ORDER` 卡片(§5.1.4);不推空 `FLIGHT_RESULT` |
| opencode 报 `401` / `token invalid` | "权限配置异常,联系管理员" — **不**重试(无 token 也无法重试) |
| opencode 报 `-32099 访问频率过高` | 退避 ~1s 重试 1 次;仍失败告知"系统繁忙" |
| opencode 报 `network timeout` | 重试 1 次;仍失败告知稍后重试 |
| MCP 端点连不上(`ECONNREFUSED` / `ENOTFOUND`) | "机票查询服务暂时不可用, 请稍后重试"(§5.1.4) |

> **v3 优势**:协议层错误(opencode 拦截)与业务层错误(MCP 工具返回 `isError`)**自动分离** — LLM 看到的是结构化结果,不用自己解析 HTTP 状态码、JSON-RPC `error.code`、curl exit code。Skill 不再写错误处置细节,只教"工具返回啥 → 卡片推啥"。

---

## 4. 铁律(精简)

1. **改 OD/日期/舱等/航司/限价/直飞/排序/时段/退改/差标 → 重调 `queryFlightBasic`**,**不**在 `filterFlightList` 上做客户端过滤
2. **`filterFlightList` 仅用于 TMS 不支持的维度**(`planeSize` / `maxDuration`)或用户追加简单条件
3. **绝对不要自猜日期**(包括回程)— 用户没说 `returnDate` 就追问
4. **相对日期**用当前日期转 `yyyy-MM-dd`,月日**必须补零**(`2026-06-05`,**不**是 `2026-6-5`)
5. **模糊偏好**("挑一个/最划算")老实说"本工具返回的是全量 / 含 X 维度最低价;以下是筛选结果",**不**瞎编
6. **城市用中文原话**;IATA/ICAO/机场名先翻译(见 §2)
7. **调工具失败 → 不编造**,老实说"查询失败"
8. **本 skill 仅查票** → 选航班/选舱/填人/核价/下单走 `flight-booking` skill
9. **必须用 AUIP 卡片**:`queryFlightBasic` 拿到 `flightList` 后,**必须**调 `ask_user` 工具发 `card_type: "FLIGHT_RESULT"`,前端 `FlightResultCard` 渲染 — **不要**再用 Markdown 表格发回(老方案已废,见 §5)

---

## 5. 输出格式 — FLIGHT_RESULT 卡片 (AUIP)

> LLM 拿到工具返回的 `flightList` 后,**必须**调 `ask_user` 工具,把 `card_type` 设为 `FLIGHT_RESULT`,把 flightList 整理成"方案(plan)→ 推荐航班(flight)[]"两层结构,前端 `FlightResultCard` 会自动按方案分组渲染。
>
> **不要在 chat text 里重复发整张表**。`text` 事件只放一句简短的总结(例: "按你需求筛出 3 个方案, 详见下方卡片")。

### 5.1 调 `ask_user` 模板

```json
{
  "name": "ask_user",
  "input": {
    "card_type": "FLIGHT_RESULT",
    "title": "机票已发送",
    "dismissible": false,
    "body": {
      "summary": {
        "totalCount": 50,
        "filteredCount": 10,
        "searchType": "全量查询",
        "depCity": "北京",
        "arrCity": "上海",
        "depDate": "2026-06-06",
        "weather": "北京小雨 12~20℃, 上海阴 20~28℃"
      },
      "plans": [
        {
          "id": "fastest",
          "title": "最快抵达",
          "subtitle": "用时最短",
          "criteria": "duration",
          "flights": [
            {
              "flightId": "CA1501-20260606-0900",
              "flightNo": "CA1501",
              "shareFlight": false,
              "shareInfo": null,
              "airline": { "code": "CA", "name": "中国国际航空" },
              "aircraft": "波音 737-800",
              "date": "2026-06-06",
              "departure": {
                "city": "北京", "airport": "首都国际机场",
                "airportCode": "PEK", "terminal": "T3",
                "time": "09:00"
              },
              "arrival": {
                "city": "上海", "airport": "浦东国际机场",
                "airportCode": "PVG", "terminal": "T2",
                "time": "11:20"
              },
              "duration": "2h20m",
              "stops": 0,
              "cabin": "经济舱",
              "cabinClass": "ECONOMY",
              "meal": "早餐",
              "price": 550,
              "fullPrice": 1630,
              "tags": ["国航5256413", "便宜437元"]
            }
          ]
        }
      ]
    }
  }
}
```

### 5.2 字段映射(MCP `flightList[0]` → AUIP `flights[]`)

> **本表是 LLM 整理卡片时的"翻译表"**。拿到 MCP 工具返回后,把每个字段按下面 1:1 填进 AUIP `flights[]`。

| AUIP 字段 | 来源(MCP `flightList[0]`) | 必填 | 备注 |
|---|---|---|---|
| `flightId` | `flightId`(顶层) | ✅ | 用作主键;`flightId` 即 `flightNo` |
| `flightNo` | `flightNo` | ✅ | 显示用 |
| `shareFlight` | `shareFlight`(顶层) | ❌ | `true` 时 `airline.name` 用 "厦航(共享MU5116)" 形式 |
| `airline.code` | `airId`(顶层) | ✅ | "CA" / "MU" / "MF" 等 |
| `airline.name` | `legs[0].airlineName` | ✅ | "中国国际航空" |
| `aircraft` | `legs[0].aircraftName` | ✅ | 去掉 "(大)/(中)/(小)" 后缀 |
| `date` | `depDate` | ✅ | yyyy-MM-dd |
| `departure.time` | `legs[0].depTime` | ✅ | HH:MM |
| `arrival.time` | `legs[0].arrTime` | ✅ | HH:MM |
| `departure.airport` | `legs[0].depAirportName` | ✅ | "首都国际机场" |
| `arrival.airport` | `legs[0].arrAirportName` | ✅ | "浦东国际机场" |
| `departure.airportCode` | `depAirportCode`(顶层) | ✅ | "PEK" / "PKX" |
| `arrival.airportCode` | `arrAirportCode`(顶层) | ✅ | "PVG" / "SHA" |
| `departure.terminal` | `legs[0].depTerminal` | ❌ | "T2" / null |
| `arrival.terminal` | `legs[0].arrTerminal` | ❌ | "T2" |
| `duration` | `totalDuration` | ✅ | "2h20m" |
| `stops` | `stopCount`(顶层) | ✅ | 0 = 直飞 |
| `cabin` | `lowestCabinName` | ✅ | "经济舱" |
| `cabinClass` | `lowestCabinName` → 枚举 | ❌ | ECONOMY / BUSINESS / FIRST |
| `meal` | `legs[0].meal`(bool) → "是"/"否" | ❌ | 也可保留中文 "早餐" |
| `price` | `lowestPrice` | ✅ | 数字(元) |
| `fullPrice` | `fullPrice` | ❌ | 全价票面价 |
| `tags` | LLM 派生 | ❌ | 例: ["最便宜", "1h55m ⚡"] |

> **重要**:v3 下 LLM 是从工具 schema 的 `outputSchema` 字段读出参结构,不需要 skill 内嵌。Skill 只教"业务映射规则"。

### 5.3 方案(plan)分组规则

> **每张卡 ≤ 3 个方案**,每个方案 ≤ 3 个航班,避免长卡片劝退用户。
> 全部 `flightList` 数据通过 `summary.totalCount / filteredCount` 在头部展示,用户点"更多 ▾"展开完整列表。

**默认方案维度(按用户语义切换)**:

| 用户偏好关键词 | 方案1 维度 | 方案2 维度 | 方案3 维度 |
|---|---|---|---|
| (无偏好 / "看看有哪些") | 最快抵达(`duration` 升序) | 最便宜(`lowestPrice` 升序) | 直飞首选(`shareFlight=false` + 大机型) |
| "最快" | 最短时长 | 早班直飞 | (省略) |
| "最便宜" | 最低价 | 直飞首选 | (省略) |
| "上午 / 早班" | 06:00-12:00 起飞 | 直飞首选 | (省略) |
| "下午" | 12:00-18:00 起飞 | 直飞首选 | (省略) |
| "晚班" | 18:00-24:00 起飞 | 直飞首选 | (省略) |
| "国航 / 厦航 / 东航 ..." | 指定航司 + 价格升序 | 指定航司 + 时刻 | (省略) |

> 1. 用户没偏好时**永远**推"最快 / 最便宜 / 直飞首选" 3 方案。
> 2. 任何空结果(`flightList=[]`) → 推 `CANNOT_ORDER` 卡片,message 写 "没找到符合条件的航班";**不要**推空 `FLIGHT_RESULT`。

### 5.4 错误 / 空结果

| 情况 | 处置 |
|---|---|
| `flightList=[]` 且 `filteredCount=0` | 推 `CANNOT_ORDER` card(title: "暂无符合条件的航班", body.message: 按 §3 错误处置) |
| 工具返回 `isError=true` | 推 `CANNOT_ORDER` card,message = 业务 `errorMsg` |
| 4xx / 5xx(连续 2 次) | 推 `CANNOT_ORDER` card,message = "机票查询服务暂时不可用, 请稍后重试" |
| `flightList` 长度 ≤ 3 | 推 1 个方案 `plans=[{id:"recommended", title:"为你找到", flights: 全部}]` |

---

## 6. Skill ↔ MCP 边界(本 skill 不再做的事)

> **v2 vs v3 核心差异**。这一节是给"读过 v2 的 LLM/工程师"看的"我**不**做啥"清单。

| 事项 | v2 (legacy) | v3 (本 skill) |
|---|---|---|
| 教 LLM 用 `Bash` 调 `curl` | ✅ 教 | ❌ **不**教(opencode 调原生工具) |
| Skill 内嵌 endpoint URL | ✅ `https://traveldev.feiheair.com/api/mcp` | ❌ **不**写 |
| Skill 内嵌 `Authorization` / `token` header | ✅ 教 LLM 从 `<runtime-context>` 块取 | ❌ **不**写(由 `work/mcp/servers.json` 处理) |
| Skill 内嵌 `examples/*.sh` curl 模板 | ✅ 5 个模板 | ❌ **不**写(用工具描述代替) |
| Skill 内嵌 `tools/samples/*.json` 真实响应 | ✅ 4 份 | ❌ **不**写(工具 `outputSchema` 即权威) |
| 教业务规则(什么时候调、改条件重调、铁律) | ✅ | ✅(本 skill 的全部内容) |
| 教输出卡片规范(`FLIGHT_RESULT` 字段映射、方案分组) | ✅ §5.1 | ✅ §5(内容一致,只是来源换成工具 schema) |

详细变更记录见 `CHANGELOG.md`。

---

## 7. 子 skill(按需加载)

| 子 skill 名 | 加载时机 | 内容 |
|---|---|---|
| `flight-query-v3:iata_icao_codes` | 用户说 IATA/ICAO/机场名要翻译 / 未识别城市 | 30+ 城市 IATA+ICAO 对照 + 模糊处理 |

> v3 不再需要 `query_flight_basic` 子 skill —— opencode 加载 MCP server 时会把工具的 `inputSchema` / `outputSchema` 自动注入 LLM context,LLM 调工具前直接读 schema 拼参数即可。

---

## 8. 版本与变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| **3.0.0** | 2026-06-05 | **协议层完全外包**:<br>1. **不再教 LLM 调协议** — endpoint / header / JSON-RPC / curl / Bash 全部从 skill 删除,LLM 看不到任何 wire-level 概念<br>2. **不再内嵌 `tools/*.json` / `examples/*.sh`** — opencode 加载 MCP server 时自动注入工具 schema 给 LLM<br>3. **依赖 `work/mcp/servers.json`** — 协议层配置集中在那里,改端点不动 skill<br>4. **保留业务规则**(铁律 / 卡片规范 / 字段映射 / 方案分组)— 这些是 LLM 该学的<br>5. **`ask_user` 卡片规范不变** — `FLIGHT_RESULT` 字段映射表直接搬过来,LLM 整理卡片时按表填<br>6. **新增 §6 "Skill ↔ MCP 边界"** — 给熟悉 v2 的人"我**不**做啥"清单<br>7. **去掉 `query_flight_basic` 子 skill** — opencode 自动注入工具 schema 取代 |
