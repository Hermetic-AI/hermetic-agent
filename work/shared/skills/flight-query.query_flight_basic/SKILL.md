---
name: flight-query.query_flight_basic
description: "`queryFlightBasic` 工具的深度规范 — 完整 input schema、所有 enum 值、**真实输出字段(从 4 份真实样本提炼)**、NL→param 映射、use case。**本版基于 2026-06-04 用真实 token 抓的 4 份响应**,输出 schema 不再靠"等 MCP 端补"。冲突时以 `tools/flight-mcp.json` 为准(工具定义)+ `tools/samples/` 为准(输出结构)。"
version: 2.0.0
allowed-tools:
  - Bash
  - Read
---

# queryFlightBasic 深度规范 (On-Demand)

> **加载时机**:父 skill `flight-query` 提示"详见 `flight-query:query_flight_basic`"时;
> 或 LLM 主动判断需要完整 schema / 真实输出结构时。
>
> **本文档不重复**:endpoint / 协议 / token 契约(见父 skill `flight-query` §1 §3 §4 §5)。
>
> **数据源**:
> - 工具 schema → 父 skill 根 `tools/flight-mcp.json` → `result.tools[?(@.name=="queryFlightBasic")]`
> - 输出结构 → 父 skill 根 `tools/samples/queryFlightBasic.*.json`(4 份真实响应)

---

## 1. 工具元信息

| 字段 | 值 | 来源 |
|---|---|---|
| 名称 | `queryFlightBasic` | `tools/flight-mcp.json` |
| 描述(原文) | 【TMS 查询】调 TMS 查航班。支持舱等/行李/退改/差标/航司/限价/直飞/时段/含餐/排序。首次查询时把用户所有条件一次性传入。改出发/到达/日期/舱等 → 必须重调本工具。不支持:飞机大小、飞行时长 → 查完后用 `filterFlightList` 或 LLM 自行筛选。模糊偏好("哪个最划算""帮我推荐") → LLM 直接分析返回的航班列表,不调工具。 | `tools/flight-mcp.json` |
| 类别 | TMS 查询(调上游);首次查 / 改条件查 | 描述推论 |
| 配套 | 同会话内可用 `filterFlightList` 在结果上做内存筛选(planeSize / maxDuration) | 父 skill §2 |
| 幂等 | 纯查询;`sessionId` 由 MCP 端管理(在本工具的 `serialNumber` 字段给) | 真实响应 |

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
| `cheapest` | boolean | 是否只返回最低价航班(1 条)。`true`=最便宜 1 条,`false` 或不传=返回多条。用户说"最便宜/最低价/最划算"时设 `true`;说"看看有哪些/帮我查一下"时不传或 `false`。**真实样本验证**:传 `true` 后服务端会把 `searchType` 字段自动推成 `经济舱最低价` |
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
| `searchType` | enum(17 个中文值) | 查询意图标签,**仅供日志展示,不参与筛选排序逻辑**。可选值见 §2.3。**建议:优先填好 `cheapest` / `cabinClass` / `baggage` 等驱动参数,`searchType` 选填即可**;服务端会用驱动参数自动推导 |

### 2.3 `searchType` enum(17 个值,摘自 `tools/flight-mcp.json`)

> **真实样本验证**:
> - 全量查询(不传驱动参数)→ 服务端推 `searchType: "全量查询"` ✓
> - `cheapest: true` → 服务端推 `searchType: "经济舱最低价"` ✓
> - 其他 15 个值**未实测**,建议**默认不传**

| 值 | 含义(原文 / 推论) |
|---|---|
| `全量查询` | **已实测**:默认,无特殊筛选 |
| `经济舱最低价` | **已实测**:由 `cheapest: true` 推导 |
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

---

## 3. 输出结构(基于 4 份真实样本提炼)

