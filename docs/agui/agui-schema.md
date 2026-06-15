# AGUI JSON Schema 规范

> 本规范基于 `docs/agui/` 目录下的 3 个实际响应样本（`01-airplan-list.json`、`02-airplan-set-list.json`、`03-pay-list.json`）归纳而成，描述国内机票（`sceneId` 以 `DOMESTIC_BOOKING_` 开头）业务场景下，AGUI（Agent GUI）通道的响应数据结构。规范版本：`schemaVersion = "2"`。

---

## 1. 文件清单

| 样本文件 | sceneId | 用途 | 出现的 basicType |
| --- | --- | --- | --- |
| `01-airplan-list.json` | `DOMESTIC_BOOKING_FLIGHT_LIST` | 航班列表查询 | `AIR_DOMESTIC_FLIGHT_LIST` / `PLAIN_TEXT` / `AIR_DOMESTIC_FLIGHT_SUGGEST` |
| `02-airplan-set-list.json` | `DOMESTIC_BOOKING_CABIN_LIST` | 选中航班后的舱位列表 | `PLAIN_TEXT` / `AIR_DOMESTIC_CABIN_LIST` |
| `03-pay-list.json` | `DOMESTIC_BOOKING_ORDER_CONFIRM` | 订单确认（待支付） | `PLAIN_TEXT` / `AIR_DOMESTIC_ORDER_SUMMARY` / `BUTTON` |

---

## 2. 顶层响应 Envelope

```json
{
  "tmsErrorCode": "",
  "errorCode": "0",
  "errorMsg": "",
  "enErrorMsg": "",
  "requestSeqNo": "T260615114050B00000001",
  "delay": 6591,
  "data": { /* AssistantTurn，见 §3 */ }
}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `tmsErrorCode` | string | 是 | 底层 TMS 错误码；空串表示无 |
| `errorCode` | string | 是 | 业务错误码；`"0"` 表示成功 |
| `errorMsg` | string | 是 | 中文错误信息 |
| `enErrorMsg` | string | 是 | 英文错误信息 |
| `requestSeqNo` | string | 是 | 请求序列号（`T` 前缀 + 时间戳 + 序号） |
| `delay` | integer | 是 | 服务端处理耗时（毫秒） |
| `data` | object | 是 | 助手返回内容，见 §3 |

---

## 3. `data` — AssistantTurn

```json
{
  "recordId": "T260615114050B00000001",
  "sessionId": "S260615114027B00000001",
  "role": "assistant",
  "intent": "BOOKING:DOMESTIC_BOOKING/air_domestic_booking",
  "sceneId": "DOMESTIC_BOOKING_FLIGHT_LIST",
  "contentJson": { /* 见 §4 */ },
  "reason": "已按您的行程条件查询航班并整理列表",
  "chatTime": "2026-06-15T03:40:57.032094018Z",
  "correlationId": ""
}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `recordId` | string | 是 | 本条消息记录 ID，与 `requestSeqNo` 一致 |
| `sessionId` | string | 是 | 所属会话 ID（`S` 前缀） |
| `role` | string | 是 | 固定 `"assistant"` |
| `intent` | string | 是 | 意图路由，格式 `<NAMESPACE>:<DOMAIN>/<scenario>`，如 `BOOKING:DOMESTIC_BOOKING/air_domestic_booking` |
| `sceneId` | string | 是 | 业务场景 ID，决定 `dataList` 中应出现的 `basicType` 组合 |
| `contentJson` | object | 是 | 渲染内容，结构见 §4 |
| `reason` | string | 是 | 助手结论摘要（多行以 `\n` 分隔） |
| `chatTime` | string | 是 | ISO 8601 UTC 时间戳 |
| `correlationId` | string | 否 | 链路追踪 ID；空串表示无 |

### 3.1 `sceneId` 已观察到的取值

| sceneId | 含义 | 主要 basicType |
| --- | --- | --- |
| `DOMESTIC_BOOKING_FLIGHT_LIST` | 航班列表 | `AIR_DOMESTIC_FLIGHT_LIST` + `AIR_DOMESTIC_FLIGHT_SUGGEST` + `PLAIN_TEXT` |
| `DOMESTIC_BOOKING_CABIN_LIST` | 舱位列表 | `AIR_DOMESTIC_CABIN_LIST` + `PLAIN_TEXT` |
| `DOMESTIC_BOOKING_ORDER_CONFIRM` | 订单确认 | `AIR_DOMESTIC_ORDER_SUMMARY` + `BUTTON` + `PLAIN_TEXT` |

---

## 4. `contentJson`

