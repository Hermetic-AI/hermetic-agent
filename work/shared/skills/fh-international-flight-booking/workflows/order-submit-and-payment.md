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

**完整请求体模板**（已验证可成功下单，2026-06-22 真实下单 ZH305/SZX→BKK）：

```json
{
  "outlayType": "1",
  "interfaceSupplier": "",
  "savePassenger": "true",
  "clientId": "",
  "payType": "0",
  "orderer": "刘酝泽",
  "orderTel": "13384459987",
  "userCode": "013",
  "orderMail": "",
  "noadvanceReason": "",
  "applicationDh": "",
  "applicationId": "",
  "depId": 115275,
  "projectName": "",
  "belongProjectCode": "",
  "belongCompany": "月亮岛开发公司",
  "belongCompanyCode": "",
  "depName": "月亮岛开发公司",
  "needAddress": "0",
  "deliverType": "3",
  "budgetCode": "",
  "specificPolicy": true,
  "travelPolicyList": [],
  "passengerList": [
    {
      "cardId": 0,
      "name": "LIU/YUNZE",
      "passengerName": "刘酝泽",
      "passengerType": "0",
      "issueCountry": "CN",
      "nationality": "CN",
      "idType": "0",
      "userCode": "013",
      "depId": 115275,
      "idNumber": "EK3971795",
      "idExpiration": "2033-05-15",
      "gender": "",
      "birthday": "2000-08-12",
      "phoneNumber": "13384459987",
      "bx1": 0,
      "bx2": 0,
      "mileageList": []
    }
  ],
  "flightList": [
    {
      "serialNumber": "260622144826A0000001",
      "priceId": "260622144820100004/100000/4",
      "pricingId": "2"
    }
  ],
  "additionalList": []
}
```

**关键字段格式（踩坑要点，违反就报 TMS_1002 / TRAVELAIR_1002）**：

| 字段 | 字面量 | 说明 |
|---|---|---|
| `outlayType` | `"1"` 字符串 | 1=公费 / 2=自费 |
| `payType` | `"0"` 字符串 | 0=挂账 / 1=现付（**不是**数字） |
| `passengerType` | `"0"` 字符串 | 0=成人 / 1=儿童 / 2=婴儿（**字符串**！） |
| `idType` | `"0"` 字符串 | 0=护照 / 1=港澳 / 2=台胞 / 3=回乡 / 4=台湾（**字符串**！） |
| `passengerList[].gender` | `""` 或 `"1"` | 空字符串合法（**不传**会被拒） |
| `passengerList[].cardId` | `0`（找不到就 0） | 数字；findPassenger 没匹配到时用 0 |
| `passengerList[].name` | **拼音** `"LIU/YUNZE"` | **不是**中文 |
| `passengerList[].passengerName` | 中文 | 必填 |
| `passengerList[].issueCountry` | `"CN"` | **发证国家**，**不是** `certIssuePlace` |
| `passengerList[].nationality` | `"CN"` | 国籍 |
| `passengerList[].idExpiration` | `"2033-05-15"` | **必填**，护照有效期 |
| `passengerList[].birthday` | `"2000-08-12"` | **必填** |
| `clientId` | `""` 空字符串 | **不要**填 `SZ001IVA`（那是查询客户） |
| 顶层 `depId` | `115275` 数字 | 用户选的成本中心 ID |
| 顶层 `belongCompany` / `depName` | `"月亮岛开发公司"` | 跟 `depId` 对应的公司/部门名 |
| `specificPolicy` | `true` | intPolicy 通过时填 true |
| `flightList[0].pricingId` | `"2"` 或长串 | **intPricing 返回的 `data[0].priceId`**（长串如 `"1,abc...,10,1E,TCPL,1"`） |
| `needAddress` | `"0"` | 不需要纸质行程单 |
| `deliverType` | `"3"` | 行程单寄送方式（无需纸质时用 3） |
| `receiver` 块 | **不需要** | 公费挂账无需寄送地址，**不要**加 |
| `orderMail` | `""` 空字符串 | 可选 |

**参数溯源（关键字段）**：

| saveOrder 字段 | 取值路径 |
|---|---|
| `flightList[0].serialNumber` | intShopping → `data.serialNumber` |
| `flightList[0].priceId` | intShopping → `groupList[].priceList[].priceId` |
| `flightList[0].pricingId` | **intPricing** → `data[].priceId`（**不是** intShopping 的 priceId） |
| `passengerList[].cardId` | findPassenger → `data.dataList[].id`（证件表 ID，没匹配就 0） |
| `passengerList[].depId` | findPassenger → `data.dataList[].depId` |
| `depId` | getMineBasicData → `data.depId` 或用户选择成本中心 |
| `userCode` | getMineBasicData → `data.userCode` |
| `belongCompany` / `depName` | 跟 `depId` 对应（用户选择成本中心时获得） |
| `passengerList[].name` | 用户提供的护照拼音（或中文转拼音） |
| `passengerList[].passengerName` | 用户提供的中文姓名 |
| `passengerList[].idNumber` | 用户提供的护照号 |
| `passengerList[].idExpiration` | 护照有效期（用户输入） |
| `passengerList[].birthday` | 出生日期（用户输入） |

