# Workflow: Order Preparation (Step 5)

> 加载时机：进入 POLICY_CHECKED 阶段后加载本文件。

## 前置条件 (GATE)

| 参数 | 来源 | 校验 |
|---|---|---|
| `ctx.serialNumber` | Step 2 | 非空 |
| `ctx.selectedPriceId` | Step 3 | 非空 |
| `ctx.pricingId` | Step 4 intPricing | 非空 |
| `ctx.clientId` | Step 1 | 非空 |
| `ctx.userCode` | Step 1 getMineBasicData | 非空 |
| `ctx.depId` | Step 1 getMineBasicData | 非空 |
| `ctx.policyPassed` | Step 4 | true |

## 执行步骤

### 5.1 获取待下单数据 (waitSave)

**API**: `POST /air/international/waitSave`

```json
{
  "applicationId": "<ctx.applicationId 或 ''>",
  "clientId": "<ctx.clientId>",
  "language": "cn",
  "flightList": [
    {
      "serialNumber": "<ctx.serialNumber>",
      "priceId": "<ctx.selectedPriceId>",
      "pricingId": "<ctx.pricingId>"
    }
  ]
}
```

**参数溯源**：

| 字段 | 取值路径 |
|---|---|
| `flightList[0].serialNumber` | `intShopping` → `data.serialNumber` |
| `flightList[0].priceId` | `intShopping` → `groupList[].priceList[].priceId` |
| `flightList[0].pricingId` | `intPricing` → `data[].priceId`（**不是** intShopping 的 priceId） |
| `clientId` | `getClientBasicData` |
| `applicationId` | 用户选择 或 OA 跳转 或 空 |

**返回关键字段提取**：

| 返回字段 | 用途 | 存入上下文 |
|---|---|---|
| `data.travelPolicyList[]` | 差旅政策列表 | `ctx.travelPolicyList` |
| `data.applicationList[].id` | 出差单 ID | `ctx.availableApplications` |
| `data.applicationList[].costCenterList[]` | 成本中心 | `ctx.availableCostCenters` |
| `data.applicationList[].passengerList[]` | 出差单乘机人 | `ctx.appPassengers` |
| `data.mileageCardList[]` | 里程卡 | `ctx.mileageCardList` |
| `data.insuranceList[]` | 保险 | `ctx.insuranceList` |
| `data.airLineList[]` | 航段数据 | `ctx.airLineList` |
| `data.applicationIdOa` | OA 跳转申请单 | `ctx.applicationIdOa` |

**状态转换**: `POLICY_CHECKED → WAIT_SAVE_LOADED`

### 5.2 乘机人选择

**API**: `POST /air/customer/findPassenger`

```json
{
  "productType": "INTERNATIONAL",
  "pageIndex": 1,
  "pageSize": 20
}
```

若用户指定姓名/工号搜索：
```json
{
  "data": "<搜索关键字>",
  "type": 0,
  "productType": "INTERNATIONAL",
  "pageIndex": 1,
  "pageSize": 20
}
```

**国际机票乘机人必填字段**（相比国内多出）：

| 字段 | 说明 | 来源 |
|---|---|---|
| `nationality` | 国籍代码 | findPassenger → `nationality`，若空需补充 |
| `idType` | 证件类型（0护照/1港澳通行证/2台胞证/3回乡证/4台湾通行证） | findPassenger → `certType` 映射 |
| `idNumber` | 证件号码 | findPassenger → `certNo` |
| `idExpiration` | 证件有效期 | findPassenger → `expiryDate`，若空需补充 |
| `gender` | 性别(1男/0女) | findPassenger → `sex` 映射 |
| `birthday` | 生日 | findPassenger → `birthDay` |
| `issueCountry` | 发证国家 | 通常 "CN" |

**证件类型映射**：

| findPassenger certType | saveOrder idType |
|---|---|
| 护照 | 0 |
| 港澳通行证 | 1 |
| 台胞证 | 2 |
| 回乡证 | 3 |
| 台湾通行证 | 4 |

**缺失证件信息处理**：
- 国籍为空 → 调用 `POST /params/system/nationality` 获取列表，让用户选择
- 证件过期 → 提醒用户"证件有效期不足6个月，部分航司可能拒绝登机"
- 性别为空 → 发 `PASSENGER_FORM` 补充

**状态转换**: `WAIT_SAVE_LOADED → PASSENGER_FILLED`

### 5.3 出差单绑定（条件执行）

**仅当** `ctx.applicationType != "NON_APPLICATION"` 时执行。

**API**: `POST /application/listOneUserApplicationsByUserCodeCertNoDateRange`

```json
{
  "productType": "INTERNATIONAL",
  "applicationSearchType": "APPLICANT",
  "startDate": "<出发日期前30天>",
  "endDate": "<出发日期后7天>",
  "internationalAirLineNew": [
    {
      "serialNumber": "<ctx.serialNumber>",
      "priceId": "<ctx.selectedPriceId>"
    }
  ],
  "returnMatchState": true
}
```

用户选择出差单后，获取对应 `costCenterList` 和 `passengerList`。

发 `OAT_BINDING` 卡片让用户选择出差单 + 成本中心。

### 5.4 归属公司/项目组（条件执行）

**仅当** `ctx.costCenter == "DISPLAY_INPUT"` 且 `ctx.allowSpecifyClient == true` 时执行。

**归属公司**: `POST /air/customer/listClientBelongCompany`

```json
{"clientIdSpecify": "<ctx.clientId>"}
```

**项目组**: `POST /air/customer/getClientProject`

```json
{"clientIdSpecify": "<ctx.clientId>", "showAll": false}
```

### 5.5 收货地址（条件执行）

**仅当** 需要纸质行程单时（`saveOrder.needAddress == "1"`）执行。

**API**: `POST /air/customer/getPassengerAllAddress`

```json
{}
```

选择默认地址（`current == true`）或让用户选择。

## 完成后上下文状态

| 上下文变量 | 来源 |
|---|---|
| `ctx.passengerList[]` | findPassenger + 用户选择 + 补充信息 |
| `ctx.applicationId` | 出差单选择（可选） |
| `ctx.applicationDh` | 出差单单号（可选） |
| `ctx.costCenterId` | 成本中心 ID |
| `ctx.belongCompany` | 归属公司 |
| `ctx.belongCompanyCode` | 归属公司编码 |
| `ctx.projectName` | 项目组名称（可选） |
| `ctx.belongProjectCode` | 项目编码（可选） |
| `ctx.travelPolicyList` | waitSave 返回 |
| `ctx.insuranceList` | waitSave 返回 |
| `ctx.mileageCardList` | waitSave 返回 |
| `ctx.addressInfo` | 收货地址（可选） |
