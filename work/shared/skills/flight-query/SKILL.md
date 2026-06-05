---
name: flight-query
description: 通过 MCP 端点查询国内航班（单程/往返）。从自然语言解析 OD + 日期 + 筛选条件,调 MCP 的 `queryFlightBasic` / `filterFlightList` 工具,以 Markdown 表格输出。Token 走 header 透传,禁止硬编码。**仅查票**;选舱/填人/核价/下单走 `flight-booking` skill。
version: 2.0.0
allowed-tools:
  - Bash
  - Read
argument-hint: "[出发地] [到达地] [出发日期] [可选: 返程日期] [可选: 筛选条件]"
---

# Flight Query Agent Skill (flight-query) — Core

> **本文档 = 核心层**(必读,始终加载)。细节走 on-demand 子 skill(见 §7)。
>
> **本 skill 范围**:只接 **2 个** MCP 工具(`queryFlightBasic` 主工具 + `filterFlightList` 内存二次筛选)。
> 其余 13 个 MCP 工具(选舱/填人/核价/下单/订单管理)走 `flight-booking` skill。
>
> **数据源**(本 skill 自包含):
> - 工具 schema 权威源 → **`tools/flight-mcp.json`**(MCP `tools/list` 真实响应)
> - 真实调用样本 → **`tools/samples/*.json`**(用真实 token 抓的 4 个响应,含 1 个业务错误)
> - 端到端 curl 模板 → **`examples/*.sh`**(可跑,占位 `${MCP_TOKEN}`)
>
> **分层加载**:
> 1. 本文件 → 必读
> 2. 遇具体工具细节 → **`flight-query:query_flight_basic`**(输入/输出 schema + NL 映射 + 真实样本字段)
> 3. 遇 IATA/ICAO/机场名翻译 → **`flight-query:iata_icao_codes`**
> 4. 任何"端到端怎么打 curl" → `examples/`

---

## 1. 入口契约

### 1.1 端到端数据流

```
[Client] POST /agent/chat
  Headers: X-MCP-Token: <token>      (or Authorization: Bearer <token>)
                │
                ▼
[OpenAgent routes.py] _extract_mcp_token(request) 读 header
                │
                ▼
[bridge → adapter → opencode_chat.py]
                │
                ▼
[把 token 拼到 system_prompt 末尾的 <runtime-context> 块]
                │
                ▼
[opencode serve] 把 system 消息送给 LLM
                │
                ▼
[LLM 看到 system 里有 MCP_TOKEN,自己拼 curl header 调用 MCP]
                │
                ▼
[opencode Bash tool 实际执行 curl] ──→ [MCP: traveldev.feiheair.com/api/mcp]
                                          Headers: token: <value>
```

### 1.2 LLM 实际看到的 system 消息(每请求拼一次)

```
[scenario 的 execution.system_prompt]
(例如: 你是飞鹤差旅 AI 助手 — 机票查询专责...)

<runtime-context>
MCP_TOKEN: <user's token, per-request>
MCP_ENDPOINT: https://traveldev.feiheair.com/api/mcp
MCP_AUTH_STYLE: header token: <value> | Authorization: Bearer <value>
MCP_USAGE: 本对话专属 MCP token。调用任何 MCP 工具时,把它放到对应 header
           (token: ... 或 Authorization: Bearer ...)中。
MCP_SECURITY: 不要在自然语言回复、表格、日志里回显这个 token。
</runtime-context>
```

### 1.3 端点 & 协议

| 项 | 值 |
|---|---|
| Endpoint | `https://traveldev.feiheair.com/api/mcp` |
| Protocol | JSON-RPC 2.0 over HTTP |
| Accept | `application/json,text/event-stream` |
| Content-Type | `application/json` (UTF-8) |
| Auth header | `token: <value>` 或 `Authorization: Bearer <value>` 任选 |
| 响应结构 | `.result.content[0].text` 是 **JSON 字符串**,需二次 `JSON.parse` |

### 1.4 LLM 行为约束

- **从 `<runtime-context>` 块取 `MCP_TOKEN`** 填入 curl header,**不**瞎编 token
- 不在 `tools/call` 参数里放 token 字段
- 不在自然语言回复、表格、日志里回显 token
- `401` 最多重试 1 次 — token 失效就告知"权限配置异常,联系管理员"
- 不接受 caller 传 `token=...` query 参数

> 完整 curl 模板见 **`examples/*.sh`**(可复制,把 `${MCP_TOKEN}` 换成实际值)。

---

## 2. 工具总览(本 skill 接 2 个)

