---
name: flight-query
description: 通过 MCP 端点查询国内航班（单程/往返）。从自然语言解析 OD + 日期 + 筛选条件,调 MCP 的 `queryFlightBasic` / `filterFlightList` 工具,以 Markdown 表格输出。Token 走 header 透传,禁止硬编码。
version: 1.5.0
allowed-tools:
  - Bash
argument-hint: "[出发地] [到达地] [出发日期] [可选: 返程日期] [可选: 筛选条件]"
---

# Flight Query Agent Skill (flight-query) — Core

> **本文档 = 核心层(必读,始终加载)**。深度细节走 on-demand 子 skill(见 §6)。
>
> **范围**:仅「机票查询」。选舱/填人/核价/下单走 `flight-booking` skill。
>
> **MCP 工具接口源**:本 skill **不**定义工具 schema;权威定义见
> **`tools/flight-mcp.json`**(skill 自包含,MCP `tools/list` 真实响应,源快照归档在 `docs/api/mcp-response-0604.json`)。
> 本 skill 仅从 `tools/flight-mcp.json` 挑出与"机票查询"相关的 2 个工具并指明**何时用**。
> 任何字段冲突时,以 `tools/flight-mcp.json` 为准。

---

## 1. Token 透传契约(Header Passthrough → system_prompt 注入)

> **铁律**:本 skill 不硬编码任何 token。Token 由调用方在每次 HTTP 请求时通过 header 传入,OpenAgent **注入到 system_prompt** 让 LLM 自己填入 MCP header。

### 1.1 完整流程

```
[Client] POST /agent/chat
  Headers: X-MCP-Token: <token>      (or Authorization: Bearer <token>)
                │
                ▼
[OpenAgent routes.py]  _extract_mcp_token(request) 读 header
                │
                ▼
[bridge → adapter → opencode_chat.py]
                │
                ▼
[把 token 拼到 system_prompt 末尾的 <runtime-context> 块]
                │
                ▼
[opencode serve]  把 system 消息送给 LLM
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

### 1.3 接收格式(MCP 端两种都接受,任选)

| 写入 header | 说明 |
|---|---|
| `token: <value>` | MCP 端默认接受 |
| `Authorization: Bearer <value>` | OAuth 标准形式,亦可 |

### 1.4 LLM 行为约束

- **从 `<runtime-context>` 块取 `MCP_TOKEN`** 填入 curl header,**不**瞎编 token
- 不在 `tools/call` 参数里放 token 字段
- 不在自然语言回复、表格、日志里回显 token
- `401` 最多重试 1 次 — token 失效就告知"权限配置异常,联系管理员"
- 不接受 caller 传 `token=...` query 参数

---

## 2. MCP 端点 & 协议

| 项 | 值 |
|---|---|
| Endpoint | `https://traveldev.feiheair.com/api/mcp` |
| Protocol | JSON-RPC 2.0 over HTTP |
| Accept | `application/json,text/event-stream` |
| Content-Type | `application/json` (UTF-8) |
| Auth header | 见 §1 |
| 响应结构 | `.result.content[0].text` 是 JSON 字符串,需二次 `JSON.parse` |

---

## 3. 工具清单(本 skill 用 2 个)

> **权威源**:`tools/flight-mcp.json`(skill 自包含,服务端 `tools/list` 真实响应)。
> **本节是"什么时候用哪个"的使用指南**,不重复 schema。

| MCP 工具名 | 何时用 | 详见 |
|---|---|---|
| `queryFlightBasic` | **首调** — 调 TMS 查航班。支持舱等/行李/退改/差标/航司/限价/直飞/时段/含餐/排序。**改 OD/日期/舱等/航司/限价/直飞/排序 → 重调** | 子 skill `flight-query:query_flight_basic` |
| `filterFlightList` | **次调** — 在已加载的列表上**内存筛选**,不调 TMS。**只**用于 TMS 不支持的维度(`planeSize` / `maxDuration`)或用户加追加简单条件。**改 OD/日期/舱等 → 不要用本工具,改用 `queryFlightBasic`** | `tools/flight-mcp.json` 直接查 |
| 其他 13 个 | `getWeather` / `buildOrderPreview` / `fillPassenger` / `getDefaultContact` / `getOrderDetail` / `getTripApplicationDetail` / `bindCostCenter` / `listCostCenters` / `listTripApplications` / `recordPolicyUserDecision` / `resetBookingSession` / `validateBookingInfo` / `read_skill` | **本 skill 不接** — 归 `flight-booking` skill 或不归 |

### 3.1 路由决策(LLM 行为)

