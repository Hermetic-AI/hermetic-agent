---
name: fh-international-flight-booking
description: |
  Use when the user wants to search, compare, or book international flights
  via the fh-travel backend. Covers: intent detection, permission check,
  flight search (intShopping), cabin/price selection, refund rules (intRule),
  pricing verification (intPricing), travel policy (intPolicy), trip application
  matching, passenger/cost-center binding, order creation (saveOrder), and
  payment. Triggers on keywords: 国际机票, international flight, 出境机票,
  跨国航班, book international, intl flight.
version: "1.0.0"
---

# FH International Flight Booking

## Purpose

通过 **原生 HTTP 直连** fh-travel 后端完成国际机票查询与订购全流程。
不使用 MCP，不经过 mcporter bridge。所有 API 调用通过 `scripts/http_client.py`
封装，Token 从环境变量 `FLIGHT_API_KEY` 动态注入（Hub 在会话开始时通过 sandbox
admin API 注入，与国内机票场景共用同一 token）。

Agent 通过 **bash 工具** 执行 `python3 /work/shared/skills/fh-international-flight-booking/scripts/http_client.py <path> '<body-json>'`
发起 HTTP 请求。不依赖 MCP 工具。

**重要**：沙箱内只有 `python3`（无 `python`），只有 `requests`（无 `httpx`）。
脚本已使用 `requests` 替代 `httpx`。

本 Skill 只做：意图识别 → 参数组装 → API 调用 → 结果精简 → AGUI 卡片渲染。
**不**重新实现后端业务逻辑、差旅政策引擎或订单状态机。

## Load Strategy (渐进式披露)

只加载本文件。按需加载一个资源：

| 触发条件 | 加载文件 |
|---|---|
| 首次调用任何 API 前 | `references/api-endpoint-map.md` |
| Token / 鉴权异常 | `references/auth-and-token-flow.md` |
| 首次渲染国际机票卡片 | `references/agui-mapping.md` |
| 进入 Step 1 (意图/权限) | `workflows/intent-and-permission.md` |
| 进入 Step 2 (航班查询) | `workflows/flight-search.md` |
| 进入 Step 3 (选航班/舱) | `workflows/flight-selection.md` |
| 进入 Step 4 (核价/差标) | `workflows/pricing-and-policy.md` |
| 进入 Step 5 (备单/组装) | `workflows/order-preparation.md` |
| 进入 Step 6 (下单/支付) | `workflows/order-submit-and-payment.md` |
| 阶段不确定 | `schemas/state-machine.json` |
| API 前置参数校验 | `schemas/api-contracts.json` |
| 用户说中文城市名 | `context/city-code-lookup.md` |

不要用 `webfetch` 读取 `file://` 路径。本地文件只能用 `read` 工具读取；常用城市直接用本文件内置映射。
快速查询路径不需要再读取任何 `references/*` 或 `context/*` 文件，避免触发外部目录审批。

## Hard Fast Path (必须遵守)

如果用户原话中已经包含 **出发城市 + 到达城市 + 出发日期**，必须直接查询，不得发 `OD_INPUT`/`ask_user` 要用户重复填写。
该路径是自包含流程：不要先读 `references/api-endpoint-map.md`，不要读 `context/city-code-lookup.md`，不要读 `agui-mapping.md`。

完整查询示例：

| 用户原话 | 判断 | 行动 |
|---|---|---|
| `帮我查询深圳到曼谷的明天的单程机票` | 已包含出发=深圳、到达=曼谷、日期=明天、单程 | 直接调用 `intShopping` |
| `查北京到东京7月1日国际机票` | 已包含出发、到达、日期 | 直接调用 `intShopping` |

默认值仅用于查询，不要追问：

| 字段 | 默认值 |
|---|---|
| `passengerType` | `ADT` |
| `language` | `cn` |
| `stopQuantity` | `0` |
| 单程 | `tripList` 只放 1 段 |

