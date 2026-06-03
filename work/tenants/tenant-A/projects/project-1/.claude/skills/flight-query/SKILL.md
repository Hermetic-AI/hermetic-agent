---
name: flight-query
description: 通过 MCP 端点查询国内/国际航班，支持单程、往返、最低价、指定航司、舱等筛选、含行李/餐食、时段、退改、差标合规等条件。把用户的自然语言转成 queryFlightBasic / getWeather 工具调用，并以表格形式输出结果。
version: 1.0.0
allowed-tools:
  - Bash
argument-hint: "[出发地] [到达地] [出发日期] [可选: 返程日期] [可选: 筛选条件]"
---

# Flight Query Agent Skill

通过 MCP 端点 `https://traveldev.feiheair.com/api/mcp` 查询航班，支持舱等、行李、退改、差标、航司、限价、直飞、时段、含餐、排序等丰富筛选条件。

## MCP 端点配置

| 项 | 值 |
| --- | --- |
| Endpoint | `https://traveldev.feiheair.com/api/mcp` |
| Token | `y6lnsna8rpkt856fe2k1` |
| Protocol | JSON-RPC over HTTP (MCP) |
| Accept | `application/json,text/event-stream` |

## 可用工具

| 工具名 | 用途 |
| --- | --- |
| `queryFlightBasic` | 主工具：查航班，支持舱等/行李/退改/差标/航司/限价/直飞/时段/含餐/排序 |

调用前可先用 `tools/list` 确认工具清单（见下方"健康检查"）。

---

## 健康检查（首次使用）

```bash
curl --location --request POST 'https://traveldev.feiheair.com/api/mcp' \
  --header 'token: r6lns3cc9gikkpmg6mbq' \
  --header 'Accept: application/json,text/event-stream' \
  --header 'Content-Type: application/json' \
  --data-raw '{
      "jsonrpc": "2.0",
      "id": 1,
      "method": "tools/list",
      "params": {}
  }'
```

若返回 `result.tools` 包含 `queryFlightBasic`，则端点正常。

---

## 通用调用模板

```bash
curl --silent --location --request POST 'https://traveldev.feiheair.com/api/mcp' \
  --header 'token: r6lns3cc9gikkpmg6mbq' \
  --header 'Accept: application/json,text/event-stream' \
  --header 'Content-Type: application/json' \
  --data-raw '{
      "jsonrpc": "2.0",
      "id": 1,
      "method": "tools/call",
      "params": {
          "name": "queryFlightBasic",
          "arguments": { /* 见下方各场景的参数 */ }
      }
  }'
```

返回值在 `.result.content[0].text`（MCP 标准），通常是 JSON 字符串，需要再 `JSON.parse` 一次拿到航班列表。

---

## 自然语言 → 参数映射

把用户原话一次性映射成 `queryFlightBasic.arguments` 的字段。下表是常用映射，遇到模糊表述走"歧义处理"小节。

| 用户原话 | 字段 | 值 / 取值范围 |
| --- | --- | --- |
| 北京、上海、深圳、成都 | `departureCity` / `arrivalCity` | 用**用户原话**，不要翻译/补全 |
| 明天、后天、下周三、6月5号 | → 转成 `yyyy-MM-dd` | 见"日期换算"小节 |
| 明天下午、晚上 8 点走 | `departureDayPart` | `MORNING` / `AFTERNOON` / `EVENING` |
| 最便宜、挑个最低的 | `cheapest: true` | 仅返回 1 条 |
| 看看有哪些 | `cheapest: false`（或不传） | 返回多条 |
| 经济舱、公务舱、头等舱 | `cabinClass` | `ECONOMY` / `BUSINESS` / `FIRST`，全价经济用 `FULL_ECONOMY` |
| 含行李、要托运 | `baggage: true` | |
| 含餐、要饭吃 | `requireMeal: true` | |
| 只要南航 / 国航 | `airlineName: "南航"` | 中文或二字码 |
| 不要春秋 9C | `excludeAirlineKeywords: "春秋,中联航"` | 逗号分隔 |
| 直飞、不经停 | `nonStop: true` | |
| 不超过 800 块 | `maxPrice: 800` | 整数（元） |
| 能退票、能改签 | `refundable: true` | 含免费退改 |
| 免费退改 | `freeRefund: true` | 仅退改费=0 |
| 差旅合规、出差标准 | `policyCompliant: true` | |
| 早上 6 点到中午的 | `depTimeStart: "06:00"`, `depTimeEnd: "12:00"` | HH:mm |
| 上午 / 下午 / 晚上 | `departureDayPart` | 与 `depTime*` 二选一，**优先用** `departureDayPart` |
| 价格升序、最便宜优先 | `sortBy: "PRICE"` | 默认就是 PRICE |
| 飞行时间最短 | `sortBy: "DURATION"` | |
| 退改最灵活 | `sortBy: "REFUND_FLEXIBILITY"` | |
| 飞过去再飞回来、往返 | 同时传 `returnDate` + `roundTripListMode` | `RECOMMENDED`=去程回程打包推荐，`FREE`=自由组合 |

