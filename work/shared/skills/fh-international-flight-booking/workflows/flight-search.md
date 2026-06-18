# Workflow: Flight Search (Step 2)

> 加载时机：进入 SEARCH_PARAMS_READY 阶段时加载本文件。

## 前置条件 (GATE)

| 参数 | 来源 | 校验 |
|---|---|---|
| 出发城市（三字码） | 用户输入 → `context/city-code-lookup.md` 查找 | 非空 3 字母 |
| 到达城市（三字码） | 用户输入 → `context/city-code-lookup.md` 查找 | 非空 3 字母 |
| 出发日期 | 用户输入（规范化为 yyyy-MM-dd） | 合法日期 |
| `ctx.clientId` | Step 1 | 非空 |

缺失 → 发 `OD_INPUT` 卡片补齐，**禁止**用空值调用 API。

## 执行步骤

### 2.1 请求体组装

**API**: `POST /air/international/intShopping`

```json
{
  "stopQuantity": 0,
  "onlyBigCustomerPrice": true,
  "clientId": "<ctx.clientId>",
  "language": "cn",
  "passengerType": "ADT",
  "tripList": [
    {
      "fromCity": "<出发城市三字码>",
      "toCity": "<到达城市三字码>",
      "flyDate": "<yyyy-MM-dd>",
      "isCity": true
    }
  ]
}
```

**往返行程** `tripList` 含两个元素：
```json
[
  {"fromCity":"SZX","toCity":"LHR","flyDate":"2026-07-15","isCity":true},
  {"fromCity":"LHR","toCity":"SZX","flyDate":"2026-07-22","isCity":true}
]
```

**可选参数**（用户提及才填，否则省略）：

| 参数 | 用户原话示例 | 填入值 |
|---|---|---|
| `airIdList[]` | "坐南航" | `["CZ"]` |
| `cabClass[]` | "商务舱" | `["BUSINESS"]` |
| `stopQuantity` | "直飞" | `0` |
| `passengerType` | "带小孩" | `"CHD"` |

**禁止**填入用户未提及的可选参数。禁止假设默认舱等。

### 2.2 返回体精简

`intShopping` 返回体巨大（可能 > 100KB），必须经 `compact_intl_payload.py` 压缩：

```bash
python3 scripts/compact_intl_payload.py raw_result.json --limit 10
```

保留的决策字段：
- `data.serialNumber`
- `data.groupList[].groupId`
- `data.groupList[].tripList[].flightList[].flightId, flyDate, arrDate, duration, fromPort, toPort`
- `data.groupList[].priceList[].priceId, price, tax, totalPrice, cabClass, passengerType`
- `data.cityList[]`
- `data.airwayList[]`
- `data.baggageList[]`

### 2.3 航班列表渲染

触发标准 AGUI：`PLAIN_TEXT`

将压缩后的结果渲染为 Markdown 表格，通过 `FLIGHT_RESULT` 卡片的 `body.contentJson.dataList[0]` 传递。

```bash
python3 scripts/render_intl_options.py compact.json
```

### 2.4 签证提醒（条件执行）

若 `groupList[].tripList[].visaInfoList` 非空，调用：

**API**: `POST /air/international/visa`

```json
{
  "fromCity": "<出发城市三字码>",
  "toCity": "<到达城市三字码>",
  "stopCity": "<中转城市三字码,逗号分隔（可选）>"
}
```

在航班列表卡片后追加 `PLAIN_TEXT`：`data.visaDetails` 内容。

### 2.5 上下文存储

| 上下文变量 | 来源 |
|---|---|
| `ctx.serialNumber` | `intShopping` → `data.serialNumber` |
| `ctx.rawGroupList` | 压缩后的 `data.groupList[]` |
| `ctx.cityList` | `data.cityList[]` |
| `ctx.airwayList` | `data.airwayList[]` |
| `ctx.baggageList` | `data.baggageList[]` |

## 错误处理

| 场景 | 行为 |
|---|---|
| 查询无结果 | `PLAIN_TEXT`: "未找到符合条件的航班，请调整出发日期或路线" |
| API 超时 | `CANNOT_ORDER`: "航班查询服务暂时超时，请稍后重试" |
| errorCode != "0" | 显示 `errorMsg` 中文错误说明 |