```
用户: "明天北京到上海最便宜的,只要东航,含行李,上午走"
   │
   ▼ 解析
   OD: 北京→上海  日期: <tomorrow>  舱等: 经济  航司: 东航  行李: 是  时段: MORNING
   cheapest: true
   │
   ▼ 这些条件都是 queryFlightBasic 一次能查的 → 走 queryFlightBasic
   │
   {"name":"queryFlightBasic","arguments":{...一次性传完...}}
   │
   ▼ 返回 flightList
   │
   ▼ 用户追加: "只要大飞机的"  → planeSize 不在 queryFlightBasic 里
   │
   ▼ 走 filterFlightList (内存筛选, 不调 TMS)
```

```
用户: "明天下午北京到上海,看看有哪些航班,再帮我挑个飞行时长最短的"
   │
   ▼ "看看有哪些" → 不传 cheapest / cabinClass → 走 queryFlightBasic 拿全量
   │
   ▼ "飞行时长最短" → TMS 没有这维度 → 用户说了再调 filterFlightList(maxDuration: ...)
   │
   {"name":"filterFlightList","arguments":{"sessionId":"...","sortBy":"DURATION"}}
```

> **关键铁律**:用户要换 OD/日期/舱等/航司/限价/直飞/排序 → **必须重调** `queryFlightBasic`,**不**在 `filterFlightList` 上做客户端过滤。
> `filterFlightList` 仅用于 TMS 不支持的维度(`planeSize` / `maxDuration`)。

---

## 4. 城市/机场代码(翻译辅助)

> MCP `queryFlightBasic` 的 `departureCity` / `arrivalCity` **接受用户原话**(中文城市名优先,详见 `mcp-response-0604.json` 的 `inputSchema.properties.departureCity.description`)。本节是"用户说 IATA/ICAO/机场名 → LLM 翻成用户原话"的翻译辅助。

### 4.1 翻译流程(LLM 行为)

```
用户: "BJS 到 SHA 明天的航班"
          │
          ▼ LLM 查 §4.2 表(或加载子 skill flight-query:iata_icao_codes)
          │
   BJS → 北京     SHA → 上海
          │
          ▼ 拼 JSON-RPC
          │
   {"name":"queryFlightBasic","arguments":{"departureCity":"北京","arrivalCity":"上海",...}}
```

> 用户**直接说中文**(北京、上海)→ 跳过翻译,直接用。
> 用户**说 IATA/ICAO** → 查 §4.2 翻成中文再发。
> 用户**说机场名**(首都/大兴/虹桥/浦东)→ 查 §4.2 翻成对应城市名(可备注"按 XX 机场")。

### 4.2 IATA/ICAO → 中文城市名(常用)

| 用户原话 | 发给 MCP 的原话 | 备注 |
|---|---|---|
| 北京 / BJS / PEK / PKX | `北京` | 城市码 BJS 含首都+大兴;LLM 不强制区分机场 |
| 上海 / SHA / PVG | `上海` | 城市码 SHA 含虹桥+浦东 |
| 深圳 / SZX | `深圳` |  |
| 广州 / CAN | `广州` |  |
| 香港 / HKG | `香港` |  |
| 澳门 / MFM | `澳门` |  |
| 成都 / CTU | `成都` |  |
| 杭州 / HGH | `杭州` |  |
| 台北 / TPE | `台北` |  |
| 东京 / HND / NRT | `东京` | 羽田/成田合并 |
| 新加坡 / SIN | `新加坡` |  |
| (其他) | **查 `flight-query:iata_icao_codes` 子 skill** | 表里没有 → 主动问用户 |

> 完整版含 ICAO 4 字码 + 模糊处理 → **`flight-query:iata_icao_codes`**(on-demand,见 §6)。

---

## 5. 错误处理(精简)

| 现象 | 处置 |
|---|---|
| `401 / token invalid` | "权限配置异常,联系管理员";最多重试 1 次 |
| `errorCode≠0`(业务级) | 按 `errorMsg` 提示用户改条件 |
| 返回空列表 | 提示放宽(换日期/换舱等/换 OD) |
| HTTP 400 `Invalid message format`(Spring `WebMvcStatelessServerTransport#handlePost` stack) | **服务端 MCP bug**(已知),token 认证已通过但 JSON-RPC body 解析失败。告知"机票查询服务暂时不可用",**不**重试,**不**编造航班 |
| HTTP 5xx `JSON parse error: Cannot deserialize...` | 同上(同一 bug 的另一 stack 路径) |
| `-32099 访问频率过高` | 退避 ~1s 重试 1 次;仍失败告知"系统繁忙" |
| 城市识别错误 | 主动澄清(同 §4 速查里没说清的) |