常用城市三字码：深圳=SZX，北京=PEK，上海=PVG，广州=CAN，香港=HKG，东京=NRT，
大阪=KIX，首尔=ICN，曼谷=BKK，新加坡=SIN，吉隆坡=KUL。

对于“深圳到曼谷明天单程”，直接执行：

```bash
python3 /work/shared/skills/fh-international-flight-booking/scripts/http_client.py /air/international/intShopping '{"stopQuantity":0,"language":"cn","passengerType":"ADT","tripList":[{"fromCity":"SZX","toCity":"BKK","flyDate":"<明天yyyy-MM-dd>","isCity":true}]}'
```

只有拿到真实 API 返回后才能发送 `FLIGHT_RESULT`。禁止先发送“正在查询”的 `FLIGHT_RESULT` 假卡片。

**重要：航班卡片由 Hub 自动生成，你不需要手动渲染。**
调用 `intShopping` 后，Hub 会自动拦截 API 返回结果并生成 `FLIGHT_RESULT` 卡片发送给用户。
你**不要**调用 `compact_intl_payload.py` 或 `render_intl_options.py`，
也**不要**调用 `ask_user` 发送 `FLIGHT_RESULT` 卡片。
你只需要在卡片发送后，用简短的文字告诉用户查询结果概要（如航班数量、推荐航班），
然后等待用户选择航班。

## Token & Auth

- Token 由 Hub 在会话开始时通过 sandbox admin API 注入环境变量 `FLIGHT_API_KEY`
  （与国内机票场景共用同一 token，由 `_push_flight_token_to_opencode` 写入）
- **不要**向用户索要、解释、回显 token
- 所有 API 调用通过 `scripts/http_client.py` 的 `api_post()` 自动注入 header
- 若 `FLIGHT_API_KEY` 缺失 → 立即终止，发 `CANNOT_ORDER` 卡片

## API 调用方式

Agent 通过 bash 工具执行 Python3 脚本发起 API 调用：

```bash
# 航班查询（注意：用 python3，不是 python）
python3 /work/shared/skills/fh-international-flight-booking/scripts/http_client.py /air/international/intShopping '{"tripList":[{"fromCity":"SZX","toCity":"BKK","flyDate":"2026-06-18","isCity":true}]}'

# 核价
python3 /work/shared/skills/fh-international-flight-booking/scripts/http_client.py /air/international/intPricing body.json

# 差标校验
python3 /work/shared/skills/fh-international-flight-booking/scripts/http_client.py /air/international/intPolicy body.json

# ... 其他 API 同理
```

请求体 JSON 可以是文件路径（.json 结尾）或直接传入 JSON 字符串。
脚本自动注入 Token header，处理超时和错误，输出 JSON 结果到 stdout。

**沙箱内 Python 路径为 `python3`，不要用 `python`。**

## Core State Machine (14 阶段)

```
INIT → PERMISSION_CHECKED → SEARCH_PARAMS_READY → FLIGHT_LISTED
→ GROUP_SELECTED → PRICE_SELECTED → RULE_CHECKED
→ PRICING_VERIFIED → POLICY_CHECKED → WAIT_SAVE_LOADED
→ PASSENGER_FILLED → ORDER_SUBMITTED → PAYMENT_VERIFIED → FINISHED
```

分支与回退见 `schemas/state-machine.json`。
任何阶段权限/风控拦截 → `CANNOT_ORDER`（终态）。

## API Route Table (高精度路由)

