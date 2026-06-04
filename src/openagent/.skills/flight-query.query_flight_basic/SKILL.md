---
name: flight-query.query_flight_basic
description: "`queryFlightBasic` 深度规范 — 输入/输出完整 JSON Schema、错误码、自然语言→参数映射、5 个 use case、输出模板。**v1.4.0 修正**:实际工具名是 `queryFlightBasic`(camelCase 无 namespace),参数用中文城市名而非 IATA。父 skill `flight-query` 调用本子 skill 获取细节。"
version: 1.4.0
allowed-tools:
  - Bash
---

# query_flight_basic 深度规范 (On-Demand)

> **加载时机**:父 skill `flight-query` 提示"详见 `flight-query:query_flight_basic`"时;或 LLM 主动判断需要完整 schema 时。
>
> **本文档不重复**:endpoint / 协议 / token 契约(见父 skill `flight-query` §1 §2)。

---

## 1. 工具元信息

| 字段 | 值 |
|---|---|
| 名称 | `queryFlightBasic` |
| 描述 | 根据出发地/目的地/日期,查询国内航班及舱位列表。单程/往返均可。 |
| 入口守卫 | OD_CONFIRMED / FLIGHT_LISTED / FLIGHT_SELECTED(本 skill 不强制,只查票) |
| 写 ctx 副作用 | `ctx.resultSetId = data.serialNumber`;`ctx.flightList = data.flightList` 精简版 |
| 幂等 | 纯查询;`idempotencyKey` 可选(日志去重) |

---

## 2. 输入参数(模型只看这些)

> **v1.4.0 修正**(用户用 MCP Inspector 抓包验证):实际参数 schema 是中文城市名 + 中文 searchType 枚举,不是 IATA 码。

| 字段 | 类型 | 必填 | 取值 | 说明 |
|---|---|---|---|---|
| `departureCity` | string | ✅ | **中文城市名**,例 `北京` `上海` | **不是 IATA 码**!用户说 "BJS" / "PEK" 时 LLM 需先查父 skill §4.2 翻译成"北京"再发 |
| `arrivalCity` | string | ✅ | **中文城市名**,例 `深圳` `广州` | 同上 |
| `departureDate` | string (date) | ✅ | `yyyy-MM-dd` | 出发日期 |
| `searchType` | string | ❌ | `全量查询` (已确认);`低价查询` / `快速查询` (待实测) | 中文枚举,见 §2.1 |
| `returnDate` | string (date) | ❌(仅往返) | `yyyy-MM-dd` | **待 MCP 端实测确认**;MCP Inspector 暂未观察到往返调用的真实样本 |
| `journeyType` | int | ❌ | `0` `1` | **待 MCP 端实测确认**;MCP Inspector 暂未观察到 |

### 2.1 `searchType` 中文枚举(实测状态)

| 取值 | 实测 | 备注 |
|---|---|---|
| `全量查询` | ✅ MCP Inspector 已确认 | 默认推荐 |
| `低价查询` | ❓ 未实测 | 文档可能支持,**未确认前不要瞎传** |
| `快速查询` | ❓ 未实测 | 文档可能支持,**未确认前不要瞎传** |

> **不传 `searchType`**:服务端会用默认(应该是全量)。**新代码默认不传,需要时再加**。

> 系统标志位(`dataSource` / `cacheType` / `official` / `showPriceText` / `publicWeb` / `returnFcy` / `clientIdSpecify` / `dataSourceShowAllCab` / `choiceHf`)由 MCP Gateway 默认注入,模型不感知。

---

## 3. 输出结构(精简)

```jsonc
{
  "errorCode": "0",          // "0"=成功;非 0=业务错误
  "errorMsg":  "string",     // errorCode≠0 时展示
  "data": {
    "serialNumber": "260602152119A00000001",
    "flightList": [
      {
        "flightId": "MU6662",
        "flight": [
          {
            "flightId":  "MU6662",
            "airLine":   "SZXPKX",             // 起降机场组合
            "flyDate":   "2026-06-04 06:55:00",  // 起飞
            "arrDate":   "2026-06-04 10:10:00",  // 到达
            "fromPort":  "T3",                  // 出发航站楼
            "toPort":    "T2",                  // 到达航站楼
            "type":      "325",                 // 机型代码
            "stop":      0,                     // 经停;0=直飞
            "shareId":   "",                    // 共享航班主号;空=非共享
            "cabins": [
              {
                "cabId":     "11476",            // 舱位报价 ID(choose_cabin 回传)
                "cab":       "S",                 // IATA 订座类:Y/C/F/S/G
                "cabClass":  "Y1",                // 舱等大类:F/C/C1/W/W1/Y/Y1
                "cabName":   "经济舱",
                "num":       "A",                 // 余票:"A"≥9,"B"=8,数字<9 时直显
                "price":     1360,                // 实际售价(含税)
                "normalPrice": 1360,
                "clientService": 27.2,            // 机建+燃油(已含 price)
                "priceType": 0,                   // 0=普通;1=特价(退改严格)
                "weight":   "20",
                "portableWeight": "8",
                "luggage":  "...",
                "refund":   "...",
                "change":   "...",
                "refundRules":  "...",
                "changeRules":  "..."
              }
            ]
          }
        ]
      }
    ],
    "citys":    [...],   // cityCode → cityName/airPortName
    "airways":  [...],   // companyNo → companyName
    "types":    [...]    // type → name
  }
}
```