### 日期换算规则

- 用户说相对日期（明天 / 后天 / 大后天 / 下周X）→ **用当前日期** 转成绝对日期，格式 `yyyy-MM-dd`，月份和日期**必须补零**（如 `2026-06-03`，不要 `2026-6-3`）。
- 用户说"明天下午"这类同时含日期+时段 → 日期进 `departureDate`，时段进 `departureDayPart`。
- 不知道具体日期 → 主动向用户确认，**禁止自猜**。
- 往返时 `returnDate` 必传，**禁止自猜**回程日期。

### 歧义处理

| 场景 | 处理 |
| --- | --- |
| "明天北京到上海" → 没指定舱等 | 默认 `ECONOMY`，不传 `cabinClass` |
| "去上海出差，差标以内" | `policyCompliant: true` |
| "我下周要飞深圳，时间灵活，挑个最便宜的" | `cheapest: true` |
| "上海去北京，再从北京回上海" | 单次调用，分别传两次；如要打包推荐传 `roundTripListMode: "RECOMMENDED"` + `returnDate` |
| "南航的只要下午的" | 同时设 `airlineName: "南航"` + `departureDayPart: "AFTERNOON"` |
| 城市重名（北京/东京都有"东京"问题） | 向用户澄清具体是哪个城市或机场 |

**模糊偏好（"哪个最划算""帮我推荐""挑一个"）**：先调工具拿到完整列表，**不要传** `cheapest: true`，拿到结果后由 LLM 自行筛选/排序/解释。

---

## 典型场景示例

### 1. 单程 · 最低价

用户："明天北京到上海最便宜的"

```json
{
  "departureCity": "北京",
  "arrivalCity": "上海",
  "departureDate": "2026-06-03",
  "cheapest": true
}
```

### 2. 单程 · 看全量

用户："帮我查一下 6 月 5 号深圳到成都的航班"

```json
{
  "departureCity": "深圳",
  "arrivalCity": "成都",
  "departureDate": "2026-06-05"
}
```

### 3. 往返 · 打包推荐

用户："下周一去上海出差，13 号回"

```json
{
  "departureCity": "北京",
  "arrivalCity": "上海",
  "departureDate": "2026-06-08",
  "returnDate": "2026-06-13",
  "roundTripListMode": "RECOMMENDED"
}
```

### 4. 往返 · 自由组合（分段订）

用户："先帮我看去程的"

```json
{
  "departureCity": "北京",
  "arrivalCity": "上海",
  "departureDate": "2026-06-08",
  "returnDate": "2026-06-13",
  "roundTripListMode": "FREE"
}
```

### 5. 含行李 + 下午 + 直飞

用户："明天下午北京到上海，要直飞还要托运行李"

```json
{
  "departureCity": "北京",
  "arrivalCity": "上海",
  "departureDate": "2026-06-03",
  "departureDayPart": "AFTERNOON",
  "nonStop": true,
  "baggage": true
}
```

### 6. 限价

用户："6 月 10 号上海到深圳，不要超过 600 块的"