| Step | 业务动作 | API 端点 | 前置依赖 (必须来自上游返回) | Workflow |
|---|---|---|---|---|
| 1 | 权限+客户配置 | `POST /air/customer/getClientBasicData` | Token | `intent-and-permission.md` |
| 1 | 当前用户信息 | `POST /customer/mine/getMineBasicData` | Token | `intent-and-permission.md` |
| 2 | 航班查询 | `POST /air/international/intShopping` | `tripList[].fromCity/toCity/flyDate` | `flight-search.md` |
| 2 | 签证提醒 | `POST /air/international/visa` | `fromCity/toCity`(三字码) | `flight-search.md` |
| 3 | 退改规则 | `POST /air/international/intRule` | `serialNumber`←intShopping, `priceId`←intShopping | `flight-selection.md` |
| 4 | 核价 | `POST /air/international/intPricing` | `serialNumber`+`priceId`←intShopping | `pricing-and-policy.md` |
| 4 | 差标校验 | `POST /air/international/intPolicy` | `serialNumber`+`priceId`←intShopping | `pricing-and-policy.md` |
| 4 | 出差单校验 | `POST /air/international/intCheckApplication` | `applicationId`←用户/OA, `serialNumber`+`priceId` | `pricing-and-policy.md` |
| 5 | 待下单数据 | `POST /air/international/waitSave` | `serialNumber`+`priceId`+`pricingId`←intPricing | `order-preparation.md` |
| 5 | 乘机人查询 | `POST /air/customer/findPassenger` | Token, `productType=INTERNATIONAL` | `order-preparation.md` |
| 5 | 归属公司 | `POST /air/customer/listClientBelongCompany` | Token | `order-preparation.md` |
| 5 | 项目组 | `POST /air/customer/getClientProject` | Token | `order-preparation.md` |
| 5 | 出差单列表 | `POST /application/listOneUserApplicationsByUserCodeCertNoDateRange` | `userCode`←getMineBasicData | `order-preparation.md` |
| 5 | 国籍代码 | `POST /params/system/nationality` | Token | `order-preparation.md` |
| 5 | 地址列表 | `POST /air/customer/getPassengerAllAddress` | Token | `order-preparation.md` |
| 6 | 提交订单 | `POST /air/international/saveOrder` | 全字段←waitSave+findPassenger+用户选择 | `order-submit-and-payment.md` |
| 6 | 支付验证 | `POST /air/domestic/getPlaneSendpki` | `orderGroup`←saveOrder.orderGroupId | `order-submit-and-payment.md` |
| 6 | 提交支付 | `POST /air/domestic/submitPlaneSendpki` | `orderBasicDataJson`←getPlaneSendpki | `order-submit-and-payment.md` |

### 前置参数强校验规则

**在调用任何 API 前，必须确认所有前置参数已存在于当前会话上下文。**
缺失任何一个 → **禁止调用 API**，改为：

1. 若参数可从上游 API 返回中获取但未获取 → 先调用上游 API
2. 若参数需用户提供 → 发 `ask_user` 卡片一次性收集所有缺失字段
3. 若参数不可获取（如 Token 缺失）→ 发 `CANNOT_ORDER`

**参数溯源表**（关键参数）：

| 参数 | 来源 | 禁止猜测 |
|---|---|---|
| `serialNumber` | `intShopping` 返回 `data.serialNumber` | 禁止编造 |
| `priceId` | `intShopping` 返回 `groupList[].priceList[].priceId` | 禁止编造 |
| `pricingId` | `intPricing` 返回 `data[].priceId`（核价返回的 priceId 即 pricingId） | 禁止编造 |
| `applicationId` | 用户提供 或 OA 跳转 或 `listOneUserApplications` 返回 | 禁止编造 |
| `clientId` | `getClientBasicData` 返回 或用户指定 | 禁止编造 |
| `depId` | `getMineBasicData` 返回 `data.depId` 或用户选择成本中心 | 禁止编造 |
| `userCode` | `getMineBasicData` 返回 `data.userCode` | 禁止编造 |

## Fast Path

用户已提供 **出发城市 + 到达城市 + 出发日期** 时：

