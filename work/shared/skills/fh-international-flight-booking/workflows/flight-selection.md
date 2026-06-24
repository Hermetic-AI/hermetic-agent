# Workflow: Flight & Price Selection (Step 3)

> 加载时机：进入 FLIGHT_LISTED 阶段后用户选择航班时加载本文件。

## 前置条件 (GATE)

| 参数 | 来源 | 校验 |
|---|---|---|
| `ctx.serialNumber` | Step 2 intShopping | 非空 |
| `ctx.rawGroupList` | Step 2 intShopping | 非空数组 |

## 执行步骤

### 3.1 选择航班组合 (Group)

用户通过序号或描述选择一个 `groupList[]` 中的航班组合。

**选择方式**：
- 回复序号（如 "1"）
- 描述偏好（如 "最便宜的"、"直飞"、"南航"、"3小时内到达"）
- 指定航班号（如 "CZ301"）

Agent 从 `ctx.rawGroupList` 中匹配，确认后存储：

| 上下文变量 | 值 |
|---|---|
| `ctx.selectedGroupId` | 用户选中的 `groupList[].groupId` |
| `ctx.selectedGroup` | 完整 group 对象 |

**状态转换**: `FLIGHT_LISTED → GROUP_SELECTED`

### 3.2 展示价格方案

从 `ctx.selectedGroup.priceList[]` 展示所有可选价格方案。

触发标准 AGUI：`PLAIN_TEXT`

渲染为价格列表 Markdown 表格（见 `references/agui-mapping.md` 价格列表模板）。

每行包含：
- `priceId`（序号映射，不暴露原始 ID）
- 出票航司 (`airId`)
- 票面价 / 税费 / 服务费 / 总价
- 舱等 (`tripList[].cabClass`: Y=经济舱, W=高级经济舱, C=商务舱, F=头等舱)
- 退改摘要（`rule.refund` / `rule.change` 的 boolean）
- 行李额（查 `baggageList[]` 中 `carryBaggageId` / `checkBaggageId` 对应条目）

### 3.3 用户选择价格方案

**只有**用户真正点击了舱位卡片（消息为 `用户已提交 FLIGHT_RESULT 卡片：{...selectedCabin: ...}`）后才能进入此步骤。

用户点击后，消息包含 `selectedCabin.priceId`，将其存入：

| 上下文变量 | 值 |
| :--- | :--- |
| `ctx.selectedPriceId` | `user_input.selectedCabin.priceId` |
| `ctx.selectedCabClass` | `user_input.selectedCabin.cabinName` |
| `ctx.originalTotalPrice` | `user_input.selectedCabin.totalPrice` |

**不要**用消息中 `[选择参数: priceId=...]` 里的 `priceId`（那是前端 hint，是最低价）。
**只**用 `selectedCabin.priceId`。

**状态转换**: `GROUP_SELECTED → PRICE_SELECTED`

接下来按 Rule 10 的完整流程：getMineBasicData + findPassenger → 检查信息 → 缺则等 PASSENGER_FORM → 完整则 intRule+intPricing+intPolicy。

### 3.4 退改规则查询（可选）

用户询问退改规则时，调用：

**API**: `POST /air/international/intRule`

**前置条件**：
- `ctx.serialNumber` 非空
- `ctx.selectedPriceId` 非空
- `pricingId`：初次无此值，传 `ctx.selectedPriceId`（intRule 的 pricingId 参数可复用 priceId）

```json
{
  "serialNumber": "<ctx.serialNumber>",
  "priceId": "<ctx.selectedPriceId>",
  "pricingId": "<ctx.selectedPriceId>"
}
```

**返回处理**：
- 展示 `refundRule.beforeDeparture` / `afterDeparture` 的 `allowed` + `amount`
- 展示 `changeRule` 同结构
- 展示 `cabList[].baggageList[]` 行李规则

触发标准 AGUI：`PLAIN_TEXT`

**状态转换**: `PRICE_SELECTED → RULE_CHECKED`

### 3.5 往返/多程处理

对于往返行程（`tripList` 长度 == 2）：
- 去程 (`io=0`) 和回程 (`io=1`) 在同一 `groupList` 中绑定
- 用户选择去程后，回程自动绑定，无需二次选择
- 价格为去程+回程合计

对于多程（`tripList` 长度 > 2）：
- 按相同规则，所有程在同一 group 中绑定

## 舱位选择规则（绝对禁止代选）

Hub 在用户选航班后**自动发送舱位选择卡片**（`AIR_DOMESTIC_CABIN_LIST` / `CABIN_LIST`），消息中会包含：
> "已发送舱位选择卡片，请等待用户在卡片中点击选择舱位，不要自行决定"

收到此消息后**必须立即停止**，输出一句"请在舱位卡片中选择舱位"，等待用户点击。

**关键识别**：
- 用户消息含 `[选择参数: groupId=..., priceId=...]` → 这只是前端发卡片的 hint 参数。`priceId` 是前端自动选的最低价格方案，**不**代表用户意愿。
- 用户消息含"已发送舱位选择卡片，请等待..." → **立即停止**，不调任何 API。
- **唯一可自动继续**：消息为 `用户已提交 FLIGHT_RESULT 卡片：{...selectedCabin: ...}`（用户真正点击了舱位卡片）。

**禁止行为**：
- ❌ 看到价格方案列表就用第一个 priceId 调 intPricing（等于代选最低价）
- ❌ 看到"请帮我选择方案并继续下一步"就继续（旧版消息，新版已改为等待指令）
- ❌ 跳过舱位选择直接调用 intRule/intPricing

## 错误处理

| 场景 | 行为 |
|---|---|
| 用户选择序号越界 | 提示有效范围 |
| intRule 超时 | 跳过退改展示，告知用户"退改规则暂不可查，下单前可在确认页查看" |