> **真实样本**:`tools/samples/queryFlightBasic.*.json`(4 份,2026-06-04 用真实 token 抓)。
> **响应路径**:`.result.content[0].text` → JSON 字符串 → **二次 `JSON.parse`** 得下面结构。
> **顶层 error 标记**:`.result.isError === true` 时,`text` 字段是**业务级错误消息**(如"请求航信超时"),**没有** `serialNumber`/`flightList` 等结构。

### 3.1 顶层 envelope

```jsonc
{
  "serialNumber":  "260604160455A00000001",   // 流水号(选航班后回传)
  "searchType":    "全量查询" | "经济舱最低价", // 服务端推导
  "roundTrip":     false,                     // 是否往返
  "flightCount":   193,                       // TMS 全量
  "filteredCount": 193 | 1 | 0,               // 经筛选条件后
  "flightList":    [ /* 见 §3.2 */ ],
  "citys":         [ /* 见 §3.4 字典 */ ],
  "airways":       [ /* 见 §3.4 字典 */ ],
  "types":         [ /* 见 §3.4 字典 */ ],
  "cityWeatherList": [ /* 见 §3.5 天气 */ ],
  "notIncluded":   [                          // 服务端明示"以下字段不在本接口,要走其他工具"
    "cabinList(舱位列表,选航班后用 chooseFlight 获取)",
    "refundRules(退改规则详情,用航班详情 Tool 补查)",
    "baggageWeight(行李额,用航班详情 Tool 补查)",
    "passengerInfo(乘机人信息,选舱后用 queryPassenger 获取)",
    "validationResult(校验结果,信息齐后用 validateBookingInfo 校验)",
    "orderPreview(订单预览,校验通过后用 buildOrderPreview 生成)"
  ]
}
```

### 3.2 `flightList[]` — 航班条目(从真实样本提炼)

```jsonc
{
  "serialNo":              1,                  // 1-based 序号
  "flightId":              "MF8561",           // = flightNo(主航段航班号)
  "outboundFlightId":      "MF8561",
  "flightNo":              "MF8561",
  "airId":                 "MF",               // 航司代码 → airways[].companyNo
  "tripType":              "ONE_WAY",          // ONE_WAY | ROUND_TRIP
  "lowestPrice":           400,                // 该航班最便宜的舱位价(含税)
  "lowestCabinName":       "经济舱",            // 最低价舱位名
  "lowestCabinId":         null,               // ⚠️ null — 选航班后才有
  "fullPrice":             1630,               // Y 舱全价(差标用)
  "depCityName":           "北京",
  "arrCityName":           "上海",
  "depDate":               "2026-06-05",       // 出发日期
  "totalDuration":         "1h55m",            // 总飞行时长
  "transferCount":         0,                  // 中转次数
  "totalMile":             1178 | null,
  "depAirportCode":        "PKX",              // 出发机场 IATA
  "arrAirportCode":        "PVG",              // 到达机场 IATA
  "outboundDepDate":       "2026-06-05",       // ⚠️ 只是 date,时分秒在 legs[]
  "outboundArrDate":       "2026-06-05",       // 跨天时会 +1(如 2026-06-06)
  "stopCount":             0,                  // 经停次数
  "durationMin":           150 | null,
  "meal":                  null,               // ⚠️ 顶层 null,meal 信息在 legs[].meal
  "planeSize":             "",                 // ⚠️ 顶层空字符串,机型信息在 legs[].aircraftName
  "totalPrice":            570,
  "legs":                  [ /* 见 §3.3 */ ]
}
```

### 3.3 `legs[]` — 航段(单程=1,往返=2)

