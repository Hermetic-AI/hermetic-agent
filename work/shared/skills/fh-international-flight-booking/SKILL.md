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
version: "1.1.0"
---

# FH International Flight Booking

## Purpose

通过原生 HTTP 直连 fh-travel 后端完成国际机票查询与订购全流程。
所有 API 通过 `scripts/http_client.py` 调用，Token 从 `FLIGHT_API_KEY` 环境变量注入。

本 Skill 只做：意图识别 → 参数组装 → API 调用 → 等待 Hub 自动生成卡片。
**不**实现后端业务逻辑、差旅政策引擎或订单状态机。

## Load Strategy (渐进式披露)

只加载本文件。按需加载：

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

## Hard Fast Path (自包含快速路径)

用户原话中已有 **出发城市 + 到达城市 + 出发日期** → **直接查询，不追问**。

| 用户原话 | 行动 |
|---|---|
| `查深圳到曼谷明天单程` | 直接 `intShopping` |
| `查北京到东京7月1日国际机票` | 直接 `intShopping` |

默认值（不追问）：`passengerType=ADT`，`language=cn`，`stopQuantity=0`，单程 `tripList` 1段。

常用三字码（内置，不需要读文件）：深圳=SZX，北京=PEK，上海=PVG，广州=CAN，香港=HKG，东京=NRT，大阪=KIX，首尔=ICN，曼谷=BKK，新加坡=SIN，吉隆坡=KUL。

示例：
```bash
python3 /work/shared/skills/fh-international-flight-booking/scripts/http_client.py /air/international/intShopping '{"stopQuantity":0,"language":"cn","passengerType":"ADT","tripList":[{"fromCity":"SZX","toCity":"BKK","flyDate":"<yyyy-MM-dd>","isCity":true}]}'
```

航班卡片由 Hub 自动生成。拿到 API 返回后，用简短中文概述结果，等待用户选择。

## Token & Auth

- Token 由 Hub 注入 `FLIGHT_API_KEY`，`http_client.py` 自动注入 header
- 不要索要、回显 token
- Token 缺失 → 发 `CANNOT_ORDER` 卡片
- 沙箱内用 `python3`，不用 `python`

## Core State Machine (14 阶段)

```
INIT → PERMISSION_CHECKED → SEARCH_PARAMS_READY → FLIGHT_LISTED
→ GROUP_SELECTED → PRICE_SELECTED → RULE_CHECKED
→ PRICING_VERIFIED → POLICY_CHECKED → WAIT_SAVE_LOADED
→ PASSENGER_FILLED → ORDER_SUBMITTED → PAYMENT_VERIFIED → FINISHED
```

权限/风控拦截 → `CANNOT_ORDER`（终态）。详细分支见 `schemas/state-machine.json`。

## Universal Rules (通则)

### API & 工具
1. **只用 `http_client.py`** 调 API，不要 curl/wget/webfetch/requests。**禁止**调 `compact_intl_payload.py` / `render_intl_options.py`。
2. **intShopping 后禁止读取/解析 spill 文件**（`tool_result` 中 `_hub_marker: full_output_spilled` 指向的文件）。Hub 已自动生成 FLIGHT_RESULT 卡片，你不需要解析原始航班数据。禁止 `python3 -c "... open(spill_file) ..."` 读 spill 文件、禁止手动构造 FLIGHT_RESULT 卡片。
3. **调业务 API 前必须先读对应 workflow 文件**，确认参数格式和约束。参数错第一次就立即读 workflow，不要反复重试。

### 数据
3. **一切数据来自 API 返回**，禁止编造航班号/价格/税费/舱位/退改规则/订单号。
4. **`serialNumber` 必须从 `intShopping.data.serialNumber` 精确复制**（20位 `YYYYMMDDHHMMA+7位`），不要用 `serialKey`、`requestSeqNo` 或其它字段替代。

