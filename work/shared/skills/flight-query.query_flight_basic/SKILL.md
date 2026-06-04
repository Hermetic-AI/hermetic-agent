---
name: flight-query.query_flight_basic
description: "`queryFlightBasic` 工具的深度规范 — 完整 input schema、所有 enum 值、输出字段说明、NL→param 映射、use case。schema 摘录自 skill 内 `tools/flight-mcp.json`(MCP `tools/list` 真实响应)。**冲突时以源 JSON 为准**。"
version: 1.5.0
allowed-tools:
  - Bash
---

# queryFlightBasic 深度规范 (On-Demand)

> **加载时机**:父 skill `flight-query` 提示"详见 `flight-query:query_flight_basic`"时;
> 或 LLM 主动判断需要完整 schema 时。
>
> **本文档不重复**:endpoint / 协议 / token 契约(见父 skill `flight-query` §1 §2)。
>
> **schema 源**:skill 根 `tools/flight-mcp.json` →
> `result.tools[?(@.name=="queryFlightBasic")].inputSchema`
>
> **本文件是源 JSON 的可读摘录 + 使用说明**,不是独立来源。

---

## 1. 工具元信息

| 字段 | 值 | 来源 |
|---|---|---|
| 名称 | `queryFlightBasic` | `tools/flight-mcp.json` |
| 描述(原文) | 【TMS 查询】调 TMS 查航班。支持舱等/行李/退改/差标/航司/限价/直飞/时段/含餐/排序。首次查询时把用户所有条件一次性传入。改出发/到达/日期/舱等 → 必须重调本工具。不支持:飞机大小、飞行时长 → 查完后用 `filterFlightList` 或 LLM 自行筛选。模糊偏好("哪个最划算""帮我推荐") → LLM 直接分析返回的航班列表,不调工具。 | `tools/flight-mcp.json` |
| 类别 | TMS 查询(调上游);首次查 / 改条件查 | 描述推论 |
| 配套 | 同会话内可用 `filterFlightList` 在结果上做内存筛选(planeSize / maxDuration) | 父 skill §3 |
| 幂等 | 纯查询;`sessionId` 由 MCP 端管(在本工具的返回里给) | 描述 |

---

## 2. 输入参数 schema(摘自 `tools/flight-mcp.json`)

### 2.1 必填(3 个)

| 字段 | 类型 | 说明(原文) |
|---|---|---|
| `departureCity` | string | 出发城市,**用用户原话**,如 `北京`、`深圳` |
| `arrivalCity` | string | 到达城市,**用用户原话**,如 `上海`、`成都` |
| `departureDate` | string | 出发日期,格式 `yyyy-MM-dd`,**月份和日期必须补零**,如 `2026-05-01` 而非 `2026-5-1`。用户说"明天/后天"等相对日期时,需结合当前日期转换为绝对日期;仅日期部分写入本参数,**时段部分**(上午/下午/晚上)写 `departureDayPart` |

### 2.2 可选(按用途分组)

#### 往返

| 字段 | 类型 | 说明 |
|---|---|---|
| `returnDate` | string (date) | 回程日期,`yyyy-MM-dd`。**往返时必传**(含 FREE 模式首次查去程),单程不传。FREE 模式首次查去程时也应传入,系统据此标记往返行程。**禁止自猜** |
| `roundTripListMode` | enum `RECOMMENDED` \| `FREE` | 往返列表模式。RECOMMENDED=去程回程打包推荐(默认),FREE=自由组合/分段订。用户明确要分段订或先看去程时传 FREE |

#### 价格 / 排序 / 限额

| 字段 | 类型 | 说明 |
|---|---|---|
| `cheapest` | boolean | 是否只返回最低价航班(1 条)。`true`=最便宜 1 条,`false` 或不传=返回多条 |
| `maxPrice` | int | 最高价(元),如 `800`。超出此价格的航班不返回 |
| `sortBy` | enum `PRICE` \| `ARRIVAL_TIME` \| `DURATION` \| `REFUND_FLEXIBILITY` | 排序方式。PRICE=最低价(默认),ARRIVAL_TIME=最快到达,DURATION=飞行最短,REFUND_FLEXIBILITY=退改最灵活 |