```json
{
  "schemaVersion": "2",
  "dataList": [ /* DataItem 数组，按渲染顺序排列 */ ],
  "thinkingSteps": [
    "已按您的行程条件查询航班并整理列表",
    "已根据页面点选确定航班"
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `schemaVersion` | string | 是 | 内容协议版本；当前为 `"2"` |
| `dataList` | DataItem[] | 是 | 渲染单元列表，**至少 1 项**；不同 `sceneId` 下 `basicType` 组合受限，见 §3.1 |
| `thinkingSteps` | string[] | 否 | 思考步骤，按时间顺序；用于前端折叠展示 |

---

## 5. `DataItem` — 通用渲染单元

所有 `dataList` 元素的统一外壳：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `basicType` | string | 是 | 渲染类型，决定 `dataJson` 的 schema；枚举见 §6 |
| `dataStr` | string | 是 | 展示用主文本（标题 / 提示文案 / 按钮文案） |
| `dataJson` | object \| null | 是 | 结构化数据；纯文本 / 按钮可置 `null` |
| `linkUrl` | string | 是 | 跳转标识或 URL；空串表示无跳转；按钮用枚举值，如 `GO_PAY` |

---

## 6. `basicType` 与 `dataJson` 详表

### 6.1 `PLAIN_TEXT`

- 纯文本段落。
- `dataStr`：要展示的文本（支持中文 / 换行 / 全角符号）。
- `dataJson`：`null`。
- `linkUrl`：`""`。

### 6.2 `AIR_DOMESTIC_FLIGHT_LIST`

航班列表卡片。

```json
{
  "basicType": "AIR_DOMESTIC_FLIGHT_LIST",
  "dataStr": "共查询到133个航班最后筛选出133个",
  "dataJson": {
    "serialNumber": "260615114056A00000001",
    "totalCount": 133,
    "filteredCount": 133,
    "flightList": [ /* Flight[]，见 §7.1 */ ]
  },
  "linkUrl": ""
}
```

| dataJson 字段 | 类型 | 说明 |
| --- | --- | --- |
| `serialNumber` | string | 查询批次号（A 前缀），与提交订单的 `serialNumber` 关联 |
| `totalCount` | integer | 原始命中数 |
| `filteredCount` | integer | 过滤后数 |
| `flightList` | Flight[] | 航班列表 |

### 6.3 `AIR_DOMESTIC_FLIGHT_SUGGEST`

单条推荐航班（早班 / 午间 / 晚间等分时低价），无列表包装。

- `dataStr`：推荐标题，如 `"早班低价推荐"`。
- `dataJson`：**单个 Flight 对象**（见 §7.1）。
- `linkUrl`：`""`。

### 6.4 `AIR_DOMESTIC_CABIN_LIST`

舱位列表（含已选航班摘要）。

```json
{
  "basicType": "AIR_DOMESTIC_CABIN_LIST",
  "dataStr": "可选舱位",
  "dataJson": {
    "serialNumber": "260615114056A00000001",
    "cabins": [ /* Cabin[]，见 §7.4 */ ],
    "selectedFlight": { /* Flight，见 §7.1 */ }
  },
  "linkUrl": ""
}
```

| dataJson 字段 | 类型 | 说明 |
| --- | --- | --- |
| `serialNumber` | string | 关联航班列表的批次号 |
| `cabins` | Cabin[] | 可选舱位，按价格升序 |
| `selectedFlight` | Flight | 用户已选中的航班 |

### 6.5 `AIR_DOMESTIC_ORDER_SUMMARY`

订单确认摘要 + 提交载荷。

```json
{
  "basicType": "AIR_DOMESTIC_ORDER_SUMMARY",
  "dataStr": "订单确认",
  "dataJson": {
    "actionType": "SUBMIT_ORDER",
    "orderId": "20260615000000013",
    "orderNo": "89ITZ",
    "orderStatus": "PENDING_PAY",
    "totalPrice": 1016,
    "passengerCount": 1,
    "createTime": "2026-06-15T11:43:14.739110292",
    "pnr": null,
    "idempotencyKey": "0203be28-7e31-4cb8-904c-2a638fc14357",
    "message": "订单已生成，请您确认信息后前往支付",
    "payUrl": null,
    "payDeadline": null,
    "submitPayload": { /* SubmitPayload，见 §7.5 */ },
    "flightSummary": { /* FlightSummary，见 §7.6 */ },
    "passengerLines": [
      "刘酝泽(身份证:220502200008120216)"
    ],
    "tripTypeLabel": "单程"
  },
  "linkUrl": ""
}
```

| dataJson 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `actionType` | string | 是 | 前端动作标识；当前样本均为 `SUBMIT_ORDER` |
| `orderId` | string | 是 | 系统内部订单 ID（长整型字符串） |
| `orderNo` | string | 是 | 业务订单号（短码，如 `89ITZ`） |
| `orderStatus` | string | 是 | 订单状态枚举；已观察到 `PENDING_PAY` |
| `totalPrice` | number | 是 | 订单总价（含税 + 服务费） |
| `passengerCount` | integer | 是 | 乘机人数 |
| `createTime` | string | 是 | ISO 8601 本地时间戳 |
| `pnr` | string \| null | 否 | 航司 PNR；下单未出票时为 `null` |
| `idempotencyKey` | string | 是 | 幂等键（UUID） |
| `message` | string | 是 | 展示文案 |
| `payUrl` | string \| null | 否 | 支付跳转 URL；未生成时为 `null` |
| `payDeadline` | string \| null | 否 | 支付截止时间（ISO 8601）；未生成时为 `null` |
| `submitPayload` | SubmitPayload | 是 | 提交订单所需的全部参数 |
| `flightSummary` | FlightSummary | 是 | 航班摘要（仅首段） |
| `passengerLines` | string[] | 是 | 乘机人展示行，格式 `"姓名(证件:证件号)"` |
| `tripTypeLabel` | string | 是 | 行程类型中文标签，如 `"单程"`、`"往返"` |

### 6.6 `BUTTON`

操作按钮。

- `dataStr`：按钮文案，如 `"去支付"`。
- `dataJson`：`null`。
- `linkUrl`：动作枚举或 URL；已观察到 `"GO_PAY"`。

---

## 7. 公共子结构

### 7.1 `Flight`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `depCityName` | string | 是 | 出发城市中文名 |
| `arrCityName` | string | 是 | 到达城市中文名 |
| `depDate` | string | 是 | 出发日期 `YYYY-MM-DD` |
| `lowestPrice` | number | 是 | 该航班最低舱位价（人民币，元） |
| `lowestCabinName` | string | 是 | 最低价对应舱位名；已观察到 `ECONOMY` |
| `totalPrice` | number | 是 | 当前展示总价（最低价对应总价） |
| `totalDuration` | integer | 是 | 总时长（分钟） |
| `durationMin` | integer | 是 | 与 `totalDuration` 同义，部分场景冗余 |
| `stopCount` | integer | 是 | 经停次数（同一航段内的中停） |
| `transferCount` | integer | 是 | 中转次数（多段联程） |
| `transferCities` | string[] | 是 | 中转城市列表；无中转时为空数组 |
| `airlineName` | string | 是 | 承运航司中文名 |
| `flightNo` | string | 是 | 航班号（含航司代码，如 `ZH9111`） |
| `airId` | string | 是 | 航司二字码（如 `ZH`、`CA`、`MU`） |
| `tripType` | string | 是 | 行程类型；已观察到 `OW`（One Way，单程） |
| `serialNo` | integer | 是 | 列表内序号，从 1 开始 |
| `flightId` | string | 是 | 航班唯一标识（多数样本与 `flightNo` 相同） |
| `legs` | Leg[] | 是 | 航段列表；单程通常 1 段 |
| `depTime` | string | 是 | 出发时间 `HH:MM` |
| `depAirportName` | string | 是 | 出发机场中文名 |
| `depTerminal` | string | 是 | 出发航站楼；空串表示未指定 |
| `shareFlight` | boolean | 是 | 是否共享航班 |
| `shareId` | string | 否 | 共享主航班号；非共享时为 `""` |
| `arrDate` | string | 是 | 到达日期 `YYYY-MM-DD` |
| `arrTime` | string | 是 | 到达时间 `HH:MM` |
| `arrAirportName` | string | 是 | 到达机场中文名 |
| `arrTerminal` | string | 是 | 到达航站楼；空串表示未指定 |
| `arrDayOffset` | integer | 是 | 到达相对出发日的天数偏移（0 = 当日，1 = 次日） |

### 7.2 `Leg`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `direction` | string | 是 | 方向；已观察到 `OUTBOUND`（去程）；往返场景下还会有 `INBOUND` |
| `flightNo` | string | 是 | 航段航班号 |
| `airlineName` | string | 是 | 航段承运航司 |
| `depDate` | string | 是 | 出发日期 `YYYY-MM-DD` |
| `depTime` | string | 是 | 出发时间 `HH:MM` |
| `arrTime` | string | 是 | 到达时间 `HH:MM` |
| `arrDate` | string | 是 | 到达日期 `YYYY-MM-DD` |
| `depAirportName` | string | 是 | 出发机场 |
| `depTerminal` | string | 是 | 出发航站楼 |
| `arrAirportName` | string | 是 | 到达机场 |
| `arrTerminal` | string | 是 | 到达航站楼；空串表示未指定 |
| `duration` | integer | 是 | 航段时长（分钟） |
| `aircraftName` | string | 是 | 机型简码（如 `320`、`7MX`、`359`） |
| `meal` | boolean | 是 | 是否含餐 |
| `shareFlight` | boolean | 是 | 是否共享航班 |
| `shareId` | string | 否 | 共享主航班号；非共享时为 `""` |
| `stops` | Stop[] | 是 | 经停列表；无经停时为空数组 |
| `arrDayOffset` | integer | 是 | 到达相对出发日的天数偏移 |

### 7.3 `Stop`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `stopCityName` | string \| null | 否 | 经停城市；样本中均以 `null` 出现 |
| `duration` | integer \| null | 否 | 经停时长（分钟）；样本中均以 `null` 出现 |

### 7.4 `Cabin`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `cabId` | string | 是 | 舱位业务 ID（字符串型） |
| `cabinName` | string | 是 | 舱位中文名（`经济舱` / `尊享舒适经济舱` 等） |
| `cab` | string | 是 | 舱位单字母代码（`Y` / `K` / `P` / `V` / `S` / `W` / `E` / `Q` / `H` / `U` / `M` / `B` / `G` …） |
| `cabinCode` | string | 是 | 与 `cab` 相同的展示用代码 |
| `cabClass` | string | 是 | 舱位等级码；已观察到 `Y` / `Y1` / `W` / `W1` |
| `price` | number | 是 | 票面价 |
| `totalPrice` | number | 是 | 含税 + 服务费总价 |
| `normalPrice` | number | 是 | 全价基准价 |
| `discountRate` | number | 是 | 折扣率（`0~1`，`1` 表示全价） |
| `tax` | number | 是 | 税费 |
| `clientService` | number | 是 | 服务费 |
| `mealIncluded` | boolean | 是 | 是否含餐 |
| `miniPriceFlag` | boolean \| null | 否 | 是否最低价标记 |
| `productLabel` | string \| null | 否 | 产品角标文案 |
| `productName` | string \| null | 否 | 产品包名 |
| `priceType` | integer | 是 | 价格类型；已观察到 `0` / `1` |
| `priceKind` | integer | 是 | 价格种类；样本中均为 `0` |
| `refund` | string \| null | 否 | 退票规则（中文长文本） |
| `change` | string \| null | 否 | 改期规则（中文长文本） |
| `refundRules` | object \| null | 否 | 结构化退票规则；样本中均为 `null` |
| `changeRules` | object \| null | 否 | 结构化改期规则；样本中均为 `null` |
| `luggage` | string | 是 | 行李额（中文长文本） |
| `baggagePolicy` | object \| null | 否 | 结构化行李政策；样本中均为 `null` |
| `weight` | string | 是 | 免费托运重量（字符串，如 `"20"`） |
| `remainSeats` | integer | 是 | 剩余座位数；`0` 通常表示 `A`（多于 9 张） |
| `num` | string | 是 | 剩余座位数字展示；`"A"` 表示充足（>=10） |
| `returnCabinName` | string \| null | 否 | 返程舱位名（往返场景） |
| `returnCab` | string \| null | 否 | 返程舱位代码 |
| `returnCabClass` | string \| null | 否 | 返程舱位等级 |
| `returnLuggage` | string \| null | 否 | 返程行李额 |
| `outboundLuggage` | string \| null | 否 | 去程行李额（往返冗余字段） |
| `policyCompliance` | object \| null | 否 | 差旅政策合规结果；样本中均为 `null` |

### 7.5 `SubmitPayload`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `serialNumber` | string | 是 | 关联航班列表的批次号 |
| `cabId` | string | 是 | 选中舱位的 `cabId` |
| `passengers` | Passenger[] | 是 | 乘机人列表（去重） |
| `costCenterId` | string | 是 | 成本中心 / 部门 ID |
| `contactName` | string | 是 | 联系人姓名 |
| `contactPhone` | string | 是 | 联系人手机号 |
| `idempotencyKey` | string | 是 | 幂等键（与 `orderSummary.idempotencyKey` 一致） |

#### 7.5.1 `Passenger`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `name` | string | 是 | 乘机人姓名 |
| `idType` | string | 是 | 证件类型中文名（如 `身份证`） |
| `idNo` | string | 是 | 证件号 |
| `userCode` | string | 是 | 员工编号 |
| `id` | integer | 是 | 乘机人业务 ID |
| `_rawPassengerResult` | RawPassengerResult | 是 | 原始乘机人档案（脱敏） |
| `depId` | integer | 是 | 部门 ID |
| `mobile` | string | 是 | 手机号 |
| `phone` | string | 是 | 备用联系电话（常与 `mobile` 相同） |

#### 7.5.2 `RawPassengerResult`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | integer | 是 | 乘机人 ID |
| `userID` | integer | 是 | 关联用户 ID |
| `passengerName` | string | 是 | 姓名 |
| `certNo` | string | 是 | 证件号（**已脱敏**，如 `220502********0216`） |
| `certType` | string | 是 | 证件类型 |
| `sex` | string | 是 | 性别；空串表示未指定 |
| `userCode` | string | 是 | 员工编号 |
| `email` | string | 是 | 邮箱；空串表示无 |
| `depId` | integer | 是 | 部门 ID |
| `depName` | string | 是 | 部门名称 |
| `accountBank` | string | 是 | 开户行；空串表示无 |
| `birthDay` | string \| null | 否 | 出生日期（ISO 8601 或 `null`） |
| `certName` | string | 是 | 证件上姓名 |
| `certNamePinyin` | string | 是 | 姓名拼音；空串表示无 |
| `nationality` | string | 是 | 国籍码；空串表示中国 |
| `nationalityName` | string | 是 | 国籍中文名；空串表示中国 |
| `expiryDate` | string | 是 | 证件有效期；空串表示长期 |
| `telList` | Tel[] | 是 | 联系电话列表 |
| `mobile` | string | 是 | 默认手机号 |
| `ageLevel` | integer | 是 | 年龄段（0 = 成人） |
| `currentUser` | boolean | 是 | 是否当前登录用户本人 |

#### 7.5.3 `Tel`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | integer | 是 | 电话 ID |
| `pid` | integer | 是 | 关联乘机人 ID |
| `tel` | string | 是 | 电话号码 |
| `ifDefault` | integer | 是 | 是否默认电话（`0` = 否，`1` = 是） |

### 7.6 `FlightSummary`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `depDate` | string | 是 | 出发日期 `YYYY-MM-DD` |
| `depTime` | string | 是 | 出发时间 `HH:MM` |
| `arrTime` | string | 是 | 到达时间 `HH:MM` |
| `depAirportName` | string | 是 | 出发机场 |
| `arrAirportName` | string | 是 | 到达机场 |
| `airlineName` | string | 是 | 航司 |
| `flightNo` | string | 是 | 航班号 |
| `depCityName` | string | 是 | 出发城市 |
| `arrCityName` | string | 是 | 到达城市 |

---

## 8. 完整 JSON Schema（Draft 2020-12）

> 可直接复制到 `agui.schema.json` 后用 Ajv / jsonschema / pydantic 等校验库加载。

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://openagent.local/schemas/agui.schema.json",
  "title": "AGUIResponse",
  "type": "object",
  "additionalProperties": false,
  "required": ["tmsErrorCode", "errorCode", "errorMsg", "enErrorMsg", "requestSeqNo", "delay", "data"],
  "properties": {
    "tmsErrorCode":  { "type": "string" },
    "errorCode":     { "type": "string" },
    "errorMsg":      { "type": "string" },
    "enErrorMsg":    { "type": "string" },
    "requestSeqNo":  { "type": "string", "pattern": "^T[0-9]+B[0-9]+$" },
    "delay":         { "type": "integer", "minimum": 0 },
    "data":          { "$ref": "#/$defs/AssistantTurn" }
  },
  "$defs": {
    "AssistantTurn": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "recordId", "sessionId", "role", "intent", "sceneId",
        "contentJson", "reason", "chatTime"
      ],
      "properties": {
        "recordId":      { "type": "string" },
        "sessionId":     { "type": "string", "pattern": "^S[0-9]+B[0-9]+$" },
        "role":          { "const": "assistant" },
        "intent":        { "type": "string" },
        "sceneId":       { "type": "string" },
        "contentJson":   { "$ref": "#/$defs/ContentJson" },
        "reason":        { "type": "string" },
        "chatTime":      { "type": "string", "format": "date-time" },
        "correlationId": { "type": "string" }
      }
    },

    "ContentJson": {
      "type": "object",
      "additionalProperties": false,
      "required": ["schemaVersion", "dataList"],
      "properties": {
        "schemaVersion":  { "const": "2" },
        "dataList":       { "type": "array", "minItems": 1, "items": { "$ref": "#/$defs/DataItem" } },
        "thinkingSteps":  { "type": "array", "items": { "type": "string" } }
      }
    },

    "DataItem": {
      "type": "object",
      "additionalProperties": false,
      "required": ["basicType", "dataStr", "dataJson", "linkUrl"],
      "properties": {
        "basicType": { "$ref": "#/$defs/BasicType" },
        "dataStr":   { "type": "string" },
        "dataJson":  { "type": ["object", "null"] },
        "linkUrl":   { "type": "string" }
      },
      "allOf": [
        { "$ref": "#/$defs/DataItemTypeGuard" }
      ]
    },

    "BasicType": {
      "type": "string",
      "enum": [
        "PLAIN_TEXT",
        "AIR_DOMESTIC_FLIGHT_LIST",
        "AIR_DOMESTIC_FLIGHT_SUGGEST",
        "AIR_DOMESTIC_CABIN_LIST",
        "AIR_DOMESTIC_ORDER_SUMMARY",
        "BUTTON"
      ]
    },

    "DataItemTypeGuard": {
      "if": { "properties": { "basicType": { "const": "PLAIN_TEXT" } } },
      "then": { "properties": { "dataJson": { "const": null }, "linkUrl": { "type": "string", "maxLength": 0 } } }
    },

    "Flight": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "depCityName", "arrCityName", "depDate",
        "lowestPrice", "lowestCabinName",
        "totalPrice", "totalDuration", "durationMin",
        "stopCount", "transferCount", "transferCities",
        "airlineName", "flightNo", "airId",
        "tripType", "serialNo", "flightId",
        "legs", "depTime", "depAirportName", "depTerminal",
        "shareFlight", "arrDate", "arrTime", "arrAirportName",
        "arrTerminal", "arrDayOffset"
      ],
      "properties": {
        "depCityName":     { "type": "string" },
        "arrCityName":     { "type": "string" },
        "depDate":         { "type": "string", "format": "date" },
        "lowestPrice":     { "type": "number", "minimum": 0 },
        "lowestCabinName": { "type": "string" },
        "totalPrice":      { "type": "number", "minimum": 0 },
        "totalDuration":   { "type": "integer", "minimum": 0 },
        "durationMin":     { "type": "integer", "minimum": 0 },
        "stopCount":       { "type": "integer", "minimum": 0 },
        "transferCount":   { "type": "integer", "minimum": 0 },
        "transferCities":  { "type": "array", "items": { "type": "string" } },
        "airlineName":     { "type": "string" },
        "flightNo":        { "type": "string" },
        "airId":           { "type": "string", "minLength": 2, "maxLength": 3 },
        "tripType":        { "type": "string", "enum": ["OW", "RT"] },
        "serialNo":        { "type": "integer", "minimum": 1 },
        "flightId":        { "type": "string" },
        "legs":            { "type": "array", "minItems": 1, "items": { "$ref": "#/$defs/Leg" } },
        "depTime":         { "type": "string", "pattern": "^[0-2][0-9]:[0-5][0-9]$" },
        "depAirportName":  { "type": "string" },
        "depTerminal":     { "type": "string" },
        "shareFlight":     { "type": "boolean" },
        "shareId":         { "type": "string" },
        "arrDate":         { "type": "string", "format": "date" },
        "arrTime":         { "type": "string", "pattern": "^[0-2][0-9]:[0-5][0-9]$" },
        "arrAirportName":  { "type": "string" },
        "arrTerminal":     { "type": "string" },
        "arrDayOffset":    { "type": "integer", "minimum": 0 }
      }
    },

    "Leg": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "direction", "flightNo", "airlineName",
        "depDate", "depTime", "arrTime", "arrDate",
        "depAirportName", "depTerminal",
        "arrAirportName", "arrTerminal",
        "duration", "aircraftName", "meal",
        "shareFlight", "stops", "arrDayOffset"
      ],
      "properties": {
        "direction":     { "type": "string", "enum": ["OUTBOUND", "INBOUND"] },
        "flightNo":      { "type": "string" },
        "airlineName":   { "type": "string" },
        "depDate":       { "type": "string", "format": "date" },
        "depTime":       { "type": "string", "pattern": "^[0-2][0-9]:[0-5][0-9]$" },
        "arrTime":       { "type": "string", "pattern": "^[0-2][0-9]:[0-5][0-9]$" },
        "arrDate":       { "type": "string", "format": "date" },
        "depAirportName":{ "type": "string" },
        "depTerminal":   { "type": "string" },
        "arrAirportName":{ "type": "string" },
        "arrTerminal":   { "type": "string" },
        "duration":      { "type": "integer", "minimum": 0 },
        "aircraftName":  { "type": "string" },
        "meal":          { "type": "boolean" },
        "shareFlight":   { "type": "boolean" },
        "shareId":       { "type": "string" },
        "stops":         { "type": "array", "items": { "$ref": "#/$defs/Stop" } },
        "arrDayOffset":  { "type": "integer", "minimum": 0 }
      }
    },

    "Stop": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "stopCityName": { "type": ["string", "null"] },
        "duration":     { "type": ["integer", "null"], "minimum": 0 }
      }
    },

    "Cabin": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "cabId", "cabinName", "cab", "cabinCode", "cabClass",
        "price", "totalPrice", "normalPrice", "discountRate",
        "tax", "clientService", "mealIncluded",
        "priceType", "priceKind", "luggage", "weight",
        "remainSeats", "num"
      ],
      "properties": {
        "cabId":            { "type": "string" },
        "cabinName":        { "type": "string" },
        "cab":              { "type": "string", "minLength": 1, "maxLength": 1 },
        "cabinCode":        { "type": "string" },
        "cabClass":         { "type": "string" },
        "price":            { "type": "number", "minimum": 0 },
        "totalPrice":       { "type": "number", "minimum": 0 },
        "normalPrice":      { "type": "number", "minimum": 0 },
        "discountRate":     { "type": "number", "minimum": 0, "maximum": 1 },
        "tax":              { "type": "number", "minimum": 0 },
        "clientService":    { "type": "number", "minimum": 0 },
        "mealIncluded":     { "type": "boolean" },
        "miniPriceFlag":    { "type": ["boolean", "null"] },
        "productLabel":     { "type": ["string", "null"] },
        "productName":      { "type": ["string", "null"] },
        "priceType":        { "type": "integer" },
        "priceKind":        { "type": "integer" },
        "refund":           { "type": ["string", "null"] },
        "change":           { "type": ["string", "null"] },
        "refundRules":      { "type": ["object", "null"] },
        "changeRules":      { "type": ["object", "null"] },
        "luggage":          { "type": "string" },
        "baggagePolicy":    { "type": ["object", "null"] },
        "weight":           { "type": "string" },
        "remainSeats":      { "type": "integer", "minimum": 0 },
        "num":              { "type": "string" },
        "returnCabinName":  { "type": ["string", "null"] },
        "returnCab":        { "type": ["string", "null"] },
        "returnCabClass":   { "type": ["string", "null"] },
        "returnLuggage":    { "type": ["string", "null"] },
        "outboundLuggage":  { "type": ["string", "null"] },
        "policyCompliance": { "type": ["object", "null"] }
      }
    },

    "CabinListDataJson": {
      "type": "object",
      "additionalProperties": false,
      "required": ["serialNumber", "cabins", "selectedFlight"],
      "properties": {
        "serialNumber":  { "type": "string" },
        "cabins":        { "type": "array", "minItems": 1, "items": { "$ref": "#/$defs/Cabin" } },
        "selectedFlight":{ "$ref": "#/$defs/Flight" }
      }
    },

    "FlightListDataJson": {
      "type": "object",
      "additionalProperties": false,
      "required": ["serialNumber", "totalCount", "filteredCount", "flightList"],
      "properties": {
        "serialNumber":  { "type": "string" },
        "totalCount":    { "type": "integer", "minimum": 0 },
        "filteredCount": { "type": "integer", "minimum": 0 },
        "flightList":    { "type": "array", "items": { "$ref": "#/$defs/Flight" } }
      }
    },

    "Tel": {
      "type": "object",
      "additionalProperties": false,
      "required": ["id", "pid", "tel", "ifDefault"],
      "properties": {
        "id":        { "type": "integer" },
        "pid":       { "type": "integer" },
        "tel":       { "type": "string" },
        "ifDefault": { "type": "integer", "enum": [0, 1] }
      }
    },

    "RawPassengerResult": {
      "type": "object",
      "additionalProperties": true,
      "required": [
        "id", "userID", "passengerName", "certNo", "certType",
        "userCode", "depId", "depName",
        "certName", "telList", "mobile", "ageLevel", "currentUser"
      ],
      "properties": {
        "id":              { "type": "integer" },
        "userID":          { "type": "integer" },
        "passengerName":   { "type": "string" },
        "certNo":          { "type": "string" },
        "certType":        { "type": "string" },
        "sex":             { "type": "string" },
        "userCode":        { "type": "string" },
        "email":           { "type": "string" },
        "depId":           { "type": "integer" },
        "depName":         { "type": "string" },
        "accountBank":     { "type": "string" },
        "birthDay":        { "type": ["string", "null"], "format": "date" },
        "certName":        { "type": "string" },
        "certNamePinyin":  { "type": "string" },
        "nationality":     { "type": "string" },
        "nationalityName": { "type": "string" },
        "expiryDate":      { "type": "string" },
        "telList":         { "type": "array", "items": { "$ref": "#/$defs/Tel" } },
        "mobile":          { "type": "string" },
        "ageLevel":        { "type": "integer" },
        "currentUser":     { "type": "boolean" }
      }
    },

    "Passenger": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "name", "idType", "idNo", "userCode", "id",
        "_rawPassengerResult", "depId", "mobile", "phone"
      ],
      "properties": {
        "name":                { "type": "string" },
        "idType":              { "type": "string" },
        "idNo":                { "type": "string" },
        "userCode":            { "type": "string" },
        "id":                  { "type": "integer" },
        "_rawPassengerResult": { "$ref": "#/$defs/RawPassengerResult" },
        "depId":               { "type": "integer" },
        "mobile":              { "type": "string" },
        "phone":               { "type": "string" }
      }
    },

    "SubmitPayload": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "serialNumber", "cabId", "passengers",
        "costCenterId", "contactName", "contactPhone", "idempotencyKey"
      ],
      "properties": {
        "serialNumber":   { "type": "string" },
        "cabId":          { "type": "string" },
        "passengers":     { "type": "array", "minItems": 1, "items": { "$ref": "#/$defs/Passenger" } },
        "costCenterId":   { "type": "string" },
        "contactName":    { "type": "string" },
        "contactPhone":   { "type": "string" },
        "idempotencyKey": { "type": "string", "format": "uuid" }
      }
    },

    "FlightSummary": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "depDate", "depTime", "arrTime",
        "depAirportName", "arrAirportName",
        "airlineName", "flightNo",
        "depCityName", "arrCityName"
      ],
      "properties": {
        "depDate":        { "type": "string", "format": "date" },
        "depTime":        { "type": "string", "pattern": "^[0-2][0-9]:[0-5][0-9]$" },
        "arrTime":        { "type": "string", "pattern": "^[0-2][0-9]:[0-5][0-9]$" },
        "depAirportName": { "type": "string" },
        "arrAirportName": { "type": "string" },
        "airlineName":    { "type": "string" },
        "flightNo":       { "type": "string" },
        "depCityName":    { "type": "string" },
        "arrCityName":    { "type": "string" }
      }
    },

    "OrderSummaryDataJson": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "actionType", "orderId", "orderNo", "orderStatus",
        "totalPrice", "passengerCount", "createTime",
        "idempotencyKey", "message",
        "submitPayload", "flightSummary",
        "passengerLines", "tripTypeLabel"
      ],
      "properties": {
        "actionType":      { "type": "string" },
        "orderId":         { "type": "string" },
        "orderNo":         { "type": "string" },
        "orderStatus":     { "type": "string" },
        "totalPrice":      { "type": "number", "minimum": 0 },
        "passengerCount":  { "type": "integer", "minimum": 1 },
        "createTime":      { "type": "string" },
        "pnr":             { "type": ["string", "null"] },
        "idempotencyKey":  { "type": "string", "format": "uuid" },
        "message":         { "type": "string" },
        "payUrl":          { "type": ["string", "null"], "format": "uri" },
        "payDeadline":     { "type": ["string", "null"], "format": "date-time" },
        "submitPayload":   { "$ref": "#/$defs/SubmitPayload" },
        "flightSummary":   { "$ref": "#/$defs/FlightSummary" },
        "passengerLines":  { "type": "array", "minItems": 1, "items": { "type": "string" } },
        "tripTypeLabel":   { "type": "string" }
      }
    }
  }
}
```