### 用户界面
5. **中文优先，不泄露内部信息**。用户可见 text 中禁止出现：API 名（intShopping/intPricing/...）、内部 ID（serialNumber/priceId/groupId/...）、脚本名、卡片机制名。
6. **禁止过程叙述**。不说"正在查询"/"现在渲染卡片"/"let me query"。直接输出结果概要。
7. **先提取再追问，合并提问**。从用户消息提取行程/日期/偏好，只问真正缺失的字段，合到一个卡片。
8. **绝不代选舱位**。Hub 发舱位卡片后 → 停止，等用户点击。`[选择参数: priceId=...]` 只是前端 hint，不是用户已选。
9. Hub 发卡片后**立即停下等交互**（舱位/PASSENGER_FORM/ORDER_CONFIRM），不要自行继续。

### 流程
10. **完整流程顺序（不可颠倒）**：
    ```
    intShopping → 等用户选航班
      → getMineBasicData (/customer/mine/getMineBasicData {}) + findPassenger (/air/customer/findPassenger {"productType":"INTERNATIONAL"})
      → 检查信息完整 → 缺则等 PASSENGER_FORM
      → 完整则 intRule+intPricing+intPolicy → ORDER_CONFIRM
      → 等用户确认 → waitSave+saveOrder
    ```
    **绝对不要**在拉用户信息前发 ORDER_CONFIRM。
11. **严格查询范围**。用户说"深圳到曼谷"就只查深圳→曼谷，不加返程/中转/其他航线。
12. **"航班数据已过期"(TMS_1002)** → 立即重新 `intShopping` 拿新 `serialNumber`，重新核价。**不要**重试同参数。

### 错误处理
13. API `errorCode != "0"` → 中文翻译 errorMsg → 发 `CANNOT_ORDER` 或提示。
14. HTTP 超时/不可达 → `CANNOT_ORDER`（中文原因，建议稍后重试）。**不要**换工具重试。
15. Token 缺失 → `CANNOT_ORDER`，不要向用户索要。

## Quick Reference

```bash
# 权限 & 用户信息 (Step 1)
python3 http_client.py /air/customer/getClientBasicData '{"productType":"INTERNATIONAL"}'
python3 http_client.py /customer/mine/getMineBasicData '{}'

# 航班查询 (Step 2)
python3 http_client.py /air/international/intShopping '{"stopQuantity":0,"language":"cn","passengerType":"ADT","tripList":[...]}'

# 核价 (Step 4, 参数格式见 workflows/pricing-and-policy.md)
python3 http_client.py /air/international/intPricing '{"language":"cn","flightList":[{"serialNumber":"...","priceId":"..."}]}'

# 差标 (Step 4)
python3 http_client.py /air/international/intPolicy '{"flightList":[{"serialNumber":"...","priceId":"..."}]}'

# 退改 (Step 3)
python3 http_client.py /air/international/intRule '{"serialNumber":"...","priceId":"..."}'

# 乘机人查询 (Step 5)
python3 http_client.py /air/customer/findPassenger '{"productType":"INTERNATIONAL","pageIndex":1,"pageSize":20}'

# 备单 (Step 5)
python3 http_client.py /air/international/waitSave '{"language":"cn","flightList":[{"serialNumber":"...","priceId":"...","pricingId":"..."}]}'

# 下单 (Step 6, 完整参数见 workflows/order-submit-and-payment.md)
python3 http_client.py /air/international/saveOrder body.json
```

所有脚本路径：`/work/shared/skills/fh-international-flight-booking/scripts/`

**关键 API 路径对照**（禁止猜路径）：
- `getClientBasicData` = `/air/customer/getClientBasicData`（不是 `/air/international/...`）
- `getMineBasicData` = `/customer/mine/getMineBasicData`（不是 `/air/passenger/...` 或 `/air/international/...`）
- `findPassenger` = `/air/customer/findPassenger`（不是 `/air/passenger/...` 或 `/air/international/...`）