#### 舱等 / 行李 / 餐食

| 字段 | 类型 | 说明 |
|---|---|---|
| `cabinClass` | enum `ECONOMY` \| `FULL_ECONOMY` \| `BUSINESS` \| `FIRST` | 舱等。ECONOMY=经济舱(默认),FULL_ECONOMY=全价经济舱,BUSINESS=公务舱,FIRST=头等舱 |
| `baggage` | boolean | 是否筛选含托运行李的最低价。`true`=含行李最低价,`false` 或不传=不限行李的最低价 |
| `requireMeal` | boolean | 是否筛选含餐食的最低价。`true`=含餐最低价(正餐/小吃),`false` 或不传=不限餐食 |

#### 航司

| 字段 | 类型 | 说明 |
|---|---|---|
| `airlineName` | string | 指定航司,中文或代码均可,如 `南航`、`CZ`。**用户原样传入** |
| `excludeAirlineKeywords` | string | 排除廉航关键词,逗号分隔,如 `春秋,中联航` |

#### 出发时段

| 字段 | 类型 | 说明 |
|---|---|---|
| `departureDayPart` | enum `MORNING` \| `AFTERNOON` \| `EVENING` | 出发时段。MORNING=上午(00:00-11:59),AFTERNOON=下午(12:00-17:59),EVENING=晚上(18:00-23:59)。**与 `depTimeStart` / `depTimeEnd` 二选一,优先用本参数**。用户说"明天下午""后天上午"等同时含日期和时段时,日期写 `departureDate`,时段写入本参数 |
| `depTimeStart` | string (HH:mm) | 出发时间起,如 `06:00`。与 `departureDayPart` 二选一 |
| `depTimeEnd` | string (HH:mm) | 出发时间止,如 `12:00`。与 `departureDayPart` 二选一 |

#### 直飞 / 退改 / 差标

| 字段 | 类型 | 说明 |
|---|---|---|
| `nonStop` | boolean | 是否仅返回不经停航班。`true`=排除经停航班 |
| `freeRefund` | boolean | 是否仅返回免费退改的航班。`true`=仅退改费=0 |
| `refundable` | boolean | 是否仅返回可退改的航班(含非免费退改)。`true`=退改费≥0(含免费退改)。用户说"可退/能退/能改"时设为 `true`;说"免费退/退改费=0"时用 `freeRefund` |
| `policyCompliant` | boolean | 是否仅返回差标合规航班。`true`=仅差旅政策合规 |

#### 意图标签(仅日志,可选)

| 字段 | 类型 | 说明 |
|---|---|---|
| `searchType` | enum (15 个中文值) | 查询意图标签,**仅供日志展示,不参与筛选排序逻辑**。可选值见 §2.3。**建议:优先填好 `cheapest` / `cabinClass` / `baggage` 等驱动参数,`searchType` 选填即可** |

### 2.3 `searchType` enum(15 个值,摘自 `tools/flight-mcp.json`)

> ⚠️ v1.4.0 SKILL.md 声称"已 MCP Inspector 确认 `全量查询`"是**错的** — 没有真实抓包。
> 本枚举是直接抄源 JSON 的 `enum` 字段,**未实测**各个值是否生效。