1. 规范化日期（"明天" → `2026-06-18`）
2. 查 `context/city-code-lookup.md` 获取三字码（若用户说中文城市名）
3. 并行调用 `getClientBasicData` + `getMineBasicData`（权限预检）
4. 权限通过 → 立即调用 `intShopping`
5. **不要**先问舱等、先问人数、先调 `ask_user`
6. **不要**发送 OD_INPUT 或“正在查询”的 FLIGHT_RESULT 假卡片

## Operating Rules

1. **Token 自动注入**：所有 API 调用走 `scripts/http_client.py`，不要手写 curl/httpx/requests。
2. **中文优先**：所有回复、卡片标题、字段标签、按钮文案、错误说明使用中文。
3. **先提取后追问**：从用户原话提取行程/日期/人数/舱等偏好，只问真正缺失的字段。
4. **合并提问**：多个缺失字段合并到一个 `ask_user` 卡片。
5. **禁止编造**：航班号、价格、税费、舱位、退改规则、政策结果、订单号一律来自 API 返回。
6. **阶段顺序**：按状态机推进，不跳阶段。调用 `scripts/stage_guard.py` 校验。
7. **航班卡片自动生成**：`intShopping` 返回后，Hub 会自动拦截结果并生成 `FLIGHT_RESULT` 卡片。**不要**调用 `compact_intl_payload.py` 或 `render_intl_options.py`，**不要**用 `ask_user` 手动发 `FLIGHT_RESULT`。你只需在卡片后用文字概述结果并等待用户选择。
8. **错误处理**：API 返回 `errorCode != "0"` → 中文翻译 errorMsg → 发 `CANNOT_ORDER` 或提示用户。
9. **网络故障**：HTTP 超时/不可达 → 发 `CANNOT_ORDER`，reason 用中文，fallback 建议稍后重试。**不要**切换 curl/wget/webfetch 重试。
10. **单会话单线程**：一个会话保持一个 `serialNumber`，不混用不同查询的结果。
11. **往返/多程**：`tripList` 数组长度 > 1 时，按 `io=0`（去程）/ `io=1`（回程）分别展示。详见 `workflows/flight-selection.md`。
12. **签证信息**：`intShopping` 返回的 `visaInfoList` 不为空时，必须在航班卡片后附加签证提醒 PLAIN_TEXT。
13. **禁止过程叙述**：不要输出任何关于你正在做什么的叙述性文字。禁止说"正在查询"、"现在渲染卡片"、"让我查询"、"let me render"、"now I'll query" 等元评论。直接执行操作，只输出用户需要的结果信息（航班详情、选择提示等）。
14. **严格查询范围**：只查询用户明确请求的行程。用户说"深圳到曼谷"就只查深圳→曼谷，**绝对不要**自行扩展查询其他航线（如曼谷→吉隆坡、吉隆坡→上海等）。用户没说单程就默认单程，不要自作主张加返程或中转。
15. **航班选择后的流程**：当用户消息包含"帮我订"或"我选择航班"且包含 `[选择参数: groupId=..., priceId=...]` 时，说明用户从航班卡片中选择了航班。你必须：
    - 从消息中提取 `groupId` 和 `priceId`
    - 如果消息包含"可选舱位/价格方案"列表，展示这些方案让用户选择（发 `ask_user` 卡片，`card_type="FLIGHT_RESULT"`，body 用 `PLAIN_TEXT` 展示价格方案表格）
    - 用户选择方案后，用对应的 `priceId` 继续后续流程（核价 intPricing、退改 intRule 等）
    - **不要**重新查询航班，**不要**要求用户重复提供航班信息
16. **API 参数格式**：调任何业务 API 前必须先读对应 workflow 文件确认参数格式：
    - `intPricing`：`{"language":"cn","flightList":[{"serialNumber":"...","priceId":"..."}]}`，**不是**平铺的 `serialNumber` + `priceId` + `tripList`
    - `intPolicy`：`{"flightList":[{"serialNumber":"...","priceId":"..."}]}`
    - `waitSave`：`{"language":"cn","flightList":[{"serialNumber":"...","priceId":"...","pricingId":"..."}]}`，`pricingId` 来自 `intPricing` 返回的 `data[0].priceId`
    - `intRule`：`{"serialNumber":"...","priceId":"..."}`（这个用平铺格式）
    - **禁止**盲目试错：参数错误时**第一次**失败就立即读 workflow 文件确认格式，**禁止**重复试错 3 次以上浪费 token