> **权威源**:`tools/flight-mcp.json`(skill 自包含,MCP `tools/list` 真实响应,**`result.tools[].name`** 字段直接给工具名)。
> **本节只说"何时用哪个"**。详细 schema/字段 → 加载子 skill。

| MCP 工具 | 何时用 | 详见 |
|---|---|---|
| `queryFlightBasic` | **首调 / 改条件重调** — 改 OD/日期/舱等/航司/限价/直飞/排序/时段/含餐/退改/差标**任何一个** → 必重调本工具 | `flight-query:query_flight_basic` §2 + §5 |
| `filterFlightList` | **次调(内存筛选)** — 在已加载的 `flightList` 上做 TMS 不支持的维度二次筛选:飞机大小(`planeSize`)、飞行时长(`maxDuration`)、或加追加简单条件 | `tools/flight-mcp.json` 直接查 `filterFlightList.inputSchema` |

**其余 13 个工具**(`getWeather` / `buildOrderPreview` / `fillPassenger` / `getDefaultContact` / `getOrderDetail` / `getTripApplicationDetail` / `bindCostCenter` / `listCostCenters` / `listTripApplications` / `recordPolicyUserDecision` / `resetBookingSession` / `validateBookingInfo` / `read_skill`)→ **本 skill 不接**,归 `flight-booking` skill。

### 2.1 路由决策(LLM 行为)

```
用户: "明天北京到上海最便宜的,只要东航,含行李,上午走"
   │
   ▼ 解析:OD=北京→上海 / 明天 / 舱等=经济 / 航司=东航 / 行李=是 / 时段=MORNING / cheapest=true
   │
   ▼ 这些条件都是 queryFlightBasic 一次能查的 → 走 queryFlightBasic(一次传完)
   │
   ▼ 返回 flightList
   │
   ▼ 用户追加: "只要大飞机的" → planeSize 不在 queryFlightBasic 里
   │
   ▼ 走 filterFlightList(内存筛选, 不调 TMS)
```

```
用户: "明天下午北京到上海,看看有哪些航班,再帮我挑个飞行时长最短的"
   │
   ▼ "看看有哪些" → 不传 cheapest / cabinClass → queryFlightBasic 拿全量
   │
   ▼ "飞行时长最短" → TMS 不支持 → 用户说了再调 filterFlightList(maxDuration)
   │
   {"name":"filterFlightList","arguments":{"sessionId":"...","sortBy":"DURATION"}}
```

> **铁律**:改 OD/日期/舱等/航司/限价/直飞/排序 → **必须重调** `queryFlightBasic`,**不**在 `filterFlightList` 上做客户端过滤。
> `filterFlightList` **仅**用于 TMS 不支持的维度(`planeSize` / `maxDuration`)或用户加追加简单条件。

---

## 3. 城市/机场代码(翻译辅助)

> **关键**:`queryFlightBasic.departureCity` / `.arrivalCity` 接受**用户原话**(中文城市名优先,见 `tools/flight-mcp.json` 的字段说明)。
> 本节是"用户说 IATA/ICAO/机场名 → LLM 翻成中文"的翻译辅助。

```
用户: "BJS 到 SHA 明天的航班"
          │
          ▼ LLM 查子 skill flight-query:iata_icao_codes
          │
   BJS → 北京     SHA → 上海
          │
          ▼ 拼 JSON-RPC
   {"name":"queryFlightBasic","arguments":{"departureCity":"北京","arrivalCity":"上海",...}}
```

| 用户原话 | 发给 MCP 的原话 | 备注 |
|---|---|---|
| 北京 / BJS / PEK / PKX / 首都 / 大兴 | `北京` | 城市码 BJS 含首都+大兴;LLM 不强制区分机场 |
| 上海 / SHA / PVG / 虹桥 / 浦东 | `上海` | 城市码 SHA 含虹桥+浦东 |
| (其他) | **加载 `flight-query:iata_icao_codes` 子 skill** | 表里没有 → 主动问用户 |

> 完整版含 ICAO 4 字码 + 模糊处理 + 缓存建议 → **`flight-query:iata_icao_codes`**(on-demand)。

---

## 4. 错误处理(精简)

| 现象 | 处置 |
|---|---|
| `401 / token invalid` | "权限配置异常,联系管理员";最多重试 1 次 |
| `errorCode≠0` + 业务级 `errorMsg`(如"请求航信超时") | 按 `errorMsg` 提示用户;`samples/` 里有真实样例(往返那次) |
| `flightList=[]` / `filteredCount=0` | 提示放宽(换日期/换舱等/换 OD) — `samples/queryFlightBasic.北京-上海.oneway.filtered.json` 是真实空响应 |
| `-32099 访问频率过高` | 退避 ~1s 重试 1 次;仍失败告知"系统繁忙" |
| 城市识别错误 | 主动澄清(同 §3 速查里没说清的) |
| 网络超时 | 重试 1 次;仍失败告知稍后重试 |