| 值 | 含义(原文 / 推论) |
|---|---|
| `全量查询` | 默认,无特殊筛选 |
| `经济舱最低价` | 推论:经济舱 1 条最低价 |
| `经济舱带行李最低价` | 推论:经济舱 + 含行李 1 条最低价 |
| `经济舱有正餐最低价` | 推论:经济舱 + 含正餐 1 条最低价 |
| `全价经济最低价` | 推论:FULL_ECONOMY 1 条最低价 |
| `公务舱最低价` | 推论:BUSINESS 1 条最低价 |
| `公务舱带行李最低价` | 推论:BUSINESS + 含行李 1 条最低价 |
| `头等舱最低价` | 推论:FIRST 1 条最低价 |
| `指定航司最低价` | 推论:配合 `airlineName` 用 |
| `排除廉航最低价` | 推论:配合 `excludeAirlineKeywords` 用 |
| `指定时段最低价` | 推论:配合 `departureDayPart` / `depTimeStart` 用 |
| `最高限价` | 推论:配合 `maxPrice` 用 |
| `免费退改最低价` | 推论:配合 `freeRefund: true` 用 |
| `可退改最低价` | 推论:配合 `refundable: true` 用 |
| `差标合规最低价` | 推论:配合 `policyCompliant: true` 用 |
| `时间最短` | 推论:配合 `sortBy: DURATION` 用 |
| `差标以内退改费最低` | 推论:差标 + 退改组合 |

> **未实测**:哪些值会被服务端真识别,需要服务端确认。
> **建议**:**默认不传** `searchType`,优先用 §2.2 的驱动参数(更明确)。需要时再补。

---

