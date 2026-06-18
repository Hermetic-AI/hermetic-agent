# Workflow: Order Submit & Payment (Step 6)

> 加载时机：进入 PASSENGER_FILLED 阶段后加载本文件。

## 前置条件 (GATE)

| 参数 | 来源 | 校验 |
|---|---|---|
| `ctx.serialNumber` | Step 2 | 非空 |
| `ctx.selectedPriceId` | Step 3 | 非空 |
| `ctx.pricingId` | Step 4 | 非空 |
| `ctx.passengerList[]` | Step 5 | 至少 1 人 |
| `ctx.costCenterId` | Step 5 | 非空 |
| `ctx.verifiedTotalPrice` | Step 4 | 数值 |
| `ctx.travelPolicyList` | Step 5 | 数组（可为空） |

## 执行步骤

### 6.1 订单确认预览

在提交前展示订单摘要，触发标准 AGUI：`AIR_DOMESTIC_ORDER_SUMMARY` + `BUTTON`

**ORDER_CONFIRM 卡片组装**：

```json
{
  "card_type": "ORDER_CONFIRM",
  "title": "订单确认",
  "body": {
    "contentJson": {
      "schemaVersion": "2",
      "dataList": [
        {
          "basicType": "AIR_DOMESTIC_ORDER_SUMMARY",
          "dataStr": "订单确认",
          "dataJson": {
            "actionType": "SUBMIT_ORDER",
            "orderId": "",
            "orderNo": "",
            "orderStatus": "PENDING_SUBMIT",
            "totalPrice": <ctx.verifiedTotalPrice>,
            "passengerCount": <passengerList.length>,
            "createTime": "<ISO 8601 now>",
            "pnr": null,
            "idempotencyKey": "<UUID4>",
            "message": "请确认以下信息后提交订单",
            "payUrl": null,
            "payDeadline": null,
            "submitPayload": { ... },
            "flightSummary": { ... },
            "passengerLines": ["张三(护照:E12345678)"],
            "tripTypeLabel": "单程"
          },
          "linkUrl": ""
        },
        {
          "basicType": "BUTTON",
          "dataStr": "确认提交",
          "dataJson": null,
          "linkUrl": "CONFIRM_SUBMIT"
        }
      ]
    }
  }
}
```

**flightSummary 组装**（取首段去程）：

| 字段 | 映射 |
|---|---|
| `depDate` | intShopping tripList[io=0].flightList[0].flyDate 日期 |
| `depTime` | intShopping tripList[io=0].flightList[0].flyDate 时间 |
| `arrTime` | intShopping tripList[io=0].flightList[-1].arrDate 时间 |
| `depAirportName` | cityList 中 fromPort 的 airPortName |
| `arrAirportName` | cityList 中 toPort 的 airPortName |
| `airlineName` | airwayList 中 airId 的 companyName |
| `flightNo` | intShopping tripList[0].flightList[0].flightId |
| `depCityName` | cityList 中 fromPort 的 cityName |
| `arrCityName` | cityList 中 toPort 的 cityName |

**用户确认后 → 调用 saveOrder**

### 6.2 提交订单 (saveOrder)

**API**: `POST /air/international/saveOrder`

**请求体组装**：