```jsonc
{
  "direction":        "GO",                    // GO=去程 / RETURN=回程
  "flightId":         "9C7555",
  "flightIndex":      0,                       // 段索引
  "flightNo":         "9C7555",
  "airlineName":      "春秋航空",                // ⚠️ 已含中文航司名(在 legs 里有)
  "depDate":          "2026-06-05",            // 出发 date
  "depTime":          "23:00",                 // ⚠️ HH:mm(顶层 outboundDepDate 没有时分秒)
  "arrTime":          "01:30",                 // HH:mm
  "arrDate":          "2026-06-06",            // 到达 date(跨天会 +1)
  "depAirportName":   "浦东机场",
  "depTerminal":      "T1",
  "arrAirportName":   "宝安机场",
  "arrTerminal":      "T3",
  "duration":         "2h30m",
  "mile":             null,
  "aircraftName":     "空客320(中)",           // ⚠️ 含 (大)/(中)/(小) 后缀 — 解析飞机大小
  "onTime":           null,
  "meal":             null,                    // 是否含餐
  "shareFlight":      false,                   // 是否共享航班
  "shareId":          null,                    // 共享主航班号(空=非共享)
  "stops":            [],                      // 经停列表
  "transferWait":     null,
  "previewCabinCount": 1                       // 该航段可选舱位数(选航班后用 chooseFlight 取)
}
```

### 3.4 字典(反查用)

```jsonc
citys[] = {
  "cityCode":      "PEK",      // 机场 IATA
  "city":          "BJS",      // 城市码
  "cityCodeName":  "北京首都",  // 机场中文名
  "cityName":      "北京",     // 城市中文名
  "airPortEn":     "",         // 机场英文名(常空)
  "airPortName":   "首都机场",
  "unifiedCityId": "110000"    // 行政区划代码
}

airways[] = {
  "companyNo":      "MF",
  "companyName":    "厦门航空",
  "fullCompanyName":"厦航"
}

types[] = {
  "type":   "320",
  "airCom": "空客",
  "size":   "中",                 // 大 | 中 | 小
  "name":   "空客320"
}
```

### 3.5 `cityWeatherList[]`(免费赠)

```jsonc
{
  "cityName":  "上海市",
  "date":      "2026-06-05",
  "week":      "5",
  "dayWeather":"阴",
  "dayTemp":   "29",
  "nightTemp": "21",
  "dayWind":   "东北",
  "dayPower":  "1-3"               // 风力等级
}
```

### 3.6 业务级错误

```jsonc
// isError=true,顶层结构是:
{
  "isError": true,
  "content": [{
    "type": "text",
    "text": "请求航信超时"          // 直接是错误消息字符串,不是 JSON
  }]
}
```

> 真实样本见 `tools/samples/queryFlightBasic.北京-上海.roundtrip.recommended.json`。
> 处置:按 `errorMsg` 提示用户(见父 skill §4)。

---

## 4. JSON-RPC envelope + curl 模板

### 4.1 envelope

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "queryFlightBasic",
    "arguments": { /* §2 字段 */ }
  }
}
```

### 4.2 curl(完整)

```bash
curl -s --location --request POST 'https://traveldev.feiheair.com/api/mcp' \
  --header 'Accept: application/json,text/event-stream' \
  --header 'Authorization: Bearer ${MCP_TOKEN}' \
  --header 'Content-Type: application/json' \
  --data-raw '{
      "jsonrpc": "2.0",
      "id": 1,
      "method": "tools/call",
      "params": {
        "name": "queryFlightBasic",
        "arguments": {
          "departureCity": "北京",
          "arrivalCity":   "上海",
          "departureDate": "2026-06-05"
        }
      }
  }'