**返回关键字段**：

| 返回字段 | 用途 |
|---|---|
| `data.orderGroupId` | 订单组号，后续支付用 |
| `data.pnr` | PNR 号 |
| `data.orderList[].orderId` | 订单号 |
| `data.orderList[].subOrderId` | 副订单号 |
| `data.orderList[].recPrice` | 应付款 |

**状态转换**: `PASSENGER_FILLED → ORDER_SUBMITTED`

### 6.3 支付验证 (getPlaneSendpki) — **公费挂账跳过本节**

**API**: `POST /air/domestic/getPlaneSendpki`

```json
{
  "datatype": 0,
  "orderGroup": "<saveOrder 返回的 data.orderGroupId>"
}
```

**返回处理**：
- `data.payType` 确定支付方式（**1-5=需在线支付，0 或 3=公费挂账不需支付**）
- `data.violatePolicy == true` → 需差标审批
- `data.approveUserList[]` → 审批人列表（公费挂账场景展示给用户）
- `data.diffcashData` → 差额支付数据

**⚠️ 重要：公费挂账（`payType == 0`）场景**：
- saveOrder 成功后**不要**调 getPlaneSendpki 和 submitPlaneSendpki
- 直接告诉用户"订单已创建，订单号 XXX，请登录企业后台完成支付或联系审批人"
- 原因：公费挂账后端不需要发起在线支付，调 submitPlaneSendpki 会因 `payType` 缺失/超范围（`[1-5]`）报错 `TRAVELAIR_1006`，浪费 5-10 秒

### 6.4 提交支付 (submitPlaneSendpki) — **公费挂账跳过本节**

**API**: `POST /air/domestic/submitPlaneSendpki`

```json
{
  "orderBasicDataJson": "<getPlaneSendpki 返回的 data.orderBasicDataJson>",
  "payType": <支付类型 1-5>,
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

## 失败恢复

### saveOrder 第一次失败立即读 workflow

saveOrder 返回 `errorCode != "0"` → **立即重新读本文件 §6.2 字段表**，不要猜字段、不要直接重试。

**常见报错 → 缺/错字段速查**：

| 错误码/消息 | 真正缺/错的字段 | 修正 |
|---|---|---|
| `乘客类型不能为空` | `passengerList[0].passengerType` 缺失 | 填 `"0"` |
| `国籍代码不能为空` | `passengerList[0].nationality` 缺失 | 填 `"CN"` |
| `发证国家不能为空` | `passengerList[0].issueCountry` 缺失 | 填 `"CN"`（**不是** `certIssuePlace`） |
| `没有指定客户下单权限` | `clientId`/`depId`/`pricingId` 组合错 | `clientId=""`, `depId` 数字 |
| `乘客证件号不能为空` | certNo 用了脱敏值 | 从 PASSENGER_FORM 提交取完整号 |

**禁止**在读 workflow 前改字段乱试。**禁止**重复试错 ≥2 次。

### 公费挂账跳过 getPlaneSendpki / submitPlaneSendpki

saveOrder 成功后，如果公费挂账（用户选非个人现付），**不要**调 getPlaneSendpki 和 submitPlaneSendpki。
直接告诉用户"订单已创建，订单号 XXX，PNR XXX，请登录企业后台完成支付或联系审批人"。

### Hub 响应精简说明

- **getPlaneSendpki** 响应已被 Hub 精简：删除了 `approveUserList` 详情、`airlineList[].baggageList`、`nameList` 等冗余字段。保留 `payType` / `violatePolicy` / `paymentKind` / `approverCount` + 前 5 个 approver + **完整** `orderBasicDataJson`。
- 如果你觉得"看的不全"想找 airlineList 详情 → 响应里**没有**这些字段。**禁止**调第二次。
- **getPassengerAllAddress** 响应只保留 `current=true` 的地址，**禁止**调第二次。

### certNo 必须完整

findPassenger 返回的 `certNo` 经常脱敏（如 `220502********0216`），**不能**直接用于 saveOrder。
必须等用户通过 PASSENGER_FORM 提交完整证件号，否则 saveOrder 报"乘客证件号不能为空"。

## 错误处理

| 场景 | 行为 |
|---|---|
| saveOrder errorCode != "0" | 显示 errorMsg，不重试 |
| saveOrder 返回 pnr 为空 | 提示"订单已创建，正在占座中" |
| 支付验证失败 | 提示"订单已创建但支付验证失败，请联系客服" |
| 需审批 | 展示审批人列表，提示"已提交审批，审批通过后将自动出票" |
