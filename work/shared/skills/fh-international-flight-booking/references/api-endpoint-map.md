# API Endpoint Map

> 加载时机：首次调用任何 API 前加载本文件。

## 端点索引

| # | 端点 | 方法 | 超时(s) | 必需 header | 必需 body 字段 | 返回关键字段 |
|---|---|---|---|---|---|---|
| 1 | `/air/customer/getClientBasicData` | POST | 30 | token | `productType=INTERNATIONAL` | `data.showInternational`, `data.oaLogin`, `data.applicationType`, `data.costCenter`, `data.depId` |
| 2 | `/customer/mine/getMineBasicData` | POST | 30 | token | (空 body) | `data.userCode`, `data.depId`, `data.depName`, `data.userName`, `data.certList[]` |
| 3 | `/air/international/intShopping` | POST | 60 | token | `stopQuantity`, `onlyBigCustomerPrice`, `language`, `passengerType`, `tripList[]` | `data.serialNumber`, `data.groupList[]`, `data.baggageList[]`, `data.cityList[]`, `data.airwayList[]` |
| 4 | `/air/international/intRule` | POST | 30 | token | `serialNumber`, `priceId`, `pricingId` | `data[].refund`, `data[].change`, `data[].refundRule`, `data[].changeRule`, `data[].cabList[]` |
| 5 | `/air/international/intPricing` | POST | 45 | token | `language`, `clientId`, `flightList[].serialNumber`, `flightList[].priceId` | `data[].serialKey`, `data[].priceId`(=pricingId), `data[].priceList[].totalPrice` |
| 6 | `/air/international/intPolicy` | POST | 30 | token | `oaLogin`, `flightList[].serialNumber`, `flightList[].priceId` | (违反政策数据或空) |
| 7 | `/air/international/intCheckApplication` | POST | 30 | token | `flag`, `applicationId`, `flightList[].serialNumber`, `flightList[].priceId` | (匹配结果) |
| 8 | `/air/international/waitSave` | POST | 45 | token | `applicationId`, `clientId`, `language`, `flightList[].serialNumber/priceId/pricingId` | `data.travelPolicyList[]`, `data.applicationList[]`, `data.mileageCardList[]`, `data.insuranceList[]`, `data.airLineList[]` |
| 9 | `/air/customer/findPassenger` | POST | 30 | token | `productType=INTERNATIONAL` | `data.dataList[].id`, `.passengerName`, `.certNo`, `.certType`, `.depId`, `.nationality` |
| 10 | `/air/customer/listClientBelongCompany` | POST | 30 | token | `clientIdSpecify` | `data.dataList[].id`, `.name`, `.bm` |
| 11 | `/air/customer/getClientProject` | POST | 30 | token | `clientIdSpecify`, `showAll` | `data.dataList[].id`, `.name`, `.bm` |
| 12 | `/application/listOneUserApplicationsByUserCodeCertNoDateRange` | POST | 30 | token | `productType=INTERNATIONAL`, `applicationSearchType`, `startDate`, `endDate`, `internationalAirLineNew[]` | `data.application.clientID`, `.dh`, `.match` |
| 13 | `/params/system/nationality` | POST | 30 | token | (空 body) | `data[].names`, `.nameCode`, `.enames` |
| 14 | `/air/customer/getPassengerAllAddress` | POST | 30 | token | (空 body) | `data.dataList[].id`, `.address`, `.realName`, `.mobile`, `.current` |
| 15 | `/air/international/visa` | POST | 30 | token | `fromCity`, `stopCity`(可选), `toCity` | `data.visaDetails` |
| 16 | `/air/international/saveOrder` | POST | 45 | token | `flightList[].serialNumber/priceId/pricingId`, `passengerList[]`, `outlayType`, `payType`, ... | `data.orderGroupId`, `data.pnr`, `data.orderList[].orderId` |
| 17 | `/air/domestic/getPlaneSendpki` | POST | 30 | token | `datatype=0`, `orderGroup` | `data.payType`, `data.violatePolicy`, `data.orderList[]`, `data.approveUserList[]` |
| 18 | `/air/domestic/submitPlaneSendpki` | POST | 30 | token | `orderBasicDataJson`, `payType`, `orderPriceList[]` | `data.payType`, `data.alipayRequestData`, `data.wxpayRequestData` |

