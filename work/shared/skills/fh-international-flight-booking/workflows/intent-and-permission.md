# Workflow: Intent & Permission (Step 1)

> 加载时机：进入 INIT 阶段时加载本文件。

## 前置条件

无。本步骤是整个流程的起点。

## 执行步骤

### 1.1 意图识别

从用户消息中判断：

| 判断条件 | 结果 |
|---|---|
| 明确提到国际机票/出境/跨国航班 | 进入 1.2 |
| 提到机票但未区分国内/国际 | 询问："您需要国内机票还是国际机票？" |
| 未提到机票 | 非本 skill 范围，不触发 |

### 1.2 行程/日期明确性

| 判断条件 | 结果 |
|---|---|
| 出发城市 + 到达城市 + 出发日期 均已提供 | 进入 1.3 |
| 部分缺失 | 发 `OD_INPUT` 卡片，收集缺失字段 |
| 全部缺失 | 发 `OD_INPUT` 卡片，收集所有字段 |

### 1.3 权限校验

并行调用两个 API（必须同时成功才能继续）：

**API 1**: `POST /air/customer/getClientBasicData`

```json
{
  "productType": "INTERNATIONAL"
}
```

> **必须传 `productType=INTERNATIONAL`**。Hub 端的 `http_client.py` 在 body 为 `{}` 或缺 `productType` 时会自动补 `productType=INTERNATIONAL`，但主动传更稳。**不要**传 `{}`—— fh-travel BFF 可能返回 `TMS_1002 / 网络异常`。

**API 2**: `POST /customer/mine/getMineBasicData`

```json
{}
```

**判断逻辑**：

| 条件 | 结果 |
|---|---|
| `getClientBasicData.data.showInternational == false` | `CANNOT_ORDER`: "您的企业暂未开通国际机票服务" |
| `getClientBasicData.errorCode != "0"` | `CANNOT_ORDER`: "客户配置获取失败" |
| `getMineBasicData.errorCode != "0"` | `CANNOT_ORDER`: "用户信息获取失败" |
| 均成功 | 进入 Step 2 |

### 1.4 上下文存储

权限校验通过后，将以下字段存入会话上下文：

| 上下文变量 | 来源 |
|---|---|
| `ctx.clientId` | `getClientBasicData` 未直接返回 clientId，使用 `getMineBasicData.data.companyId` |
| `ctx.depId` | `getMineBasicData.data.depId` |
| `ctx.userCode` | `getMineBasicData.data.userCode` |
| `ctx.userName` | `getMineBasicData.data.userName` |
| `ctx.oaLogin` | `getClientBasicData.data.oaLogin` |
| `ctx.showInternational` | `getClientBasicData.data.showInternational` |
| `ctx.applicationType` | `getClientBasicData.data.applicationType` |
| `ctx.costCenter` | `getClientBasicData.data.costCenter` |
| `ctx.onlyInternationalAirOrderSelfChannel` | `getClientBasicData.data.onlyInternationalAirOrderSelfChannel` |

## 错误处理

| 场景 | 行为 |
|---|---|
| Token 缺失 | `CANNOT_ORDER`: "登录状态已失效" |
| API 超时 | `CANNOT_ORDER`: "客户配置服务暂时无法连接，请稍后重试" |
| API 网络错误 | `CANNOT_ORDER`: "网络不可达，请稍后重试" |