**已知服务端问题(2026-06-04)**:MCP 对**部分** `tools/list` 请求返 HTTP 400 + `Invalid message format`(Spring 反序列化失败)。`tools/call` 路由正常(返回 `-32602 Unknown tool` 时是名字错,不是服务端 bug)。

---

## 6. 子 skill(按需加载)

> LLM: 用户问具体细节时,**主动用 `skill` 工具加载**对应子 skill;不要把全部内容塞上下文。

| 子 skill 名 | 加载时机 | 内容 |
|---|---|---|
| `flight-query:query_flight_basic` | 准备调 `queryFlightBasic` / 需查完整参数 schema / 出参怎么解析 / NL→param 映射 | 完整输入 schema(从 `mcp-response-0604.json` 摘)+ 输出字段说明 + 5 个 use case + 输出模板 |
| `flight-query:iata_icao_codes` | 遇到 IATA/ICAO 码要翻译 / 未识别城市 / 用户问"XX 城市的代码" | 30+ 城市 IATA+ICAO 对照 + 模糊处理 + 临时表查询指引 |
| `flight-query:flight_booking`(待建) | 用户要"选航班/下单" | 见 `flight-booking` skill,本 skill **不**加载 |

---

## 7. 铁律

1. **改 OD/日期/舱等/航司/限价/直飞/排序必须重调 `queryFlightBasic`**,**不**在 `filterFlightList` 上做客户端过滤
2. **`filterFlightList` 仅用于 TMS 不支持的维度**(`planeSize` / `maxDuration`)或用户加追加简单条件
3. **绝对不要自猜日期**(包括回程)— `returnDate` 用户没说就追问
4. **相对日期**用当前日期转 `yyyy-MM-dd`,月份日期**必须补零**(`2026-06-04`,**不**是 `2026-6-4`)
5. **模糊偏好**("挑一个/最划算")老实说"本接口返回的是全量 / 含 X 维度最低价;以下是筛选结果",**不**瞎编
6. **城市用用户原话**(中文优先);IATA/ICAO/机场名先翻译(见 §4)
7. **token 不外泄**(§1)
8. **调工具失败 → 不编造**,老实说"查询失败"
9. **本 skill 仅查票** → 选航班/选舱/填人/核价/下单走 `flight-booking` skill

---

## 8. 一句话示例(只给 `arguments` 字段;实际要包 JSON-RPC envelope)

- "明天北京到上海" → `{"departureCity":"北京","arrivalCity":"上海","departureDate":"<tomorrow>"}`
- "下周二上海到深圳经济舱" → `{"departureCity":"上海","arrivalCity":"深圳","departureDate":"<next-tue>","cabinClass":"ECONOMY"}`
- "6 月 10 日去北京,13 号回,只看东航" → 加 `"returnDate":"2026-06-13","airlineName":"东航"`
- "最便宜的、含行李的、上午走" → `"cheapest":true,"baggage":true,"departureDayPart":"MORNING"`
- "再加个只要大飞机的" → 切 `filterFlightList`:`{"sessionId":"...","planeSize":"大"}`

> **`searchType` 选填**。完整 enum 列表见 `tools/flight-mcp.json` 的 `inputSchema.properties.searchType.enum`(15 个中文值)。建议优先填好 `cheapest` / `cabinClass` / `baggage` 等驱动参数,`searchType` 留空让服务端推导。

---

## 9. 版本与变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| 1.0.0 ~ 1.3.0 | (历史) | 早期版本;§1 Token 透传契约;渐进式加载 |
| 1.4.0 | 2026-06-03 | 修了"工具名/参数" — 用了 `queryFlightBasic` + `departureCity` 等。当时声称"MCP Inspector 验证过" — **这是错的**,**没有**真实抓包验证。值猜对了(`全量查询` 确实存在),但 searchType 枚举、cabinClass、baggage、refundable 等多个可选参数**漏写**了。撤回。 |
| **1.5.0** | 2026-06-04 | **本版** — 按用户要求重构:<br>1. 工具 schema **不**在本文件 — 改引用 **`tools/flight-mcp.json`**(skill 自包含,真实 `tools/list` 响应);源快照归档在 `docs/api/mcp-response-0604.json`,SKILL 不再直接引用<br>2. §3 工具清单瘦身,只列"何时用哪个"<br>3. 删掉 v1.4.0 编的"17 个工具,本 skill 用 1 个" — 实际 MCP 是 **15 个**,本 skill 用 **2 个**(`queryFlightBasic` + `filterFlightList`)<br>4. §7 加铁律"改 OD/舱等/航司 → 重调 queryFlightBasic,不调 filterFlightList"<br>5. §8 给出 `searchType` 提示但不列全表(以源 JSON 为准) |