**已知服务端问题(2026-06-04)**:MCP `tools/list` 在 Spring 反序列化层**偶发**返 HTTP 400 `Invalid message format`;`tools/call` 路由正常。
遇 400 → 退 1~2s 重试 1 次;仍 400 告知"机票查询服务暂时不可用"。

---

## 5. 铁律

1. **改 OD/日期/舱等/航司/限价/直飞/排序/时段/退改/差标 → 必须重调 `queryFlightBasic`**,**不**在 `filterFlightList` 上做客户端过滤
2. **`filterFlightList` 仅用于 TMS 不支持的维度**(`planeSize` / `maxDuration`)或用户加追加简单条件
3. **绝对不要自猜日期**(包括回程)— `returnDate` 用户没说就追问
4. **相对日期**用当前日期转 `yyyy-MM-dd`,月份日期**必须补零**(`2026-06-04`,**不**是 `2026-6-4`)
5. **模糊偏好**("挑一个/最划算")老实说"本接口返回的是全量 / 含 X 维度最低价;以下是筛选结果",**不**瞎编
6. **城市用用户原话**(中文优先);IATA/ICAO/机场名先翻译(见 §3)
7. **token 不外泄**(§1.4)
8. **调工具失败 → 不编造**,老实说"查询失败"
9. **本 skill 仅查票** → 选航班/选舱/填人/核价/下单走 `flight-booking` skill
10. **底层数据缺失**(`samples/*.json` 的 `notIncluded` 字段明示):舱位列表/退改规则/行李额/乘机人/校验/订单预览 — **本 skill 不渲染**这些,只展示 `flightList` 顶层的 `lowestPrice/lowestCabinName/fullPrice/totalDuration/depTime/arrTime` 等;细节引导用户"选航班后看舱位",**不**在 skill 里给空值
11. **必须用 AUIP 卡片**:`queryFlightBasic` 拿到 flightList 后, **必须**调 `ask_user` 工具发 `card_type: "FLIGHT_RESULT"`,把航班按"最快/最便宜/舒适"等维度分方案,推到前端 `FlightResultCard` 渲染 — **不要**再用 Markdown 表格发回(老方案已废,见 §5.1)

---

## 5.1 输出格式 — FLIGHT_RESULT 卡片 (AUIP)

> 旧版用 Markdown 表格 (`| 航班 | 时刻 | ... |`)。**新版统一走 AUIP 卡片**:
> LLM 调 `ask_user` 工具,把 `card_type` 设为 `FLIGHT_RESULT`,把
> flightList 整理成"方案(plan)→ 推荐航班(flight)[]"两层结构,前端
> `FlightResultCard` 会自动按方案分组渲染。
>
> **不要在 chat text 里重复发整张表**。`text` 事件只放一句简短的
> 总结(例: "按你需求筛出 3 个方案, 详见下方卡片")。

### 5.1.1 调用 `ask_user` 模板

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

### 5.1.2 字段映射 (MCP → AUIP Card)

| AUIP 字段 | 来源 (MCP `flightList[0]`) | 必填 | 备注 |
|---|---|---|---|
| `flightId` | `flightId` (顶层) | ✅ | 用作主键; `flightId` 即 `flightNo` |
| `flightNo` | `flightNo` | ✅ | 显示用 |
| `shareFlight` | `shareFlight` (顶层) | ❌ | `true` 时 `airline.name` 用 "厦航(共享MU5116)" 形式 |
| `airline.code` | `airId` (顶层) | ✅ | "CA" / "MU" / "MF" 等 |
| `airline.name` | `legs[0].airlineName` | ✅ | "中国国际航空" |
| `aircraft` | `legs[0].aircraftName` | ✅ | 去掉 "(大)/(中)/(小)" 后缀 |
| `date` | `depDate` | ✅ | yyyy-MM-dd |
| `departure.time` | `legs[0].depTime` | ✅ | HH:MM |
| `arrival.time` | `legs[0].arrTime` | ✅ | HH:MM |
| `departure.airport` | `legs[0].depAirportName` | ✅ | "首都国际机场" |
| `arrival.airport` | `legs[0].arrAirportName` | ✅ | "浦东国际机场" |
| `departure.airportCode` | `depAirportCode` (顶层) | ✅ | "PEK" / "PKX" |
| `arrival.airportCode` | `arrAirportCode` (顶层) | ✅ | "PVG" / "SHA" |
| `departure.terminal` | `legs[0].depTerminal` | ❌ | "T2" / null |
| `arrival.terminal` | `legs[0].arrTerminal` | ❌ | "T2" |
| `duration` | `totalDuration` | ✅ | "2h20m" |
| `stops` | `stopCount` (顶层) | ✅ | 0 = 直飞 |
| `cabin` | `lowestCabinName` | ✅ | "经济舱" |
| `cabinClass` | `lowestCabinName` → 枚举 | ❌ | ECONOMY / BUSINESS / FIRST |
| `meal` | `legs[0].meal` (bool) → "是"/"否" | ❌ | 也可保留中文 "早餐" |
| `price` | `lowestPrice` | ✅ | 数字(元) |
| `fullPrice` | `fullPrice` | ❌ | 全价票面价;算折扣率用 |
| `tags` | LLM 派生 | ❌ | 例: ["最便宜", "1h55m ⚡"] |