```json
{
  "outlayType": "<ctx.outlayType 或 '1'(公费)>",
  "interfaceSupplier": "",
  "savePassenger": "true",
  "clientId": "<ctx.clientId>",
  "payType": "<ctx.payType 或 '0'(挂账)>",
  "orderer": "<ctx.userName>",
  "orderTel": "<ctx.contactPhone>",
  "userCode": "<ctx.userCode>",
  "orderMail": "",
  "noadvanceReason": "<ctx.travelReason 或 ''>",
  "applicationDh": "<ctx.applicationDh 或 ''>",
  "applicationId": "<ctx.applicationId 或 ''>",
  "depId": "<ctx.costCenterId>",
  "projectName": "<ctx.projectName 或 ''>",
  "belongProjectCode": "<ctx.belongProjectCode 或 ''>",
  "belongCompany": "<ctx.belongCompany 或 ''>",
  "belongCompanyCode": "<ctx.belongCompanyCode 或 ''>",
  "depName": "<ctx.costCenterName 或 ''>",
  "needAddress": "<需要纸质行程单则 '1' 否则 '0'>",
  "deliverType": "<needAddress=='1' 则 '2' 否则 '3'>",
  "receiver": {
    "contact": "<ctx.addressInfo.realName>",
    "clientTel": "<ctx.addressInfo.mobile>",
    "sendAddress": "<ctx.addressInfo.address>"
  },
  "budgetCode": "<ctx.budgetCode 或 ''>",
  "specificPolicy": <ctx.policyPassed>,
  "travelPolicyList": [
    {"id": "<policy.id>", "reason": "<用户填写的差标原因>"}
  ],
  "passengerList": [
    {
      "cardId": <certId>,
      "name": "<LastName/FirstName>",
      "passengerName": "<中文姓名>",
      "passengerType": "<0成人/1儿童/2婴儿>",
      "issueCountry": "CN",
      "nationality": "<nationality code>",
      "idType": "<0护照/1港澳/2台胞/3回乡/4台湾>",
      "userCode": "<userCode>",
      "depId": <depId>,
      "idNumber": "<certNo>",
      "idExpiration": "<expiryDate>",
      "gender": "<1男/0女>",
      "birthday": "<birthDay>",
      "phoneNumber": "<mobile>",
      "bx1": 0,
      "bx2": 0,
      "mileageList": []
    }
  ],
  "flightList": [
    {
      "serialNumber": "<ctx.serialNumber>",
      "priceId": "<ctx.selectedPriceId>",
      "pricingId": "<ctx.pricingId>"
    }
  ],
  "additionalList": []
}
```

**参数溯源（关键字段）**：

| saveOrder 字段 | 取值路径 |
|---|---|
| `flightList[0].serialNumber` | intShopping → `data.serialNumber` |
| `flightList[0].priceId` | intShopping → `groupList[].priceList[].priceId` |
| `flightList[0].pricingId` | **intPricing** → `data[].priceId`（**不是** intShopping 的 priceId） |
| `passengerList[].cardId` | findPassenger → `data.dataList[].id`（证件表 ID） |
| `passengerList[].depId` | findPassenger → `data.dataList[].depId` |
| `depId` | getMineBasicData → `data.depId` 或用户选择成本中心 |
| `userCode` | getMineBasicData → `data.userCode` |

**返回关键字段**：

| 返回字段 | 用途 |
|---|---|
| `data.orderGroupId` | 订单组号，后续支付用 |
| `data.pnr` | PNR 号 |
| `data.orderList[].orderId` | 订单号 |
| `data.orderList[].subOrderId` | 副订单号 |
| `data.orderList[].recPrice` | 应付款 |

**状态转换**: `PASSENGER_FILLED → ORDER_SUBMITTED`

### 6.3 支付验证 (getPlaneSendpki)

**API**: `POST /air/domestic/getPlaneSendpki`

```json
{
  "datatype": 0,
  "orderGroup": "<saveOrder 返回的 data.orderGroupId>"
}
```

**返回处理**：
- `data.payType` 确定支付方式
- `data.violatePolicy == true` → 需差标审批
- `data.approveUserList[]` → 审批人列表
- `data.diffcashData` → 差额支付数据

### 6.4 提交支付 (submitPlaneSendpki)

**API**: `POST /air/domestic/submitPlaneSendpki`

```json
{
  "orderBasicDataJson": "<getPlaneSendpki 返回的 data.orderBasicDataJson>",
  "payType": <支付类型>,
  "orderPriceList": [
    {"order_id": "<orderId>", "recPrice": <recPrice>, "payPrice": 0}
  ]
}
```

**返回处理**：
- `data.wxpayRequestData` → 微信支付信息
- `data.alipayRequestData` → 支付宝信息
- `data.sendSucc == true` → 支付发起成功

**状态转换**: `ORDER_SUBMITTED → PAYMENT_VERIFIED → FINISHED`

### 6.5 订单完成

触发标准 AGUI：`ORDER_SUCCESS`

```json
{
  "card_type": "ORDER_SUCCESS",
  "title": "下单成功",
  "body": {
    "order_no": "<data.orderList[0].orderId>",
    "pnr": "<data.pnr>",
    "order_summary": "国际机票订单已创建，PNR: {pnr}，订单号: {orderId}，应付金额: ¥{recPrice}"
  }
}
```

## 错误处理

| 场景 | 行为 |
|---|---|
| saveOrder errorCode != "0" | 显示 errorMsg，不重试 |
| saveOrder 返回 pnr 为空 | 提示"订单已创建，正在占座中" |
| 支付验证失败 | 提示"订单已创建但支付验证失败，请联系客服" |
| 需审批 | 展示审批人列表，提示"已提交审批，审批通过后将自动出票" |