> 备注：上方 `DataItem` 仅对 `PLAIN_TEXT` 加了 `dataJson == null` 的硬约束；其他 `basicType` 的 `dataJson` 形状按 §6 各小节说明 + 上面 `$defs` 对应类型自行校验。建议在业务层用 `if basicType == ...: validate(dataJson, ...)` 的方式二次校验。

---

## 9. sceneId ↔ basicType 组合

下表总结同一 `sceneId` 下 `dataList` 中**允许出现**的 `basicType` 组合（按 3 个样本观察，已可覆盖当前国内机票订票主流程）：

| sceneId | 允许的 basicType 集合（顺序敏感） |
| --- | --- |
| `DOMESTIC_BOOKING_FLIGHT_LIST` | `AIR_DOMESTIC_FLIGHT_LIST` → `PLAIN_TEXT`（叙述）→ `AIR_DOMESTIC_FLIGHT_SUGGEST` × N |
| `DOMESTIC_BOOKING_CABIN_LIST` | `PLAIN_TEXT`（提示）→ `AIR_DOMESTIC_CABIN_LIST` |
| `DOMESTIC_BOOKING_ORDER_CONFIRM` | `PLAIN_TEXT`（提示）→ `AIR_DOMESTIC_ORDER_SUMMARY` → `BUTTON`（动作） |

未列出的 `basicType` 出现在对应 `sceneId` 时，前端应按"未渲染"处理并打 warn 日志。

---

## 10. 版本与演进

- 当前协议版本：`schemaVersion = "2"`。
- 新增 `basicType` 时：必须**同步**在 §6 增加小节、§8 JSON Schema `$defs` 增加类型、§9 维护 sceneId↔basicType 矩阵。
- 字段废弃：先在 `additionalProperties: false` 的对象里保留字段并标注 deprecated，下一主版本再移除；不要在样本里直接删除，否则校验将失败。
- 字段新增：在对应 `$defs` 子结构里 `required` 不加、只放 `properties`，保证向后兼容。