17. **saveOrder 关键参数（必读，违反会导致 TMS_1002 "没有指定客户下单权限"）**：
    - `flightList[0].pricingId` = **`intPricing` 返回的 `data[0].priceId`**（**字面长串**如 `"1,abc...,10,1E,TCPL,1"`），**不是** `"1"` 或 `priceId` 的简写。LLM 常见错误：把 `pricingId` 填成 `"1"`（字面量），导致核价 cache 错位、后端校验失败。
    - `flightList[0].priceId` = `intShopping` 返回的 `groupList[].priceList[].priceId`（也是长串）
    - `flightList[0].serialNumber` = `intShopping` 返回的 `data.serialNumber`
    - **三者** 都来自前序 API 返回，**禁止**自创或简化。
    - 顶层 `clientId`：传 `""`（空字符串，让后端根据 `depId` 自行判断客户）。**不要**传 `getClientBasicData` 返回的 `clientId`（那是查询参数，不一定是下单客户）。
    - 顶层 `depId`：传 `""`（空），下单客户由 `passengerList[0].depId`（来自 `findPassenger`）决定。
    - `passengerList[0].name`：用**护照/证件上的拼音**（如 `"LIU/YUNZE"`），**不是**中文姓名。
    - `passengerList[0].idType` = `"0"`（护照），`idNumber` = 护照号，`idExpiration` = 护照有效期（必填），`birthday` = 出生日期（必填）。
    - 必须从 `findPassenger` 响应里取 `cardId`（证件表 ID）填到 `passengerList[0].cardId`。
18. **saveOrder 失败立即读 workflow（避免连续试错）**：
    - saveOrder 第一次返回 `errorCode != "0"` 时，**立即** `cat workflows/order-submit-and-payment.md` 重新读 §6.2 字段表，**不要**继续猜字段。
    - 常见报错对照表（直接查这个表，不要猜）：
      | 错误码/消息 | 真正缺/错的字段 |
      |---|---|
      | `乘客类型不能为空` | `passengerList[0].passengerType` 缺失（填 `"0"` 字符串） |
      | `国籍代码不能为空` | `passengerList[0].nationality` 缺失（填 `"CN"`） |
      | `发证国家不能为空` | `passengerList[0].issueCountry` 缺失（填 `"CN"`，**不是** `certIssuePlace`） |
      | `国际机票保存订单有误: 没有指定客户下单权限` | 顶层 `clientId`/`depId`/`pricingId` 组合错（参考 Rule 17） |
    - **禁止**在读 workflow 之前就改字段名/换值乱试。**禁止**重复试错 ≥2 次浪费时间。
19. **公费挂账跳过 getPlaneSendpki / submitPlaneSendpki**：
    - saveOrder 返回成功后，看 `data.orderList[].recPrice` 应付金额 → 如果是公费挂账场景（用户选了非个人现付），**不要**调 getPlaneSendpki 和 submitPlaneSendpki。
    - 直接告诉用户"订单已创建，订单号 XXX，PNR XXX，请登录企业后台完成支付或联系审批人（X人）"。
    - 这两步在公费挂账场景下后端会因 `payType` 超出范围（`[1-5]`）报 `TRAVELAIR_1006`，浪费 5-10 秒。