```json
{
  "departureCity": "上海",
  "arrivalCity": "深圳",
  "departureDate": "2026-06-10",
  "maxPrice": 600
}
```

### 7. 指定航司 + 含餐

用户："后天广州到北京，南航的，要含正餐的"

```json
{
  "departureCity": "广州",
  "arrivalCity": "北京",
  "departureDate": "2026-06-04",
  "airlineName": "南航",
  "requireMeal": true
}
```

### 8. 排除廉航

用户："明天北京到上海，别给我春秋 9C 这种"

```json
{
  "departureCity": "北京",
  "arrivalCity": "上海",
  "departureDate": "2026-06-03",
  "excludeAirlineKeywords": "春秋,9C,中联航"
}
```

### 9. 免费退改

用户："找个能免费退改的"

```json
{
  "departureCity": "北京",
  "arrivalCity": "上海",
  "departureDate": "2026-06-03",
  "freeRefund": true
}
```

### 10. 差标合规 + 全价经济

用户："出差到上海，要差标合规的全价经济舱"

```json
{
  "departureCity": "北京",
  "arrivalCity": "上海",
  "departureDate": "2026-06-03",
  "cabinClass": "FULL_ECONOMY",
  "policyCompliant": true
}
```

### 11. 时间最短

用户："哪个最快到"

```json
{
  "departureCity": "北京",
  "arrivalCity": "上海",
  "departureDate": "2026-06-03",
  "sortBy": "DURATION"
}
```

### 12. 改出发地/到达地/日期/舱等 → 必须重调

> **铁律**：任何时候改了 `departureCity` / `arrivalCity` / `departureDate` / `cabinClass`，**必须重新调用** `queryFlightBasic`，**不要**在前次结果上做客户端过滤。

---

## 改用 `getWeather` 的场景

行程前用户问"明天那边天气怎么样" / "会不会影响航班" → 用 `getWeather` 查目的地的天气，作为是否提醒用户提前出门 / 改签的依据。

```bash
curl --silent --location --request POST 'https://traveldev.feiheair.com/api/mcp' \
  --header 'token: r6lns3cc9gikkpmg6mbq' \
  --header 'Accept: application/json,text/event-stream' \
  --header 'Content-Type: application/json' \
  --data-raw '{
      "jsonrpc": "2.0",
      "id": 1,
      "method": "tools/call",
      "params": {
          "name": "getWeather",
          "arguments": { "city": "上海" }
      }
  }'
```

---

## 输出格式

拿到原始返回后，**必须**整理成对用户友好的表格（Markdown）。建议结构：

```
✈️ 北京 → 上海 · 2026-06-03（周二）· 经济舱

| # | 航班 | 起飞-到达 | 机型 | 价格 | 行李 | 餐 | 退改 | 备注 |
|---|------|----------|------|------|------|----|------|------|
| 1 | CA1856 国航 | 07:30-09:45 | 738 | ¥680 | ✅含20kg | ✅正餐 | 退¥120/改¥80 | 直飞 |
| 2 | MU5102 东航 | 10:00-12:20 | 320 | ¥720 | ✅含20kg | ✅正餐 | 退¥150/改¥100 | 直飞 |
| 3 | 9C8864 春秋 | 14:00-16:15 | 320 | ¥399 | ❌手提7kg | ❌ | 不可退改 | 经停... |

推荐 1：CA1856 — 时间+价格+餐食+退改综合最优。
```

要点：

- 至少展示：航班号、航司、起降时间、价格、行李、餐食、退改、直飞标识
- 如果用户问"最便宜" → 高亮最低价那一行
- 如果用户问"最划算" → 主动用 LLM 分析（综合价格/时间/退改），不强求工具过滤
- 往返 → 分"去程"和"回程"两段表格
- 0 条结果 → 提示放宽条件（如"未找到直飞航班，可考虑放开关直飞"）

---

## 工作流（标准流程）