### 模型阅读指引

- **优先读**:`flightId` `flyDate` `arrDate` `fromPort/toPort` `stop` `cabins[].cabId/cabName/cabClass/num/price`
- **不主动读**:`baf/acf/mile/fullPrice/mealCode/weight/portableWeight` 等附属字段
- **字典**(`citys/airways/types`)只在用户问"哪个航司/哪个机场/什么机型"时按 key 反查

---

## 4. 错误码

| 错误码 | 含义 | 重试 | 处置 |
|---|---|---|---|
| `errorCode≠0` + `tmsErrorCode=""` | 业务级失败(无航班/参数非法/协议关闭) | ❌ | 按 `errorMsg` 提示用户 |
| `TMS_TIMEOUT` | 上游超时 | ✅ ×3,指数退避 | 仍失败 → "系统繁忙,请稍后重试" |
| `PRICE_UNAVAILABLE` | 协议价未下发 | ❌ | 提示换日期或换舱等 |
| `OD_NOT_SERVED` | 该 OD 不在产品范围 | ❌ | "该航线暂不支持" |
| HTTP 4xx/5xx | 网络/服务端问题 | 视情况 | 见父 skill `flight-query` §5 |

---

## 5. 自然语言 → 参数映射

### 5.1 城市(必须**中文名**,IATA 仅作翻译辅助)

| 用户原话 | LLM 翻译步骤 | 最终 `departureCity` / `arrivalCity` |
|---|---|---|
| 北京 | (已经是中文) | `北京` |
| BJS / PEK / PKX / 首都 / 大兴 | 查父 skill §4.2 → `北京` | `北京` |
| 上海 | (已经是中文) | `上海` |
| SHA / PVG / 虹桥 / 浦东 | 查父 skill §4.2 → `上海` | `上海` |
| 深圳 | (已经是中文) | `深圳` |
| SZX / 宝安 | 查父 skill §4.2 → `深圳` | `深圳` |
| (其他) | **加载 `flight-query:iata_icao_codes` 子 skill** | 表里没有 → 主动问用户 |

> **歧义**: 用户说"虹桥/浦东/首都/大兴"等具体机场 → 翻译成"上海"/"北京"等城市名,在结果展示时备注"按 XX 机场搜索"。

### 5.2 日期

- 相对日期(明天/后天/大后天/下周X)→ 用**当前日期**转 `yyyy-MM-dd`,**月份/日期必须补零**(`2026-06-03`)
- "明天下午" → 日期进 `departureDate`,本接口**不支持**时段筛选
- 不知道日期 → 主动问,**禁止自猜**
- 往返缺 `returnDate` → 必问,**禁止自猜**

### 5.3 searchType

| 用户原话 | `searchType` |
|---|---|
| 不限 / 没指定 / "查所有" | 省略字段(让服务端默认) |
| 明确说"要低价的" | `低价查询`(实测未确认,**未确认前不传**) |
| 明确说"要最快的" | `快速查询`(实测未确认,**未确认前不传**) |
| 兜底 | 省略字段 |

> **v1.4.0 变更**: 移除旧 `cabClass`(Y/C/F/W)映射 — 当前 MCP `queryFlightBasic` 实际接口**没有** `cabClass` 字段,舱等由 MCP 端按协议价返回,LLM 拿到结果后展示。

### 5.4 本接口**不**支持的筛选(别瞎拼)

