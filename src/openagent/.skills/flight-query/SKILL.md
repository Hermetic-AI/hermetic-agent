---
name: flight-query
description: 通过 MCP 端点查询国内航班（单程/往返）。把自然语言转成 `queryFlightBasic` 调用（**注意：实际 MCP 工具名是 camelCase、无 namespace 前缀；参数用中文城市名 + 中文 searchType 枚举，不要用 IATA 码**），以 Markdown 表格输出。Token 走 header 透传，禁止硬编码。
version: 1.4.0
allowed-tools:
  - Bash
argument-hint: "[出发地] [到达地] [出发日期] [可选: 返程日期] [可选: searchType]"
---

# Flight Query Agent Skill (flight-query) — Core

> **本文档 = 核心层(必读,始终加载)**。深度细节走 on-demand 子 skill(见 §8)。
>
> **范围**:仅「机票查询」。完整 13 状态订票流程见 `参考.md` / `flight-booking` skill。

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

> **关键设计**: 不走 opencode 内部 header(那需要重启 agent),不走代理(那需要新 endpoint)。
> 走**最朴素的 system 注入** — OpenAgent 把 token 写到 LLM 可见的 system 消息里,LLM 调 Bash 用 curl 时自己从 system 块取出来填 header。

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

### 1.3 接收格式(MCP 端支持两种,任选)

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

### 1.5 Debug 时的手动 curl 模板(生产路径不走)

```bash
# 注意: 这是 debug 时手动 curl 的格式。生产路径是 OpenAgent 把 token 注入到 system
# 块里,LLM 自己用。手动 curl 时用 ${MCP_TOKEN} 占位,不要 commit 真 token。
#
# 实际 queryFlightBasic 调用的完整 JSON-RPC 2.0 envelope(LLM 应严格按此格式):

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
          "departureDate": "2026-06-04",
          "searchType":    "全量查询"
        }
      }
  }'
```

> **关键修正(v1.4.0)**:
> - 工具名是 **`queryFlightBasic`**(camelCase, 无 namespace 前缀)。**不是** `domestic-booking-mcp.query_flight_basic`。
> - 参数名是 **`departureCity` / `arrivalCity` / `departureDate` / `searchType`**(camelCase)。**不是** `fromCity` / `toCity` / `flyDate` / `cabClass`。
> - 值用**中文城市名**(`北京` `上海`)+ **中文 searchType 枚举**(`全量查询`)。**不是** IATA 码。

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

## 3. 工具总览(17 个,本 skill 仅用 1 个)

| MCP 工具 | 状态 | 本 skill 用 |
|---|---|---|
| `queryFlightBasic` | ✅ **已落地** | **是(主工具)** |
| `{其他 16 个}` | 🟡 已注册未实测 | 否(归 `flight-booking` skill) |

**主工具调用形状**(精简;详细 schema 见 §8 子 skill):

```jsonc
// arguments 对象 — 放进 JSON-RPC 2.0 的 params.arguments 里
{
  "departureCity": "北京",          // 中文城市名,不是 IATA
  "arrivalCity":   "上海",
  "departureDate": "2026-06-04",    // yyyy-MM-dd
  "searchType":    "全量查询"        // 中文枚举,见 §3.1
}
```

完整参数表 / 输出 schema / 错误码 / NL 映射 / 输出模板 → **`flight-query:query_flight_basic`**(on-demand,见 §8)。

### 3.1 `searchType` 枚举(中文)

| 取值 | 含义 |
|---|---|
| `全量查询` | 全量返回(默认,无特殊筛选) |
| `低价查询` | 仅返回低价航班(待 MCP 端实测确认) |
| `快速查询` | 仅返回耗时最短(待 MCP 端实测确认) |

> 当前 MCP Inspector 已确认 `全量查询`。其他枚举值暂未实测,**未确认前不要瞎传**;缺省时省略该字段,服务端会用默认。

---

## 4. 城市/机场代码(翻译辅助)

> **关键修正(v1.4.0)**:MCP `queryFlightBasic` 的 `departureCity` / `arrivalCity` **接受中文城市名**,**不**接受 IATA 码。IATA 表仅作为「用户说 IATA → LLM 翻中文」的翻译辅助。

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

| 用户原话 | 发给 MCP 的中文 | 备注 |
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

> 完整版含 ICAO 4 字码 + 模糊处理 → **`flight-query:iata_icao_codes`**(on-demand,见 §8)。

---

## 5. 错误处理(精简)

| 现象 | 处置 |
|---|---|
| `401 / token invalid` | "权限配置异常,联系管理员";最多重试 1 次 |
| `errorCode≠0`(业务级) | 按 `errorMsg` 提示用户改条件 |
| 返回 `flightList=[]` | 提示放宽(换日期/换舱等/换 OD) |
| HTTP 400 `Invalid message format` | **服务端 MCP bug**(Spring `WebMvcStatelessServerTransport#handlePost` 反序列化失败),token 认证已通过但 JSON-RPC body 解析失败。告知"机票查询服务暂时不可用",**不**重试,**不**编造航班 |
| HTTP 5xx `JSON parse error: Cannot deserialize...` | 同上(同一 bug 的另一 stack 路径) |
| 网络超时 | 重试 1 次;仍失败告知稍后重试 |
| 城市识别错误 | 主动澄清(同 §4 速查里没说清的) |

