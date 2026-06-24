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

### 2.2 Hub 自动生成航班卡片

`intShopping` 返回后，Hub 端会**自动拦截结果并生成 `FLIGHT_RESULT` 卡片**发送给用户。
**不要**调用 `compact_intl_payload.py` 或 `render_intl_options.py`。

**禁止读取 spill 文件**：`intShopping` 返回大量数据时，`tool_result` 会包含 `_hub_marker: full_output_spilled` 指向 spill 文件。
**绝对禁止** `python3 -c "... open(spill.json) ..."` 读取和解析 spill 文件。这会产生 5-10 次无意义工具调用。
Hub 已经处理完毕，你只需要用简短中文概述查询结果（如"已为您找到 103 个航班"），然后等待用户选择航班。

### 2.3 serialNumber 提取（关键）

**唯一合法来源**：`intShopping` 返回的 `data.serialNumber`（20位 `YYYYMMDDHHMMA+7位`，如 `260623165123A0000001`）。

**不要**用以下字符串替代：
- ❌ `serialKey`（BFF 内部缓存 key）
- ❌ `requestSeqNo`（日志跟踪号）
- ❌ `orderGroupId` / `pnr` / `orderId`
- ❌ `groupId` / `priceId`

如果不确定，打开 spill 文件确认 `data.serialNumber` 字段。

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
| `ctx.rawGroupList` | `data.groupList[]`（原始返回） |
| `ctx.cityList` | `data.cityList[]` |
| `ctx.airwayList` | `data.airwayList[]` |
| `ctx.baggageList` | `data.baggageList[]` |

## 关键约束

- **严格查询范围**：用户说"深圳到曼谷"只查深圳→曼谷，**禁止**自行扩展增查曼谷→吉隆坡、吉隆坡→上海等。
- **往返/多程**：`tripList` 长度 > 1 时，去程 `io=0` / 回程 `io=1` 在同一 group 中绑定，价格含全部段。
- **Hub 自动卡片**：`intShopping` 后 Hub 自动生成航班卡片，**不要**调 compact/render 脚本，不要手动发 FLIGHT_RESULT。

## 错误处理

| 场景 | 行为 |
|---|---|
| 查询无结果 | `PLAIN_TEXT`: "未找到符合条件的航班，请调整出发日期或路线" |
| API 超时 | `CANNOT_ORDER`: "航班查询服务暂时超时，请稍后重试" |
| errorCode != "0" | 显示 `errorMsg` 中文错误说明 |