20. **getPlaneSendpki 响应已精简**（Hub 端自动处理，无需 LLM 关心）：
    - Hub 端 `http_client.py` 已对 `/air/domestic/getPlaneSendpki` 响应做精简：
      - **删除**：`approveUserList` 全字段详情、`airlineList[].baggageList`、`nameList`、`orderPlaneTgqList[].issueRule` 等冗余字段
      - **保留**：`payType` / `violatePolicy` / `paymentKind` / `approverCount` + 前 5 个 approver `{id, name, depName}` / `orderList[].orderId`/`recPrice`/`payPrice`/`tgq[].airId`/`fromCity`/`toCity`/`flyDate` + 截断到 200 字符的 `refundRule` / `changeRule` + **完整** `orderBasicDataJson`（submitPlaneSendpki 必须）
    - 如果 LLM 觉得"我看的不全"想看 airlineList 详情等字段 → 响应里**没有**这些字段，已经被精简掉。**禁止**在响应里 grep / 找这些字段。**禁止**调第二次 getPlaneSendpki。
    - 想看完整响应审计（异常排查用）：响应在 `~/.opencode-tool-output/spill_*.json`（沙箱内）或 `work/tenant-A/project-1/.opencode-tool-output/spill_*.json`（host），但**日常流程不要 cat**。
21. **getPassengerAllAddress 响应已精简**：
    - Hub 端只保留 `current=true` 的地址，其他历史地址全部删除。
    - **禁止**调第二次。响应里没有的地址就是没有。

22. **乘机人信息补全自动用表单卡片，禁发消息**：
    - findPassenger 返回的乘机人信息**不完整**（缺 `birthDay` / `nationality` / `expiryDate` / `certNamePinyin` 等）时，Hub 会**自动发 `PASSENGER_FORM` 卡片**给用户。
    - **禁止**用 text 消息让用户"发消息补全"（如："请补充出生日期、护照有效期、拼音名"）。这种引导很慢且用户容易漏填。
    - **禁止**调 ask_user 发 `OD_INPUT` 卡片（那是问行程用，不是问乘机人）。
    - Hub 端会自动判断哪些字段缺失，缺失的字段才会出现在表单里；已有字段自动 pre-fill。
    - 卡片提交后，Hub 会自动接 `waitSave` 流程，你不需要再调 findPassenger。
    - 必填字段（Hub 端会按国际机票下单要求强制收集）：
      | 字段 | 类型 | 备注 |
      |---|---|---|
      | 姓名（中文） | text | 通常 pre-fill |
      | 护照拼音名 | text | **必须** `LIU/YUNZE` 格式 |
      | 证件类型 | select | 护照/港澳/台胞/回乡/台湾 |
      | 证件号码 | text | 护照号 |
      | 国籍 | select | 默认 CN |
      | 出生日期 | date | YYYY-MM-DD |
      | 证件有效期 | date | YYYY-MM-DD |
      | 联系电话 | text | 通常 pre-fill |
      | 邮箱（可选） | text | |
23. **getClientBasicData 必传 `productType=INTERNATIONAL`**：
    - Hub 端 `http_client.py` 已经**自动**在 body 为 `{}` 或缺 `productType` 时补 `productType=INTERNATIONAL`。
    - 即使如此，**主动传**这个字段更稳：
      ```bash
      python3 http_client.py /air/customer/getClientBasicData '{"productType":"INTERNATIONAL"}'
      ```
    - **不要**传 `{}` —— fh-travel BFF 会返回 `TMS_1002 / 网络异常`（不报错但实际是参数错）。

