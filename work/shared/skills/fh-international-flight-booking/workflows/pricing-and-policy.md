# Workflow: Pricing & Policy (Step 4)

> 加载时机：进入 PRICE_SELECTED 阶段后加载本文件。
> 这是整个流程中最复杂的决策节点，包含核价、差标、出差单三重校验。

## 前置条件 (GATE)

| 参数 | 来源 | 校验 |
|---|---|---|
| `ctx.serialNumber` | Step 2 intShopping | 非空字符串 |
| `ctx.selectedPriceId` | Step 3 用户选择 | 非空字符串 |
| `ctx.clientId` | Step 1 getClientBasicData | 非空字符串 |
| `ctx.oaLogin` | Step 1 getClientBasicData | boolean |
| `ctx.applicationType` | Step 1 getClientBasicData | 非空 |
| `ctx.originalTotalPrice` | Step 3 选中价格的 totalPrice | 数值 |

**缺失处理**：
- `serialNumber` 或 `selectedPriceId` 缺失 → **禁止调用任何 API** → 回退 Step 2
- `clientId` 缺失 → 先调 `getClientBasicData`
- `applicationId` 缺失且 `applicationType != "NON_APPLICATION"` → 发 `OAT_BINDING` 卡片

## 4.1 核价 (intPricing)

**目的**：确认选中航班+舱位价格是否仍有效（防止缓存过期变价）。

**API**: `POST /air/international/intPricing`

**请求体组装**：

```json
{
  "language": "cn",
  "clientId": "<ctx.clientId>",
  "flightList": [
    {
      "serialNumber": "<ctx.serialNumber>",
      "priceId": "<ctx.selectedPriceId>"
    }
  ]
}
```

**参数溯源**：

| 请求字段 | 取值路径 | 禁止 |
|---|---|---|
| `flightList[0].serialNumber` | `intShopping` → `data.serialNumber` | 禁止编造 |
| `flightList[0].priceId` | `intShopping` → `groupList[].priceList[].priceId` | 禁止编造 |
| `clientId` | `getClientBasicData` → 用户指定 | 禁止猜测 |

**返回关键字段提取**：

| 返回字段 | 用途 | 存入上下文 |
|---|---|---|
| `data[0].serialKey` | 后续 waitSave 的缓存 key | `ctx.pricingSerialKey` |
| `data[0].priceId` | **此即 pricingId**，后续 waitSave/saveOrder 必用 | `ctx.pricingId` |
| `data[0].serialNumber` | 核价后序列号 | `ctx.pricingSerialNumber` |
| `data[0].priceList[0].totalPrice` | 核价后总价 | `ctx.verifiedTotalPrice` |
| `data[0].priceList[0].price` | 核价后票面价 | `ctx.verifiedPrice` |
| `data[0].priceList[0].tax` | 核价后税费 | `ctx.verifiedTax` |
| `data[0].priceList[0].flightList[0].ref2` | 退改签信息标识 | `ctx.ref2` |

**变价判断**：

```
originalTotalPrice = ctx.originalTotalPrice (intShopping 时的 totalPrice)
verifiedTotalPrice = ctx.verifiedTotalPrice (intPricing 返回)

if verifiedTotalPrice != originalTotalPrice:
    → 触发标准 AGUI：PLAIN_TEXT
    → 展示: "所选航班价格已变动：原价 ¥{originalTotalPrice} → 现价 ¥{verifiedTotalPrice}，差额 ¥{diff}"
    → 追加 BUTTON: "接受新价格继续" / "重新查询航班"
    → 用户接受 → 更新 ctx.originalTotalPrice = verifiedTotalPrice，继续
    → 用户拒绝 → 回退 Step 2 重新查询
```

**状态转换**: `PRICE_SELECTED → PRICING_VERIFIED`

## 4.2 差标校验 (intPolicy)

**目的**：检查选中航班是否违反企业差旅政策。

**API**: `POST /air/international/intPolicy`

**前置校验**：
- `oaLogin` 必须来自 `getClientBasicData`，不可假设

**请求体组装**：

```json
{
  "oaLogin": <ctx.oaLogin>,
  "flightList": [
    {
      "serialNumber": "<ctx.serialNumber>",
      "priceId": "<ctx.selectedPriceId>"
    }
  ]
}
```