### 5.1.3 方案(plan)分组规则

> **每张卡 ≤ 3 个方案**, 每个方案 ≤ 3 个航班, 避免长卡片劝退用户。
> 全部 flightList 数据通过 `summary.totalCount / filteredCount` 在头部展示,
> 用户点 "更多 ▾" 展开完整列表(前端默认显示前 3 + 方案)。

**默认方案维度(按用户语义切换)**:

| 用户偏好关键词 | 方案1 维度 | 方案2 维度 | 方案3 维度 |
|---|---|---|---|
| (无偏好 / "看看有哪些") | 最快抵达 (`duration` 升序) | 最便宜 (`lowestPrice` 升序) | 直飞首选 (`shareFlight=false` + 大机型) |
| "最快" | 最短时长 | 早班直飞 | (省略) |
| "最便宜" | 最低价 | 直飞首选 | (省略) |
| "上午 / 早班" | 06:00-12:00 起飞 | 直飞首选 | (省略) |
| "下午" | 12:00-18:00 起飞 | 直飞首选 | (省略) |
| "晚班" | 18:00-24:00 起飞 | 直飞首选 | (省略) |
| "国航 / 厦航 / 东航 ..." | 指定航司 + 价格升序 | 指定航司 + 时刻 | (省略) |

> 1. 用户没偏好时 **永远** 推"最快 / 最便宜 / 直飞首选"3 方案。
> 2. 任何空结果(`flightList=[]`) → 推 `CANNOT_ORDER` 卡片, message 写 "没找到符合条件的航班";**不要** 推空 `FLIGHT_RESULT`。

### 5.1.4 错误 / 空结果

| 情况 | 处置 |
|---|---|
| `flightList=[]` 且 `filteredCount=0` | 推 `CANNOT_ORDER` card (title: "暂无符合条件的航班", body.message: 按 §4 错误处置) |
| `isError=true` | 推 `CANNOT_ORDER` card, message = 业务 `errorMsg` |
| 4xx / 5xx (连续 2 次) | 推 `CANNOT_ORDER` card, message = "机票查询服务暂时不可用, 请稍后重试" |
| `flightList` 长度 ≤ 3 | 推 1 个方案 `plans=[{id:"recommended", title:"为你找到", flights: 全部}]` |

---

## 6. 真实样本与示例(本 skill 抓的真实数据)

> 2026-06-04 用真实 token 调通的 4 个样本,落盘在 `tools/samples/`,**L

LM 可直接读**这些 JSON 学习真实返回结构。

| 场景 | 请求 | 响应关键点 | 文件 |
|---|---|---|---|
| 单程 · 全量 | 北京→上海 · 2026-06-05 | 193 航班全量,含 citys/airways/types/cityWeatherList 字典 | `queryFlightBasic.北京-上海.oneway.full.json` |
| 单程 · 最便宜 | 上海→深圳 · 2026-06-05 · `cheapest:true` | 服务端把 `cheapest` 推导为 `searchType="经济舱最低价"`,`filteredCount=1` | `queryFlightBasic.上海-深圳.oneway.cheapest.json` |
| 单程 · 筛选(舱等+行李+航司+时段) | 北京→上海 · 2026-06-05 · ECONOMY/baggage/airline=东航/MORNING | `flightList=[]`,`filteredCount=0`(东航上午+含行李无符合 — 真实空结果) | `queryFlightBasic.北京-上海.oneway.filtered.json` |
| 往返 · 推荐 | 北京→上海 · 06-08→06-13 | `isError=true`,`text="请求航信超时"`(真实业务错误) | `queryFlightBasic.北京-上海.roundtrip.recommended.json` |