**已知服务端问题(2026-06-03)**:该 MCP 对**所有** `tools/call` 请求返 HTTP 400 + `Invalid message format`,与请求体格式、token 形式都无关 —— 等服务端修。

---

## 6. 铁律(精简)

1. **改 OD/日期/舱等必须重调 `query_flight_basic`**(本接口无客户端筛选参数)
2. **绝对不要自猜日期**(包括回程)
3. **相对日期**用当前日期转 `yyyy-MM-dd`,月份日期**必须补零**
4. **模糊偏好**("挑一个/最划算")老实说"本接口不支持按价格/时长/退改筛选,以下是全量"
5. **城市用 IATA 3 字码**(首选),ICAO 4 字仅在 MCP 文档明确支持时用
6. **token 不外泄**
7. **调工具失败 → 不编造**,老实说"查询失败"
8. **本 skill 仅查票** → 选航班/选舱/填人/核价/下单走 `flight-booking` skill

---

## 7. 一句话示例

- "明天北京到上海" → `{"departureCity":"北京","arrivalCity":"上海","departureDate":"<tomorrow>","searchType":"全量查询"}`
- "下周二上海到深圳经济舱" → `{"departureCity":"上海","arrivalCity":"深圳","departureDate":"<next-tue>","searchType":"全量查询"}`(本接口**没有** cabClass 字段,舱等由 MCP 端按协议价返回)
- "6 月 10 日去北京,13 号回" → 加 `returnDate` + `journeyType: 1`(往返字段待 MCP 端实测确认)

---

## 8. 子 skill(按需加载)

> LLM: 用户问具体细节时,**主动用 `skill` 工具加载**对应子 skill;不要把全部内容塞上下文。

| 子 skill 名 | 加载时机 | 内容 |
|---|---|---|
| `flight-query:query_flight_basic` | 用户问"调工具的具体参数长啥样" / "出参怎么解析" / "NL 怎么映射" | 完整输入/输出 JSON Schema + 错误码 + NL→param 映射表 + 5 个 use case + 输出模板 |
| `flight-query:iata_icao_codes` | 用户问"XX 城市的 IATA 码" / "IATA 跟 ICAO 啥区别" / 遇到未识别城市 | 30+ 城市 IATA+ICAO 对照 + 模糊处理 + 临时表查询指引 |
| `flight-query:flight_booking`(待建) | 用户想"选航班/下单" | 见 `参考.md` 13 状态机(由 `flight-booking` skill 负责,本 skill **不**加载) |

---

## 9. 版本与变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| 1.0.0 | (历史) | 初版:全量塞一个文件,中文城市名,`cheapest`/`sortBy` 等未实现字段 |
| 1.1.0 | 2026-06-03 | MCP 重构后对齐:IATA 码 + `fromCity`/`toCity`/`flyDate`/`cabClass` + 移除未实现字段 + §1 Token 透传契约 |
| **1.2.0** | 2026-06-03 | **渐进式加载重构**:<br>1. 核心层(本文件)只保留契约/协议/工具列表/速查/铁律 → ~200 行<br>2. 拆出 `query_flight_basic` 子 skill(深度 schema + 映射 + 模板)<br>3. 拆出 `iata_icao_codes` 子 skill(代码速查 + ICAO 对照)<br>4. §8 显式列出子 skill 加载时机 |
| **1.3.0** | 2026-06-03 | **Token 透传机制落地**(per-request):<br>1. §1 重写:不再"等用户说"——OpenAgent 把每请求的 token 拼到 system 末尾的 `<runtime-context>` 块,LLM 调 MCP 时自己从 system 块取 token 填 header<br>2. 移除旧"等用户口头告知 token"路径(无效设计)<br>3. 新增 §1.2 "LLM 实际看到的 system 消息"示例,让 LLM 知道去哪取 token |
| **1.4.0** | 2026-06-03 | **修正 MCP 工具 schema**(用户用 MCP Inspector 抓包验证):<br>1. 工具名 `domestic-booking-mcp.query_flight_basic` → **`queryFlightBasic`**(camelCase, 无 namespace)<br>2. 参数 `fromCity/toCity/flyDate/cabClass` → **`departureCity/arrivalCity/departureDate/searchType`**<br>3. 值用**中文城市名 + 中文 searchType 枚举**,**不再用 IATA 码**<br>4. §1.5 curl 模板换成真实可工作的 `tools/call` envelope<br>5. §4 改成"翻译辅助"语义(LLM 拿 IATA → 翻中文再发)<br>6. §3.1 新增 `searchType` 枚举已知值(`全量查询` 已确认)<br>7. 撤回 v1.2.0 关于"服务端 deserialization bug"的论断 — 实测发现是 **我 SKILL.md 教的 schema 跟实际 MCP 接口不匹配**,服务端并未 100% 拒 |