| 不支持 | 替代 |
|---|---|
| `cheapest: true` | 老老实实拿全量,LLM 自行选 |
| `sortBy: PRICE/DURATION/...` | 同上 |
| `airlineName: "南航"` | 不支持航司过滤,拿全量后用户挑 |
| `nonStop: true` | 不支持直飞过滤,看 `stop=0` 自行标 |
| `baggage: true` / `requireMeal: true` | 不支持,展示时看 `weight` / `mealCode` 字段 |
| `maxPrice: 800` | 不支持价格过滤,展示全量 |
| `refundable: true` / `freeRefund: true` | 不支持,展示时看 `refund` 字段 |
| `policyCompliant: true` | 不支持差标,服务端另外有 `validate_booking_info` |
| `roundTripListMode: RECOMMENDED/FREE` | 不支持,往返回多个 `flightId` 就行 |
| `departureDayPart: MORNING/AFTERNOON/EVENING` | 不支持时段 |
| `depTimeStart` / `depTimeEnd` | 不支持时间范围 |
| `excludeAirlineKeywords` | 不支持排除航司 |

---

## 6. 5 个 use case

> 下面是 `arguments` 字段 — 实际请求需包裹到 JSON-RPC 2.0 envelope:
> ```json
> {
>   "jsonrpc": "2.0", "id": 1, "method": "tools/call",
>   "params": { "name": "queryFlightBasic", "arguments": { ... } }
> }
> ```

### 6.1 单程 · 全量(默认)

```json
{
  "departureCity": "深圳",
  "arrivalCity":   "成都",
  "departureDate": "2026-06-05"
}
```

### 6.2 单程 · 全量 · searchType 显式

```json
{
  "departureCity": "北京",
  "arrivalCity":   "上海",
  "departureDate": "2026-06-04",
  "searchType":    "全量查询"
}
```

### 6.3 往返(待实测)

```json
{
  "departureCity": "北京",
  "arrivalCity":   "上海",
  "departureDate": "2026-06-08",
  "returnDate":    "2026-06-13",
  "journeyType":   1
}
```

> ⚠️ `returnDate` / `journeyType` 当前**未在 MCP Inspector 抓包中观测到**;服务端可能支持也可能不支持。新代码默认单程,需要往返时**先实测一次**确认格式。

### 6.4 重查(改 OD/日期)—— 必须重调,**不**做客户端过滤

> **铁律**:改了 `departureCity` / `arrivalCity` / `departureDate` / `searchType` 任何一个,必须**重新调用** `queryFlightBasic`,**不**在前次结果上做客户端过滤。

### 6.5 城市/机场解析失败时

不要瞎猜中文名。先:
1. 查 `iata_icao_codes` 子 skill 的速查表
2. 表里没有 → 主动问用户"请确认出发/目的地城市中文名" 或 "请提供机场代码"

> **v1.4.0 变更**: 旧版 use case 6.2 / 6.3 用的 `cabClass` 字段已删除 — 服务端接口**没有**该字段,展示时由 LLM 在结果里挑舱等呈现给用户。

---

## 7. 输出格式模板

```markdown
✈️ 深圳(SZX) → 成都(CTU) · 2026-06-05(周五) · 全舱位

| # | 航班 | 起飞-到达 | 航站楼 | 经停 | 最低价 | 舱位 | 余票 |
|---|------|----------|--------|------|--------|------|------|
| 1 | MU6662 东航 | 06:55-10:10 | T3→T2 | 直飞 | ¥1,360 | 经济舱 | ≥9 |
| 2 | CA1856 国航 | 07:30-09:45 | T2→T3 | 直飞 | ¥1,480 | 经济舱 | 5 |
| 3 | 3U8888 川航 | 14:00-16:15 | T1→T2 | 直飞 | ¥980   | 经济舱 | 3 |

共 3 个航班,推荐 1(MU6662 直飞 + 余票充足)。
```

要点:
- 至少展示:航班号、航司、起降时间、航站楼、经停、最低价
- 余票: `'A'`/`'B'` → `≥9`/`8`,数字直显
- 价格: `¥1,234.00` 格式
- 0 条结果 → 提示放宽(换日期/换舱等/换 OD)
- 往返 → 分"去程"和"回程"两段表格

---

## 8. 工作流(标准)

1. 解析需求 → 中文城市名 + 日期 + searchType
   - 用户说 IATA / 机场名 → 查父 skill §4.2(或 `iata_icao_codes` 子 skill)翻译
2. 缺信息 → 追问(OD/日期/返程日期)
3. 构造 `queryFlightBasic` 入参(`arguments` 字段,**用 §6 的实际 schema**)
4. 包成 JSON-RPC 2.0 envelope:
   ```json
   {"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"queryFlightBasic","arguments":{...}}}
   ```
5. 调 MCP(从 system 块取 `MCP_TOKEN` 填 `Authorization: Bearer <token>` header,见父 skill §1)
6. `.result.content[0].text` 二次 `JSON.parse`
7. 按 §7 渲染表格
8. 用户要换条件 → 重调(§6.4 铁律)
9. 用户要下单 → 切 `flight-booking` skill(本 skill 不接单)