> 关键发现(已对样本验证):
> - 顶层 `flightId` = `flightNo`(主航段航班号)
> - 时分秒在 `legs[].depTime` / `arrTime`,**不在** 顶层 `outboundDepDate`(`outboundDepDate` 只有 `yyyy-MM-dd`)
> - `planeSize` 在顶层是**空字符串**,机型信息在 `legs[].aircraftName`(含 "(大)/(中)/(小)" 后缀)
> - `meal` 顶层 `null`,`legs[].meal` 才是
> - `airlineName` 在 `legs[].airlineName`(中文),`flightList[].airId` 是代码
> - 真实舱位列表 / 退改规则 / 行李额 — `notIncluded` 字段明示要走 `chooseFlight` 等其他工具,**本 skill 不渲染**

---

## 7. 子 skill(按需加载)

> LLM: 用户问具体细节时,**主动用 `skill` 工具加载**对应子 skill;不要把全部内容塞上下文。

| 子 skill 名 | 加载时机 | 内容 |
|---|---|---|
| `flight-query:query_flight_basic` | 准备调 `queryFlightBasic` / 需查完整参数 schema / 出参怎么解析 / NL→param 映射 | 完整输入 schema(从 `tools/flight-mcp.json` 摘)+ **真实输出字段说明**(从 `samples/*.json` 提炼)+ NL 映射 + 6 个 use case + 端到端 curl 模板 |
| `flight-query:iata_icao_codes` | 遇到 IATA/ICAO 码要翻译 / 未识别城市 / 用户问"XX 城市的代码" | 30+ 城市 IATA+ICAO 对照 + 模糊处理 + 临时表查询指引 |
| `flight-query:flight_booking` | 用户要"选航班/下单"(本 skill **不**加载,只给指引) | 走 `flight-booking` skill,本 skill 只负责把 `flightList` 给前端选 |

---

## 8. 版本与变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| 1.0.0 ~ 1.3.0 | (历史) | 早期版本;§1 Token 透传契约;渐进式加载 |
| 1.4.0 | 2026-06-03 | 修了"工具名/参数",但 searchType 枚举/舱等/行李/退改多个参数漏写。撤回 |
| 1.5.0 | 2026-06-04 | 工具 schema 改引用 `tools/flight-mcp.json`(不再内联);§3 工具清单瘦身 |
| **2.0.0** | 2026-06-04 | **深度打磨 — 分层标准化**:<br>1. **真实样本**:`tools/samples/` 落 4 份真实响应(单程全量/最便宜/筛选空结果/往返业务错误),用真实 token 抓<br>2. **工具精简**:本 skill 用 **2 个**(`queryFlightBasic` + `filterFlightList`),13 个明确归 `flight-booking`<br>3. **输出 schema 修正**:v1.5.0 §4 说"等 MCP 端补" — **本版直接从 4 份真实样本提炼实际字段**(`flightList[].legs[].depTime/arrTime` / `airlineName` / `aircraftName` / `planeSize=""` / `meal=null` / `notIncluded` 等),落到子 skill `query_flight_basic` §3<br>4. **新增 examples/**:`examples/01~05.sh` 5 个真实可跑 curl 模板(单程全量/最便宜/筛选/往返/filterFlightList 二次筛选),§1.4 直接指向<br>5. **新增 SKILL-INDEX.md**:给 LLM 一页导航,免得迷失<br>6. **§6 新增"真实样本速查表"**:LLM 调工具前/后可直接读样本学结构<br>7. **§5 加铁律 #10**:`notIncluded` 字段明示舱位/退改/行李/乘机人/校验/预览不在本 skill,避免乱编 |
| **2.1.0** | 2026-06-05 | **AUIP 卡片化输出**:<br>1. **§5.1 新增 FLIGHT_RESULT 卡片规范** — 替代 v2.0.0 的 Markdown 表格输出,LLM 拿到 flightList 后必须调 `ask_user` 推 `card_type: "FLIGHT_RESULT"` 卡片(走前端 `FlightResultCard` 渲染)<br>2. **铁律 #11**:必须用 AUIP 卡片(FLIGHT_RESULT / CANNOT_ORDER),不要在 chat text 里发整张 Markdown 表<br>3. **§5.1.2 字段映射表**:MCP `flightList[]` 实际字段 → AUIP `flights[]` 字段的 1:1 映射,LLM 整理时直接照搬<br>4. **§5.1.3 方案分组规则**:默认推"最快 / 最便宜 / 直飞首选" 3 方案,每个方案 ≤ 3 个航班;按用户偏好关键词切换维度<br>5. **§5.1.4 错误处置**:空结果 / `isError` / 4xx-5xx 全部走 `CANNOT_ORDER` 卡片 |