24. **对用户的回复只能用"用户能看懂"的话**（最高优先级规则）：
    - 你面对的是普通用户，他们不知道也不需要知道：API 路径（intShopping/intPricing/findPassenger/...）、卡片机制（ask_user/Hub auto-assembly）、内部 ID 字段（serialNumber/groupId/priceId/pricingId/userCode/depId/passengerId/certId）、脚本名（compact_intl_payload.py/render_intl_options.py）、技术细节。
    - **禁止**在用户可见的 text 事件中输出以下任一内容（这些是给开发者看的）：
      - API 名称或路径：intShopping / intPricing / intRule / intPolicy / waitSave / saveOrder / findPassenger / getMineBasicData / getClientBasicData / getPlaneSendpki / submitPlaneSendpki
      - 内部 ID：serialNumber / groupId / priceId / pricingId / cardId / userCode / depId / passengerId / certId / orderGroupId / subOrderId / pnr
      - 卡片机制名：ask_user / Hub / auto-assembly / FLIGHT_RESULT / PASSENGER_FORM / PLUGIN
      - 内部脚本：compact_intl_payload.py / render_intl_options.py / http_client.py / normalize_request.py
      - "通过 ask_user 发 X 卡片"、"Hub 端 auto-assembly 已完成"等元评论
    - **正确做法**：直接说结果。
      - ❌ "新查询的 serialNumber 已更新为 260623090714A0000001"
      - ✅ "已重新查询航班"
      - ❌ "通过 ask_user 发核价确认卡片"
      - ✅ "核价完成，KE864 经济舱 ¥1006（不可退/可改）"
      - ❌ "Hub 端 auto-assembly 已生成 FLIGHT_RESULT 卡片"
      - ✅ "已为您找到 5 个航班方案"
    - 内部 ID 仅在**调 API 时**作为参数使用，**不要**复读给用户。
    - **空 text 事件不要发**——如果你想"提示一下进度"，直接发空字符串会被过滤；想说什么就一句话说完整。
25. **你只调 `http_client.py`，**禁止**调其它渲染脚本**（历史经验教训，违反会让交互流程退化）：
    - **禁止**调 `compact_intl_payload.py` / `render_intl_options.py`。
    - Hub 端会在 `intShopping` tool_result 到达时**自动**拼好航班卡片并发送给用户，你不需要做任何额外渲染工作。
    - 即使你看到 spill 文件路径，**不要** `cat` 它、不要 `python3 compact_intl_payload.py`、不要 `python3 render_intl_options.py`。
    - **唯一允许**的额外脚本调用是 `http_client.py` 一个，所有 API 都通过它。
26. **省 token：避免空 text、避免重复描述、避免 cat workflow 文件超过 1 次**：
    - 每次发空 text（content=""）就是浪费用户带宽。
    - 同一个结果不要用 text 说一遍再发"好的"/"已收到"再说一遍。
    - 调 API 失败时**第一次**立即 `cat workflows/<相关>.md` 确认格式，**不要**反复重试浪费 token。
    - 同一 session 内已读过的 workflow 文件不要重读，除非参数有变化。

## AUIP Card ContractType**。
航班搜索结果使用 `AIR_DOMESTIC_FLIGHT_LIST` 展示富卡片（前端已支持国际航班数据）。
其他场景使用 `PLAIN_TEXT` 展示结构化文本。详细映射见 `references/agui-mapping.md`。

### Card Types

| 业务场景 | `card_type` | 触发标准 AGUI 组件 | `body.contentJson.dataList` 组成 |
|---|---|---|---|
| 缺少查询输入 | `OD_INPUT` | 顶层 `fields[]`（无 contentJson） | — |
| 航班搜索结果 | `FLIGHT_RESULT` | `AIR_DOMESTIC_FLIGHT_LIST` | `AIR_DOMESTIC_FLIGHT_LIST`（航班列表）→ 可选 `PLAIN_TEXT`（签证提醒） |
| 舱位/价格选择 | `PRICE_LIST` | `PLAIN_TEXT` | `PLAIN_TEXT`（价格列表） |
| 退改规则展示 | `RULE_DETAIL` | `PLAIN_TEXT` | `PLAIN_TEXT`（退改规则文本） |
| 核价确认 | `PRICING_VERIFY` | `PLAIN_TEXT` | `PLAIN_TEXT`（价格变动说明） |
| 差标违反 | `POLICY_DECISION` | `PLAIN_TEXT` + `BUTTON` | `PLAIN_TEXT`（违反项）→ `BUTTON`（继续/重选） |
| 乘机人表单 | `PASSENGER_FORM` | 顶层 `fields[]` | — |
| 出差单/成本中心 | `OAT_BINDING` | 顶层 `fields[]` 或 `options[]` | — |
| 订单确认 | `ORDER_CONFIRM` | `AIR_DOMESTIC_ORDER_SUMMARY` + `BUTTON` | `AIR_DOMESTIC_ORDER_SUMMARY` → `BUTTON` |
| 下单完成 | `ORDER_SUCCESS` | 顶层字段 | `order_no`, `pnr`, `order_summary` |
| 无法继续 | `CANNOT_ORDER` | 顶层字段 | `reason`, `fallback` |
| 自由文本 | `CHAT_FALLBACK` | `PLAIN_TEXT` | `PLAIN_TEXT` |