## 3. JSON-RPC envelope 模板

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "queryFlightBasic",
    "arguments": { ... }
  }
}
```

完整 curl 模板见父 skill `flight-query` §1.5(本 skill 不重复)。

---

## 4. 输出结构(精简)

> ⚠️ 源 JSON 的 `outputSchema` 是空 `{}`,**没有**定义输出 schema。
> v1.4.0 列的 `flightList` / `cabins` / `serialNumber` 等结构是**历史 v1.4.0 编的**,**本版撤回**。
> 实际返回结构以 MCP 服务端实际响应为准 — **未实测**。

调用方应:

1. 读 `.result.content[0].text` — 是 JSON 字符串,需二次 `JSON.parse`
2. 按服务端实际返回字段渲染;**不要**依赖本文件历史版本列的字段
3. 如需稳定 schema,等 MCP 端补 `outputSchema`

---

## 5. NL → 参数映射

### 5.1 城市

| 用户原话 | 转换 | 最终 `departureCity` / `arrivalCity` |
|---|---|---|
| 北京 | (已经是中文) | `北京` |
| BJS / PEK / PKX / 首都 / 大兴 | 查父 skill §4.2 → `北京` | `北京` |
| 上海 | (已经是中文) | `上海` |
| SHA / PVG / 虹桥 / 浦东 | 查父 skill §4.2 → `上海` | `上海` |
| (其他) | 加载 `flight-query:iata_icao_codes` 子 skill | 表里没有 → 主动问用户 |

> **歧义**: 用户说"虹桥/浦东/首都/大兴"等具体机场 → 翻译成"上海"/"北京"等城市名,
> 在结果展示时备注"按 XX 机场搜索"。

### 5.2 日期

- 相对日期(明天/后天/大后天/下周X)→ 用**当前日期**转 `yyyy-MM-dd`,**月份/日期必须补零**(`2026-06-04`)
- "明天下午" → 日期进 `departureDate`,时段进 `departureDayPart: AFTERNOON`
- 不知道日期 → 主动问,**禁止自猜**
- 往返缺 `returnDate` → 必问,**禁止自猜**

### 5.3 舱等

| 用户原话 | `cabinClass` |
|---|---|
| 经济 / 经济舱 | `ECONOMY` |
| 全价经济 | `FULL_ECONOMY` |
| 公务 / 商务 / 公务舱 | `BUSINESS` |
| 头等 / 头等舱 | `FIRST` |
| 不限 | 省略 |

### 5.4 退改

| 用户原话 | 字段 |
|---|---|
| "可退/能退/能改" / "退改灵活" | `refundable: true` |
| "免费退/退改费=0" | `freeRefund: true` |
| "退改最灵活" | `sortBy: REFUND_FLEXIBILITY` |

### 5.5 时段

| 用户原话 | `departureDayPart` |
|---|---|
| 上午 / 早上 / 白天早 | `MORNING` |
| 下午 | `AFTERNOON` |
| 晚上 / 夜里 | `EVENING` |
| "6 点到 12 点" | `depTimeStart: "06:00"`, `depTimeEnd: "12:00"` |
| "明天下午" | 日期进 `departureDate`,时段进 `departureDayPart: AFTERNOON` |

### 5.6 排序

| 用户原话 | `sortBy` |
|---|---|
| 最低价 / 最便宜 / 最划算 | `PRICE`(默认,可省略) |
| 最快到达 | `ARRIVAL_TIME` |
| 飞行最短 / 时长短 | `DURATION` |
| 退改最灵活 | `REFUND_FLEXIBILITY` |

### 5.7 其他

| 用户原话 | 字段 |
|---|---|
| "最便宜/最低价" | `cheapest: true` |
| "要直飞/不经停" | `nonStop: true` |
| "含行李/有托运" | `baggage: true` |
| "含餐/有餐食" | `requireMeal: true` |
| "只要南航" | `airlineName: "南航"` |
| "不要春秋" | `excludeAirlineKeywords: "春秋"` |
| "800 以内" | `maxPrice: 800` |
| "差标合规" | `policyCompliant: true` |
| "先看去程,回程我自己挑" | `roundTripListMode: "FREE"` |

---

## 6. use case(只给 `arguments` 字段)

### 6.1 单程 · 全量(默认)

```json
{
  "departureCity": "深圳",
  "arrivalCity":   "成都",
  "departureDate": "2026-06-05"
}
```

### 6.2 单程 · 最便宜

```json
{
  "departureCity": "北京",
  "arrivalCity":   "上海",
  "departureDate": "2026-06-04",
  "cheapest":      true
}
```

### 6.3 单程 · 筛选(舱等 + 行李 + 直飞 + 限价 + 航司 + 排序)

```json
{
  "departureCity":   "上海",
  "arrivalCity":     "深圳",
  "departureDate":   "2026-06-04",
  "cabinClass":      "ECONOMY",
  "baggage":         true,
  "nonStop":         true,
  "maxPrice":        1500,
  "airlineName":     "东航",
  "sortBy":          "PRICE"
}
```

### 6.4 往返 · 打包推荐(默认)

```json
{
  "departureCity": "北京",
  "arrivalCity":   "上海",
  "departureDate": "2026-06-08",
  "returnDate":    "2026-06-13"
}
```

### 6.5 往返 · 自由组合(分段订)

```json
{
  "departureCity":      "北京",
  "arrivalCity":        "上海",
  "departureDate":      "2026-06-08",
  "returnDate":         "2026-06-13",
  "roundTripListMode":  "FREE"
}
```

### 6.6 改条件 → 必须重调

> **铁律**:改了 `departureCity` / `arrivalCity` / `departureDate` / `cabinClass` / `airlineName` / `nonStop` / `maxPrice` / `sortBy` / `returnDate` / `roundTripListMode` 任何一个 → **重新调用** `queryFlightBasic`,**不**在 `filterFlightList` 上做客户端过滤。
> `filterFlightList` 仅用于 TMS 不支持的维度(`planeSize` / `maxDuration`)。

---

## 7. 版本与变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| 1.4.0 | 2026-06-03 | 初版 — 含大量**编造**的输出 schema(`flightList` / `cabins` / `serialNumber` / `airLine: "SZXPKX"` 等)和一个**不实**的"已 MCP Inspector 验证"声明。**全部撤回** |
| **1.5.0** | 2026-06-04 | **本版** — 按用户要求:<br>1. schema 来源标注为 skill 内 `tools/flight-mcp.json`(源快照归档在 `docs/api/mcp-response-0604.json`,仅作历史,不直接引用),**不**独立编<br>2. §2 输入参数**逐字段**从源 JSON 摘录,带原文说明<br>3. §4 输出结构:撤回所有字段(源 JSON `outputSchema` 为 `{}`,无可信结构),**等 MCP 端补**<br>4. §5 NL 映射仅基于字段 schema 推论,不引申<br>5. 仍保留"未实测"标记 |