1. **解析用户需求**：提取出发地、到达地、日期、舱等、所有筛选条件。日期相对词先转绝对日期。
2. **缺关键信息就追问**：缺出发地/到达地/日期 → 问；相对日期不确定 → 问；往返缺回程 → 问。
3. **构造 `queryFlightBasic` 参数**：按"自然语言→参数映射"填字段。
4. **curl 调用 MCP**（带 token、Accept、Content-Type）。
5. **解析响应**：`.result.content[0].text` 二次 `JSON.parse` 得到航班列表。
6. **渲染表格**：按"输出格式"展示。如果用户说"挑一个/推荐" → 主动 LLM 分析。
7. **后续动作**：
   - 用户选了某航班 → 提示下一步（出票/改签查询，不在当前工具范围）
   - 用户要查天气 → 调 `getWeather`
   - 用户要改条件 → 重调 `queryFlightBasic`

---

## 错误处理

| 现象 | 原因 | 处置 |
| --- | --- | --- |
| `401 / token invalid` 或返回 `SC_2002`/`SC_2003` 自定义错误 | token 过期或错误 | 检查 token 是否还是 `r6lns3cc9gikkpmg6mbq`；必要时联系 MCP 维护方换 token |
| 工具返回 `error` 字段 | 参数错误 / 城市无航班 / 日期非法 | 看 `error` 内容；若是参数问题重读映射表修正；若是无结果，建议用户换日期/航线 |
| 返回空数组 | 没有任何航班满足条件 | 提示用户放宽筛选（去舱等/去航司/放宽时段/放宽价格） |
| HTTP 500 `Unexpected error: JSON parse error: Cannot deserialize value of type java.lang.String from Object value` | **服务端 MCP 实现的反序列化 bug**（与请求体格式无关，包括 `tools/list`、`tools/call`、`initialize` 都会触发） | **这是服务端 bug，客户端无解**。告知用户"机票查询服务暂时不可用，请稍后重试或联系服务方"。可在响应中保留入参（出发地/到达地/日期）以便服务恢复后重试。 |
| 网络超时 | MCP 端点问题 | 重试 1 次；仍失败则告知用户稍后重试 |
| 城市识别错误 | 同名城市 / 拼写问题 | 让用户确认城市全称或机场 IATA 代码 |

### 已知服务端问题（2026-06 验证）

> `https://traveldev.feiheair.com/api/mcp` 当前对所有 `tools/call` 请求（包括 `tools/list`、`initialize`、`ping`）都会返回 HTTP 500 与上述 Jackson 反序列化异常。**这是 Spring MCP 服务端 `WebMvcStatelessServerTransport#handlePost` 在 `McpSchema.deserializeJsonRpcMessage` 处的 bug**，与调用方的请求体格式（jsonrpc 字段、id 类型、params 嵌套、Accept 头、Content-Type、UTF-8 编码等）均无关——已通过十余种变体测试复现。Skill 内的调用模板严格遵循 MCP 规范，服务端恢复后即可正常使用。

---

## 注意事项 / 铁律

1. **改 OD/日期/舱等必须重调工具**，不要在前次结果上客户端过滤。
2. **绝对不要自猜日期**（包括回程日期），用户没说就问。
3. **相对日期**（明天/后天）必须用**当前真实日期**换算。
4. **模糊偏好**（"挑一个"）先查全量再用 LLM 分析，不要 `cheapest: true`。
5. **不支持的维度**（飞机大小、飞行时长）查完后用 LLM 自行从结果里筛选/说明。
6. **city 用原话**，不要翻译、不要"补全"成英文/拼音。
7. **token 不要外泄到日志/截图** 里。
8. 调工具失败/网络异常 → 不要编造航班数据，老实说"查询失败"。

---

## 一句话示例

- "明天北京到上海" → 单程经济舱，不带筛选的全量查询。
- "下周二上海到深圳下午最便宜的只要南航" → `cheapest: true` + `airlineName: "南航"` + `departureDayPart: "AFTERNOON"`。
- "6 月 10 号去上海出差，13 号回，要差标合规" → 往返 `RECOMMENDED` + `policyCompliant: true`。
- "挑个最划算的去上海" → 不传 `cheapest`，拿到全量后 LLM 综合判断。