**ORDER_CONFIRM 场景复用 `AIR_DOMESTIC_ORDER_SUMMARY`**：国际机票订单摘要字段
（orderId/orderNo/totalPrice/passengerCount/flightSummary/passengerLines/tripTypeLabel）
与国内一致，可直接映射。`submitPayload` 按国际 saveOrder 格式组装。

### Minimum FLIGHT_RESULT Shape

**推荐方式**：调用 `render_intl_options.py` 生成 `contentJson`，直接作为卡片 body：

```bash
python3 /work/shared/skills/fh-international-flight-booking/scripts/compact_intl_payload.py result.json --limit 10 --output /tmp/compact.json
python3 /work/shared/skills/fh-international-flight-booking/scripts/render_intl_options.py /tmp/compact.json
```

将输出的 JSON 作为 `ask_user(card_type="FLIGHT_RESULT", body={"contentJson": <输出JSON>})` 的 body。

**手动构造**（仅在脚本不可用时）：

```json
{
  "card_type": "FLIGHT_RESULT",
  "title": "国际航班查询结果",
  "body": {
    "contentJson": {
      "schemaVersion": "2",
      "dataList": [
        {
          "basicType": "AIR_DOMESTIC_FLIGHT_LIST",
          "dataStr": "共查询到15个航班组合",
          "dataJson": {
            "serialNumber": "",
            "totalCount": 15,
            "filteredCount": 10,
            "flightList": [
              {
                "depCityName": "深圳",
                "arrCityName": "曼谷",
                "depDate": "2026-06-19",
                "depTime": "00:15",
                "arrDate": "2026-06-19",
                "arrTime": "02:15",
                "lowestPrice": 2338,
                "totalPrice": 2338,
                "totalDuration": 180,
                "durationMin": 180,
                "stopCount": 0,
                "transferCount": 0,
                "airlineName": "深圳航空",
                "flightNo": "ZH305",
                "airId": "ZH",
                "tripType": "OW",
                "serialNo": 1,
                "flightId": "ZH305",
                "legs": [{"direction": "OUTBOUND", "flightNo": "ZH305", "depTime": "00:15", "arrTime": "02:15", "duration": 180, "aircraftName": "A320neo", "meal": true}],
                "shareFlight": false,
                "arrDayOffset": 0
              }
            ]
          },
          "linkUrl": ""
        }
      ]
    }
  }
}
```

## Public Utility Layer

```bash
python3 /work/shared/skills/fh-international-flight-booking/scripts/normalize_request.py plan.json
python3 /work/shared/skills/fh-international-flight-booking/scripts/stage_guard.py --stage FLIGHT_LISTED --api intRule
python3 /work/shared/skills/fh-international-flight-booking/scripts/http_client.py /air/international/intShopping body.json
```

**注意**：`intShopping` 查询后的航班卡片由 Hub 自动生成并发送，不需要调用
`compact_intl_payload.py` 或 `render_intl_options.py`。直接等待用户选择航班即可。