```

> 更多场景见父 skill 根 `examples/01-oneway-full.sh` ~ `04-roundtrip-recommended.sh`。

---

## 5. NL → 参数映射

### 5.1 城市(同父 skill §3)

> 用户说 IATA/ICAO/机场名 → 加载 `flight-query:iata_icao_codes` 子 skill。
> 中文 → 直接用。

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
| "最便宜/最低价" | `cheapest: true`(服务端会推 searchType=经济舱最低价) |
| "要直飞/不经停" | `nonStop: true` |
| "含行李/有托运" | `baggage: true` |
| "含餐/有餐食" | `requireMeal: true` |
| "只要南航" | `airlineName: "南航"` |
| "不要春秋" | `excludeAirlineKeywords: "春秋"` |
| "800 以内" | `maxPrice: 800` |
| "差标合规" | `policyCompliant: true` |
| "先看去程,回程我自己挑" | `roundTripListMode: "FREE"` |

---

## 6. use case + 输出渲染模板

> 6 个 use case 对应父 skill 根 `examples/01~05.sh`。
> **输出模板**:服务端返回后,本 skill **只渲染** `flightList[]` 顶层的可读字段;舱位/退改/行李走 `flight-booking` skill。

### 6.1 单程 · 全量

```jsonc
// arguments
{
  "departureCity": "北京",
  "arrivalCity":   "上海",
  "departureDate": "2026-06-05"
}
```

**渲染**(精简到 5 字段,实际样本 193 条):

```markdown
| # | 航班号 | 航司 | 出发 | 到达 | 飞行时长 | 最低价 | 舱位 | 直飞 |
|---|---|---|---|---|---|---|---|---|
| 1 | MF8561 | 厦门航空(MF) | PKX 06:55 | PVG 10:10 | 1h55m | ¥400 | 经济舱 | ✓ |
| 2 | 9C7555 | 春秋航空(9C) | PVG 23:00 | SZX 01:30+1 | 2h30m | ¥570 | 经济舱 | ✓ |
| ...(按 lowestPrice 升序,默认排序)|
```

### 6.2 单程 · 最便宜

```jsonc
{
  "departureCity": "上海",
  "arrivalCity":   "深圳",
  "departureDate": "2026-06-05",
  "cheapest":      true
}
```

> 服务端会把 `searchType` 推成 `经济舱最低价`,`filteredCount=1`。
> 真实样本:春秋航空 9C7555,¥570,经济舱。

### 6.3 单程 · 多维筛选(舱等+行李+航司+时段+排序)

```jsonc
{
  "departureCity":   "北京",
  "arrivalCity":     "上海",
  "departureDate":   "2026-06-05",
  "cabinClass":      "ECONOMY",
  "baggage":         true,
  "airlineName":     "东航",
  "departureDayPart":"MORNING",
  "sortBy":          "PRICE"
}
```

> 真实样本:filteredCount=0,flightList=[]。处置:提示放宽。

### 6.4 往返 · 推荐(RECOMMENDED)

```jsonc
{
  "departureCity": "北京",
  "arrivalCity":   "上海",
  "departureDate": "2026-06-08",
  "returnDate":    "2026-06-13"
}
```

> 真实样本:可能返 `请求航信超时`(`isError=true`)。处置:告知用户稍后重试。

### 6.5 往返 · 自由组合(FREE)

```jsonc
{
  "departureCity":     "北京",
  "arrivalCity":       "上海",
  "departureDate":     "2026-06-08",
  "returnDate":        "2026-06-13",
  "roundTripListMode": "FREE"
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
| 1.5.0 | 2026-06-04 | 撤回所有字段,源 JSON `outputSchema` 为 `{}`,无可信结构,等 MCP 端补 |
| **2.0.0** | 2026-06-04 | **本版 — 基于真实样本**:<br>1. §3 输出结构从 4 份真实响应提炼(`tools/samples/`),**不再靠"等 MCP 端补"**<br>2. 关键修正:顶层 `outboundDepDate` 只有 date 无时分秒 → 时分秒在 `legs[].depTime/arrTime`;`planeSize=""` / `meal=null` 在顶层是空,真实信息在 `legs[]`;`lowestCabinId=null` — 选航班后才有<br>3. §3.4 新增 `citys` / `airways` / `types` 字典反查说明<br>4. §3.6 新增业务级错误结构(`isError=true`,`text="请求航信超时"`)<br>5. §2.3 `searchType` 标"已实测"(`全量查询` / `经济舱最低价`)vs"未实测"<br>6. §3.1 新增 `notIncluded` 字段 — 服务端明示"舱位/退改/行李/乘机人/校验/预览要走其他工具"<br>7. §6.1 输出模板精简到 5 字段(航司/航班号/出发到达/时长/最低价),舱位细节走 `flight-booking` |