## 枚举值速查

### passengerType (intShopping)

| 值 | 含义 |
|---|---|
| ADT | 成人 |
| CHD | 儿童 |
| INF | 婴儿 |

### cabClass (intShopping)

| 值 | 含义 |
|---|---|
| FIRST | 头等舱 |
| PREMIUM_FIRST | 超级头等舱 |
| BUSINESS | 商务舱 |
| PREMIUM_BUSINESS | 超级商务舱 |
| ECONOMY | 经济舱 |
| PREMIUM_ECONOMY | 高级经济舱 |

### language

| 值 | 含义 |
|---|---|
| cn | 中文 |
| en | 英文 |

### productType

| 值 | 含义 |
|---|---|
| DOMESTIC | 国内机票 |
| INTERNATIONAL | 国际机票 |
| DOMESTIC_HOTEL | 国内酒店 |
| INTERNATIONAL_HOTEL | 国际酒店 |
| TRAIN | 火车 |
| CAR | 用车 |
| VISA | 签证 |

### idType (saveOrder passenger)

| 值 | 含义 |
|---|---|
| 0 | 护照 |
| 1 | 港澳通行证 |
| 2 | 台胞证 |
| 3 | 回乡证 |
| 4 | 台湾通行证 |

### passengerType (saveOrder passenger)

| 值 | 含义 |
|---|---|
| 0 | 成人 |
| 1 | 儿童 |
| 2 | 婴儿 |
| 3 | 老人 |
| 4 | 学生 |
| 5 | 劳务 |
| 6 | 移民 |
| 7 | 海员 |
| 8 | 青年 |

### outlayType (saveOrder)

| 值 | 含义 |
|---|---|
| 0 | 自费 |
| 1 | 公费 |

### payType (saveOrder)

| 值 | 含义 |
|---|---|
| 0 | 挂账 |
| 3 | 在线支付 |
| 4 | 银行转账 |

### costCenter (getClientBasicData)

| 值 | 含义 |
|---|---|
| HIDE | 隐藏 |
| DISPLAY | 显示 |
| DISPLAY_INPUT | 显示且输入/必填 |

### applicationType (getClientBasicData)

| 值 | 含义 |
|---|---|
| NON_APPLICATION | 无申请单 |
| MANUAL_INPUT | 人工输入 |
| OA_IMPORT | OA导入 |

### policyPermit (waitSave travelPolicyList)

| 值 | 含义 |
|---|---|
| 1 | 免审批 |
| 2 | 需审批 |
| 3 | 现付下单 |
| 4 | 不能下单 |

## 关键参数溯源（禁止编造）

| 参数 | 唯一来源 | 禁止 |
|---|---|---|
| `serialNumber` | `intShopping` → `data.serialNumber`（20位 `YYYYMMDDHHMMA+7位`） | 禁止编造，禁止用 `serialKey`/`requestSeqNo` |
| `priceId` | `intShopping` → `groupList[].priceList[].priceId` | 禁止编造 |
| `pricingId` | `intPricing` → `data[].priceId`（**不是** intShopping 的 priceId） | 禁止编造，禁止用字面量 `"2"` |
| `applicationId` | 用户提供 或 OA 跳转 或 `listOneUserApplications` | 禁止编造 |
| `clientId` | `getClientBasicData` 返回 或用户指定 | 禁止编造 |
| `depId` | `getMineBasicData` → `data.depId` 或用户选择成本中心 | 禁止编造 |
| `userCode` | `getMineBasicData` → `data.userCode` | 禁止编造 |

### 前置参数强校验规则

调用任何 API 前，确认所有前置参数已存在。缺失 → 回退补齐，禁止调用 API：

1. 可从上游获取但未获取 → 先调上游 API
2. 需用户提供 → 发 `ask_user` 卡片一次性收集
3. 不可获取（如 Token 缺失）→ 发 `CANNOT_ORDER`
