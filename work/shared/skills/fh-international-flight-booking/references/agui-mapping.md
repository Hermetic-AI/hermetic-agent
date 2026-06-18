# AGUI Mapping for International Flights

> 加载时机：首次渲染国际机票卡片前加载本文件。

## 核心原则

**严格复用 AGUI v2 协议已有 basicType，不引入新组件名。**
国际机票数据结构与国内差异较大时，使用 `PLAIN_TEXT` 展示结构化 Markdown 文本。
当国际机票字段可直接映射到 `AIR_DOMESTIC_ORDER_SUMMARY` 等已有组件时，复用之。

## basicType 使用策略

| 业务场景 | 使用的 basicType | 理由 |
|---|---|---|
| 航班列表 | `PLAIN_TEXT` | 国际航班数据结构（groupList+priceList）与 AIR_DOMESTIC_FLIGHT_LIST（flightList+cabins）不同，无法直接映射 |
| 签证提醒 | `PLAIN_TEXT` | 纯文本提示 |
| 价格/舱位选择 | `PLAIN_TEXT` | 国际以 priceId 粒度展示（含行程组合+舱等+退改摘要），与 AIR_DOMESTIC_CABIN_LIST 结构不同 |
| 退改规则 | `PLAIN_TEXT` | 规则结构为嵌套对象，不符合已有组件 |
| 价格变动 | `PLAIN_TEXT` | 核价前后对比文本 |
| 差标违反 | `PLAIN_TEXT` + `BUTTON` | 违反项列表 + 用户决策按钮 |
| 订单确认 | `AIR_DOMESTIC_ORDER_SUMMARY` + `BUTTON` | 国际订单摘要字段与国内兼容 |
| 通用提示 | `PLAIN_TEXT` | 默认回退 |

## 订单确认复用 AIR_DOMESTIC_ORDER_SUMMARY

国际机票 ORDER_CONFIRM 场景可复用 `AIR_DOMESTIC_ORDER_SUMMARY`，字段映射：

| ORDER_SUMMARY 字段 | 国际 saveOrder 映射来源 |
|---|---|
| `actionType` | 固定 `"SUBMIT_ORDER"` |
| `orderId` | `saveOrder` 返回 `data.orderList[0].orderId` |
| `orderNo` | `saveOrder` 返回 `data.orderList[0].subOrderId` |
| `orderStatus` | 固定 `"PENDING_PAY"` |
| `totalPrice` | `intPricing` 返回核价后总价 |
| `passengerCount` | 用户选择乘机人数 |
| `createTime` | 当前 ISO 8601 时间 |
| `pnr` | `saveOrder` 返回 `data.pnr` |
| `idempotencyKey` | 本地生成 UUID |
| `message` | 中文提示文案 |
| `submitPayload` | 按 saveOrder 请求体格式组装 |
| `flightSummary` | 从 intShopping 的 tripList + flightList 提取首段 |
| `passengerLines` | `"姓名(证件:证件号)"` 格式 |
| `tripTypeLabel` | `"单程"` / `"往返"` / `"多程"` |

### FlightSummary 映射

| FlightSummary 字段 | 国际 intShopping 映射 |
|---|---|
| `depDate` | `groupList[].tripList[io=0].flightList[0].flyDate` 取日期部分 |
| `depTime` | `groupList[].tripList[io=0].flightList[0].flyDate` 取时间部分 |
| `arrTime` | `groupList[].tripList[io=0].flightList[-1].arrDate` 取时间部分 |
| `depAirportName` | 查 `cityList[]` 中 `fromPort` 对应的 `airPortName` |
| `arrAirportName` | 查 `cityList[]` 中 `toPort` 对应的 `airPortName` |
| `airlineName` | 查 `airwayList[]` 中 `airId` 对应的 `companyName` |
| `flightNo` | `groupList[].tripList[0].flightList[0].flightId` |
| `depCityName` | 查 `cityList[]` 中 fromPort 的 `cityName` |
| `arrCityName` | 查 `cityList[]` 中 toPort 的 `cityName` |

## PLAIN_TEXT 航班列表 Markdown 模板

```markdown
共查询到 {totalCount} 个航班组合，按总价升序排列：

| 序号 | 航司 | 去程航班 | 去程时间 | 飞行时长 | 经停 | 中转 | 总价(含税) | 舱等 |
|------|------|----------|----------|----------|------|------|------------|------|
| 1    | CZ   | CZ301    | 08:30-12:45 | 7h15m | 0 | - | ¥3,200 | 经济舱 |
| 2    | CA   | CA933    | 01:30-05:45 | 10h15m | 0 | - | ¥4,100 | 经济舱 |

请回复序号选择航班组合，或告诉我您的偏好（如"最便宜"、"直飞"、"商务舱"）。
```

## PLAIN_TEXT 价格列表 Markdown 模板

```markdown
航班组合 {groupId} 的可选价格方案：

| 序号 | priceId | 出票航司 | 票面价 | 税费 | 服务费 | 总价 | 舱等 | 退 | 改 | 行李 |
|------|---------|----------|--------|------|--------|------|------|----|----|------|
| 1    | P001    | CZ       | 2800   | 400  | 0      | 3200 | Y    | ✓ | ✓ | 2×23kg |
| 2    | P002    | CZ       | 5600   | 400  | 0      | 6000 | C    | ✓ | ✓ | 2×32kg |

请回复序号选择价格方案。
```