**返回处理**：
- 返回空 `{}` 或 `errorCode == "0"` → 差标通过，进入 4.3
- 返回违反政策数据 → 构建差标违反卡片

**差标违反卡片**：

触发标准 AGUI：`PLAIN_TEXT` + `BUTTON`

```json
{
  "card_type": "POLICY_DECISION",
  "title": "差旅政策违反提醒",
  "body": {
    "contentJson": {
      "schemaVersion": "2",
      "dataList": [
        {
          "basicType": "PLAIN_TEXT",
          "dataStr": "您选用的航班违反以下差旅政策：\n1. {违反项1描述}\n2. {违反项2描述}\n\n请选择处理方式：",
          "dataJson": null,
          "linkUrl": ""
        },
        {
          "basicType": "BUTTON",
          "dataStr": "继续预订（需审批）",
          "dataJson": null,
          "linkUrl": "CONTINUE_WITH_APPROVAL"
        }
      ]
    }
  }
}
```

**policyPermit 决策矩阵**（取自 `waitSave` 返回的 `travelPolicyList[].policyPermit`）：

| policyPermit | 含义 | Agent 行为 |
|---|---|---|
| 1 | 免审批 | 直接继续 |
| 2 | 需审批 | 展示提醒，用户确认后继续 |
| 3 | 现付下单 | 告知用户需自费，确认后切换 payType=3 |
| 4 | 不能下单 | `CANNOT_ORDER`: "根据差旅政策，您无法预订此航班" |

**状态转换**: `PRICING_VERIFIED → POLICY_CHECKED`

## 4.3 出差单校验 (intCheckApplication) — 条件执行

**仅当** `ctx.applicationType != "NON_APPLICATION"` 且 `applicationId` 已知时执行。

**API**: `POST /air/international/intCheckApplication`

**请求体组装**：

```json
{
  "flag": 0,
  "applicationId": <ctx.applicationId>,
  "flightList": [
    {
      "serialNumber": "<ctx.serialNumber>",
      "priceId": "<ctx.selectedPriceId>"
    }
  ]
}
```

**flag 取值**：
- `0` = 管制（不匹配则阻断）
- `1` = 提醒（不匹配仅提示）
- 取值逻辑：若 `getClientBasicData.applicationNoMatchNoContinue == true` → flag=0；否则 → flag=1

**返回处理**：
- 匹配成功 → 进入 Step 5
- 匹配失败 + flag=0 → 发 `OAT_BINDING` 让用户重选出差单
- 匹配失败 + flag=1 → 提示不匹配但允许继续

## 完成后上下文状态

进入 Step 5 前，上下文必须包含：

| 上下文变量 | 来源 |
|---|---|
| `ctx.serialNumber` | intShopping |
| `ctx.selectedPriceId` | intShopping groupList priceList |
| `ctx.pricingId` | intPricing 返回的 data[].priceId |
| `ctx.pricingSerialKey` | intPricing 返回的 data[].serialKey |
| `ctx.pricingSerialNumber` | intPricing 返回的 data[].serialNumber |
| `ctx.verifiedTotalPrice` | intPricing |
| `ctx.policyPassed` | intPolicy |
| `ctx.applicationId` | 用户/OA（可选） |
| `ctx.applicationMatched` | intCheckApplication（可选） |
| `ctx.ref2` | intPricing priceList.flightList[0].ref2 |

**任一变量缺失 → 禁止进入 Step 5，回退到对应步骤补齐。**

## 错误处理

| 错误场景 | errorCode | Agent 行为 |
|---|---|---|
| Token 过期 | HTTP 401/403 | `CANNOT_ORDER`: "登录已过期，请重新登录" |
| 核价超时 | `FH_TIMEOUT` | `CANNOT_ORDER`: "核价服务超时，请稍后重试" |
| 价格已失效 | intPricing errorCode != "0" | 提示"所选舱位价格已变动" → 回退 Step 2 |
| 差标服务不可达 | `FH_UNREACHABLE` | `CANNOT_ORDER`: "差旅政策服务暂时不可用" |
| 出差单不匹配 | intCheckApplication flag=0 | `OAT_BINDING` 卡片让用户重选 |
