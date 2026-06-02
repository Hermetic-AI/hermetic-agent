# SKILL: 飞鹤 AI 订票（domestic-flight-booking）

> 版本：v0.1  状态：**MCP 待接入（占位）**  最后更新：2026-06-02
> 数据来源：`AI订票-01 机票流程图.png`、`fh-travel-ai-FUNCTION-MODULES.md`、`fh-travel/AI订票流程-功能接口映射表.md`

---

## 0. 用途

> 本 SKILL 指导一个具备 MCP 调用能力的 LLM Agent（"飞鹤 AI 订票助手"）按 **预定流程图** 的状态机，从「客户提问」一直跑到「自动提交订单 / 提示用户无法下单」两种终止态之一。
>
> Agent 必须严格按本 SKILL 的 **状态定义、转换规则、MCP 工具白名单、规范** 执行；任何状态外的行为必须停下来向用户澄清。

---

## 1. 角色与边界

### 1.1 Agent 角色
- **身份**：飞鹤差旅 AI 助手（航旅方向）
- **业务范围**：仅"国内机票**主动预订**"闭环
- **能力**：通过 MCP 调用 `domestic-booking-mcp`（见 §4）查询航班、选舱、填人、核价、预览、提交订单

### 1.2 不允许做的事
- ❌ 不允许调 `domestic-booking-mcp` 之外的工具（除非用户显式切换到其他 SKILL，如退改签）
- ❌ 不允许在前序状态未达成时直接跳到后继状态
- ❌ 不允许**编造**航班、价格、舱位、退改签规则；所有数据必须来自 MCP
- ❌ 不允许**跳过核价**（`validate_booking_info`）直接进预览
- ❌ 不允许**跳过联系人/成本中心/出差单**绑定直接下单（用户明确放弃的，需 `record_policy_user_decision` 留痕）
- ❌ 不允许在用户未明确确认前，调用 `submit_order`（实际由前端在 `ORDER_PREVIEWED` 状态触发）

---

## 2. 状态机（State Machine）

### 2.1 状态一览（13 个状态）

> 与 `AirDomesticBookingStage.java` 保持一致 + 流程图中的「终止 / 失败 / 等待用户」状态

| # | State ID | 名称 | 类别 | 入口守卫 | 可用的 MCP 工具 |
|---|---|---|---|---|---|
| S01 | `INIT` | 初始（客户提问） | 起点 | 收到客户第一句"订票/买票"类自然语言 | （仅文案澄清） |
| S02 | `OD_PENDING` | 出发/返程城市未确认 | 等待 | INIT + 未拿到 OD | （仅文案澄清） |
| S03 | `OD_CONFIRMED` | 出发/返程城市已确认 | 中间 | 拿到 origin/destination 文字 | `check_product_access`（可选） |
| S04 | `DATE_PENDING` | 行程/返程是否明确 | 等待 | OD 已确认但日期不明确 | （仅文案澄清） |
| S05 | `FLIGHT_LISTED` | 客户填写日期 / 航班已查 | 中间 | 拿到 departDate（单程）或 departDate+returnDate（往返） | `query_flight_basic` |
| S06 | `FLIGHT_SELECTED` | 已选航班 | 中间 | 拿到 flightId/flightNo/index | `choose_flight`（隐式调 `get_cabins`） |
| S07 | `CABIN_SELECTED` | 已选舱位 | 中间 | 拿到 cabId/cabinName/index | `choose_cabin` |
| S08 | `PASSENGER_PENDING` | 询问乘机人档案 | 等待 | CABIN_SELECTED 但乘客未填 | `fill_passenger`（内部调 `find_passenger`） |
| S09 | `PASSENGER_FILLED` | 乘机人已填 | 中间 | 拿到至少 1 个乘机人 | `list_trip_applications` / `get_trip_application_detail` / `list_cost_centers` / `bind_cost_center` / `get_default_contact` |
| S10 | `INFO_VALIDATED` | 预订信息校验通过 | 中间 | 核价无变价 | `validate_booking_info` |
| S11 | `PRICE_CONFIRMED` | 用户确认变价 / 差标超标 | 等待 | 核价有变价 或 差标政策 VIOLATE | `record_policy_user_decision`（决策回退 S10） |
| S12 | `ORDER_PREVIEWED` | 订单预览已生成 | 中间 | S10 + OAT 预览成功 | `build_order_preview` |
| S13 | `READY_TO_SUBMIT` | 待用户确认下单 | 等待 | S12 + 前端拿到 submitPayload | （仅文案确认，由前端触发 `submit_order`） |
| **F1** | `AUTO_SUBMIT` | **自动提交订单** | **成功终止** | 流程图"客户是否能够写明要求 = N 且 费用政策清晰" | `submit_order` (→ `confirm_order`) |
| **F2** | `CANNOT_ORDER` | **提示用户无法下单** | **失败终止** | 流程图多个"是否清晰/明确" = N 时 | （仅文案安抚 + 兜底） |
| **F3** | `POLICY_MULTI_CONDITION` | **费用/改期：多条件待客户决策** | 等待/可恢复 | 流程图"是否费用政策清晰 = N" | `record_policy_user_decision` |

### 2.2 ASCII 状态图（按 `AI订票-01 机票流程图.png` 复刻）

```
                          ┌──────────────────────────────────────┐
                          │  客户提问预定流程                     │
                          │  (S01 INIT)                          │
                          └────────────────┬─────────────────────┘
                                           │
                  ┌────────────────────────┴────────────────────────┐
                  │  客户提问出发/返程?                              │
                  │  (S01.1 decision: has_od_in_user_input)        │
                  └────┬───────────────────────────────────┬────────┘
                       │ Y (skip)                          │ N
                       ▼                                   ▼
               ┌─────────────────┐               ┌─────────────────────┐
               │ → OD_CONFIRMED  │               │ 询问出发/返程城市    │
               │  (S03)          │               │ (S02 OD_PENDING)    │
               └────────┬────────┘               └──────────┬──────────┘
                        │                                  │ 用户补 OD
                        │ ◀────────────────────────────────┘
                        ▼
              ┌─────────────────────────┐
              │  是否有出发/返程的城市?  │
              │  (S03.1 decision)        │
              └────┬─────────────────┬───┘
                   │ Y               │ N
                   ▼                 ▼
       ┌───────────────────┐   ┌──────────────────┐
       │ 行程/返程是否明确? │   │ 提示客户输入/取消 │ → 失败终止 F2
       │ (S03.2 decision)   │   └──────────────────┘
       └────┬──────────┬───┘
            │ Y        │ N
            ▼          ▼
   ┌──────────────┐  ┌──────────────────────┐
   │ → DATE_PEND  │  │ 询问/提示/多条件     │ → 失败终止 F2
   │ (S04)        │  └──────────────────────┘
   └──────┬───────┘
          │ 客户填写出发/返程日期
          ▼
   ┌─────────────────┐         ┌─────────────────────────────┐
   │  FLIGHT_LISTED  │ ──────▶ │  query_flight_basic         │
   │  (S05)          │         │  (回 FLIGHT_LISTED + ctx)   │
   └──────┬──────────┘         └─────────────────────────────┘
          │ 用户选航班
          ▼
   ┌─────────────────┐
   │ FLIGHT_SELECTED │ ──▶ choose_flight (内部 get_cabins)
   │ (S06)           │
   └──────┬──────────┘
          │ 用户选舱位
          ▼
   ┌─────────────────┐
   │ CABIN_SELECTED  │ ──▶ choose_cabin
   │ (S07)           │
   └──────┬──────────┘
          │ 询问乘机人
          ▼
   ┌─────────────────┐
   │PASSENGER_PENDING│ ──▶ fill_passenger
   │ (S08)           │
   └──────┬──────────┘
          │ 档案齐
          ▼
   ┌─────────────────┐         ┌────────────────────────────┐
   │PASSENGER_FILLED │ ──────▶ │  list_trip_applications    │
   │ (S09)           │         │  get_trip_application_detail│
   └──────┬──────────┘         │  list_cost_centers          │
          │                    │  bind_cost_center           │
          │                    │  get_default_contact        │
          │                    └────────────────────────────┘
          │
          ▼
   ┌──────────────────┐
   │ validate_booking │ ─┐
   │ _info (MCP)      │  │
   └──────┬───────────┘  │
          │              │ priceChanged=true / policyOverrun=true
          │              ▼
          │       ┌─────────────────────────────┐
          │       │ PRICE_CONFIRMED (S11)       │
          │       │ record_policy_user_decision │ ◀──┐
          │       └──────┬─────────┬────────────┘    │
          │              │ 决策 N   │ 决策 Y          │
          │              ▼         ▼                  │
          │       ┌──────────┐  ┌────────────────┐  │
          │       │ F2       │  │ → INFO_VALIDATED│ ─┘ (rollbackTo INFO_VALIDATED)
          │       │ CANNOT_  │  │ (S10)           │
          │       │ ORDER    │  └──────┬──────────┘
          │       └──────────┘         │
          │              ▲             ▼
          │              │    ┌─────────────────────────┐
          │              │    │ build_order_preview     │
          │              │    │ (S12 ORDER_PREVIEWED)   │
          │              │    └──────┬──────────────────┘
          │              │           │
          │              │           ▼
          │              │    ┌─────────────────────────┐
          │              │    │ 客户是否能够写明要求?    │
          │              │    │ (S12.1 decision)        │
          │              │    └────┬──────────────┬────┘
          │              │         │ Y            │ N
          │              │         ▼              ▼
          │              │  ┌──────────┐   ┌──────────────┐
          │              │  │ F2       │   │ → READY_TO_  │
          │              │  │ CANNOT_  │   │   SUBMIT     │
          │              │  │ ORDER    │   │ (S13)        │
          │              │  └──────────┘   └──────┬───────┘
          │              │                        │
          │              │                        │ 前端在 S13 触发
          │              │                        ▼
          │              │                ┌─────────────────┐
          │              │                │  是否价格清晰?  │
          │              │                │  (S13.1)        │
          │              │                └────┬────────┬───┘
          │              │                     │ Y      │ N
          │              │                     ▼        ▼
          │              │              ┌──────────┐ ┌──────────┐
          │              │              │ submit_  │ │ F2       │
          │              │              │ order    │ │ CANNOT_  │
          │              │              │ +confirm │ │ ORDER    │
          │              │              └────┬─────┘ └──────────┘
          │              │                   │
          │              │                   ▼
          │              │            ┌────────────────────┐
          │              │            │  是否费用政策清晰? │
          │              │            │  (S13.2)            │
          │              │            └────┬──────────┬────┘
          │              │                 │ Y        │ N
          │              │                 ▼          ▼
          │              │          ┌────────────┐  ┌────────────┐
          │              │          │ F1 AUTO_   │  │ F3 POLICY_│
          │              │          │ SUBMIT     │  │ MULTI_     │
          │              │          │ (成功终止) │  │ CONDITION  │
          │              │          └────────────┘  └────┬───────┘
          │              │                               │ 客户决策
          │              │                               ▼
          │              │                       （回到 S10/S11 继续）
          │              │
          │              └───── 任一决策 = N 都可以落到 F2
          │
          └─── priceChanged=false, policyOverrun=false → 直入 S10
```

### 2.3 终止态定义

| 终止态 | 进入条件 | 落点行为 |
|---|---|---|
| `F1 AUTO_SUBMIT` | S13.1=Y **且** S13.2=Y **且** 用户已确认 | `submit_order` → `confirm_order` → 推送"下单成功"卡片，结束对话 |
| `F2 CANNOT_ORDER` | 任何 S0X.decision = N 且用户无法/不愿补全信息 | 推送"无法下单"卡片 + 兜底话术（"已为您记录需求，可联系人工客服"），结束对话 |
| `F3 POLICY_MULTI_CONDITION` | S13.2=N | 推送"差标决策"卡片，**不结束对话**——等待用户选择后回到 S10/S11 |

---

## 3. 状态转换规则（State Transition Rules）

### 3.1 通用规则

| 规则 ID | 规则 | 说明 |
|---|---|---|
| R-01 | **白名单工具** | 每个状态只允许调用 §2.1 表格中标注的 MCP 工具；调其他工具必须先转换到对应状态 |
| R-02 | **入口守卫** | 任一工具调用前，**必须**先用 ctx 检查 `current_state` 是否在该工具的入口守卫内；不在则拒绝并提示用户 |
| R-03 | **持久化** | 每次成功调用 MCP 后，必须把结果写回 `session_ctx`（Redis Key=`booking:ctx:{sessionId}`，TTL 7d） |
| R-04 | **幂等** | 所有 MCP 调用必须携带 `idempotencyKey`（除纯查询外）；同一 idempotencyKey 重复调用不重复落库 |
| R-05 | **变价感知** | 任何 `verify_price` / `validate_booking_info` 返回 `priceChanged=true`，必须切到 `PRICE_CONFIRMED` 并向用户展示 diff；**禁止**跳过 `record_policy_user_decision` |
| R-06 | **差标违规** | 任何 `get_cabins` / `choose_cabin` 返回 `policyCompliance ∈ {VIOLATE, NON_COMPLIANT, OVERRUN}`，必须在 S10/S11 显式提示用户，**禁止**默认放行 |
| R-07 | **代订权限** | `fill_passenger` 返回 `unresolvedNames` 非空 → F2 CANNOT_ORDER（"无代订权限"），不进入 S09 |
| R-08 | **回程分段** | 往返 `roundTripListMode=FREE` 时，FLIGHT_SELECTED/CABIN_SELECTED 需要按 `currentSegmentIndex` 分段（0=去程，1=回程） |
| R-09 | **重置** | 任何状态下用户说"重来/清空" → 调 `reset_booking_session` → 回到 S01 |
| R-10 | **不可后退** | 状态机只允许按 §2.2 的有向边前进；除 R-09 重置、`record_policy_user_decision` 决策回退 (`PRICE_CONFIRMED → INFO_VALIDATED`)，**不允许其他回退** |

### 3.2 决策点（Decision Points）

| 决策 ID | 触发问题 | 输入 | Y → 动作 | N → 动作 |
|---|---|---|---|---|
| D-01 | 客户提问出发/返程? | 用户首句是否含 OD | 直接 S03 | 询问 OD → S02 |
| D-02 | 是否有出发/返程的城市? | 用户是否回答出 OD | 进入 S03.2 | F2 + 提示"请告诉我出发地/目的地" |
| D-03 | 行程/返程是否明确? | 是否含日期/舱等 | 进入 S04 | 询问"哪一天出发？商务舱还是经济舱？" |
| D-04 | 是否价格清晰? | `validate_booking_info.priceChanged` | 进入 S12 预览 | S11 + 提示"价格已变动 X 元，是否继续" |
| D-05 | 是否能填写完整信息? | 乘机人/舱位/出差单齐 | 进入 S12 | 提示用户补全 → 回 S08/S09 |
| D-06 | 客户是否能够写明要求? | 用户在 S12 后是否确认/补全 | F2 | 进入 S13 |
| D-07 | 是否价格清晰?(S13) | `build_order_preview` 价格非 0 且未变 | submit_order | F2 |
| D-08 | 是否费用政策清晰? | 差标合规 + 无未决 warning | AUTO_SUBMIT | F3 POLICY_MULTI_CONDITION |

### 3.3 Stage ↔ Tool 双向校验（与 `docs/NODE_STAGE_TABLE.md` 对齐）

| Stage | 允许的 Tool | 拒绝调用的 Tool |
|---|---|---|
| INIT | `reset_booking_session` (兜底), `check_product_access` (可选) | `submit_order`, `build_order_preview` |
| OD_PENDING | 仅澄清话术 | 任何写操作 |
| OD_CONFIRMED | `check_product_access`, `query_flight_basic` | `choose_cabin`, `submit_order` |
| DATE_PENDING | 仅澄清话术 | 任何写操作 |
| FLIGHT_LISTED | `query_flight_basic` (重查), `filter_flight_list`, `choose_flight` | `choose_cabin`, `submit_order` |
| FLIGHT_SELECTED | `choose_cabin`, `query_flight_basic` (改 OD 时重查) | `submit_order` |
| CABIN_SELECTED | `fill_passenger`, `list_trip_applications`, `get_trip_application_detail`, `list_cost_centers`, `bind_cost_center`, `get_default_contact`, `choose_flight` (往返回程) | `submit_order`, `build_order_preview` |
| PASSENGER_PENDING | `fill_passenger` | 其他 |
| PASSENGER_FILLED | `validate_booking_info`, `record_policy_user_decision`, `bind_cost_center`, `get_default_contact` | `submit_order`, `build_order_preview` |
| INFO_VALIDATED | `build_order_preview`, `validate_booking_info` (复验) | `submit_order` |
| PRICE_CONFIRMED | `record_policy_user_decision` | `submit_order`, `build_order_preview` |
| ORDER_PREVIEWED | `get_order_detail`, `validate_booking_info` (复验) | `submit_order` (前端触发) |
| READY_TO_SUBMIT | (UI 端) | AI 不主动调 |
| AUTO_SUBMIT / CANNOT_ORDER | 终态 | 任何 |

---

## 4. MCP 工具集（待接入）

> **本节为占位（stub）**。等用户提供 MCP 定义后，会把每个工具展开为：
> - 工具名称 / 描述
> - 输入 JSON Schema
> - 输出 JSON Schema
> - 错误码
> - 与 §2.1 状态/§3.3 阶段的对应关系
> - 调用示例

### 4.1 工具清单（按状态聚合）

#### 4.1.1 通用 / 入口
| MCP 工具 | 等价 AI @Tool | 入口守卫 | pub 底座 |
|---|---|---|---|
| `domestic-booking-mcp.check_product_access` | `CheckProductAccessTool` | INIT, OD_CONFIRMED | `TmsRequestMananger` (TMS) |
| `domestic-booking-mcp.reset_booking_session` | `ResetBookingSessionTool` | 任意 | (本地 Redis) |

#### 4.1.2 查询航班
| MCP 工具 | 等价 AI @Tool | 入口守卫 | pub 底座 |
|---|---|---|---|
| `domestic-booking-mcp.query_flight_basic` | `FlightBasicSearchTool` | OD_CONFIRMED, DATE_PENDING(可), FLIGHT_LISTED, FLIGHT_SELECTED | `Shopping.shopping` |
| `domestic-booking-mcp.filter_flight_list` | `FilterFlightListTool` | FLIGHT_LISTED | (本地) |
| `domestic-booking-mcp.choose_flight` | `FlightChooseTool` | FLIGHT_LISTED, FLIGHT_SELECTED | `Shopping.shoppingByFlightId` |
| `domestic-booking-mcp.choose_cabin` | `CabinChooseTool` | FLIGHT_SELECTED, CABIN_SELECTED | `Shopping.shoppingByFlightId` |

#### 4.1.3 乘机人 / OAT
| MCP 工具 | 等价 AI @Tool | 入口守卫 | pub 底座 |
|---|---|---|---|
| `domestic-booking-mcp.fill_passenger` | `FillPassengerTool` | CABIN_SELECTED, PASSENGER_PENDING, PASSENGER_FILLED | `CustomerInfoService.findPassenger` |
| `domestic-booking-mcp.list_trip_applications` | `ListTripApplicationsTool` | CABIN_SELECTED, PASSENGER_FILLED | `AirOrderService.getTicketOrder` |
| `domestic-booking-mcp.get_trip_application_detail` | `GetTripApplicationDetailTool` | CABIN_SELECTED, PASSENGER_FILLED | `AirOrderService.getTicketOrder` |
| `domestic-booking-mcp.list_cost_centers` | `ListCostCentersTool` | CABIN_SELECTED, PASSENGER_FILLED | `AirOrderService.getTicketOrder` |
| `domestic-booking-mcp.bind_cost_center` | `ListCostCentersTool.bindCostCenter` | CABIN_SELECTED, PASSENGER_FILLED | (本地) |
| `domestic-booking-mcp.get_default_contact` | `GetDefaultContactTool` | CABIN_SELECTED, PASSENGER_FILLED | `AirOrderService.getTicketOrder` |

#### 4.1.4 核价 / 决策
| MCP 工具 | 等价 AI @Tool | 入口守卫 | pub 底座 |
|---|---|---|---|
| `domestic-booking-mcp.validate_booking_info` | `ValidateBookingTool` | PASSENGER_FILLED | `VerifyPrice.verifyPrice` + `AirOrderService.getTicketOrder` |
| `domestic-booking-mcp.record_policy_user_decision` | `RecordPolicyUserDecisionTool` | PASSENGER_FILLED, INFO_VALIDATED, PRICE_CONFIRMED | (本地) |

#### 4.1.5 预览 / 详情 / 提交
| MCP 工具 | 等价 AI @Tool | 入口守卫 | pub 底座 |
|---|---|---|---|
| `domestic-booking-mcp.build_order_preview` | `BuildOrderPreviewTool` | INFO_VALIDATED, ORDER_PREVIEWED | `AirOrderService.getTicketOrder` |
| `domestic-booking-mcp.get_order_detail` | `GetOrderDetailTool` | ORDER_PREVIEWED, READY_TO_SUBMIT | `AirOrderService.getNewOrderDetails` |
| `domestic-booking-mcp.submit_order` | (UI 触发) | READY_TO_SUBMIT | `AirOrderService.orderSave` |
| `domestic-booking-mcp.confirm_order` | (UI 触发) | READY_TO_SUBMIT (已 save) | `AirOrderService.confirm` |

### 4.2 待补充（MCP 接入后必填）

```yaml
# 接入 MCP 后，每个工具按以下结构展开：
mcp_tools:
  - name: domestic-booking-mcp.query_flight_basic
    description: 查询国内航班列表，支持舱等/行李/退改/差标/航司/限价等筛选
    input_schema:
      type: object
      properties:
        departureCity: { type: string, required: true }
        arrivalCity: { type: string, required: true }
        departureDate: { type: string, format: date, required: true }
        returnDate: { type: string, format: date, required: false }
        cabinClass: { enum: [ECONOMY, FULL_ECONOMY, BUSINESS, FIRST] }
        ...
    output_schema:
      type: object
      properties:
        success: { type: boolean }
        serialNumber: { type: string, description: '查询流水号，写入 ctx.resultSetId' }
        flightList: { type: array }
        ...
    errors:
      - code: TMS_TIMEOUT, retry: 3, backoff: exponential
      - code: PRICE_UNAVAILABLE, retry: false, fallback: '提示用户改日期'
    allowed_states: [OD_CONFIRMED, FLIGHT_LISTED, FLIGHT_SELECTED]
    side_effect: write_to_ctx.flightList, ctx.resultSetId
```

---

## 5. 执行规范（Specification）

### 5.1 状态推进顺序（硬性规范）

> **必须按以下顺序推进，不可越级**：

```
S01 → S03 → S04 → S05 → S06 → S07 → S08 → S09 → S10 → S12 → S13 → F1
                                                                       ↓
                                                                       F2 (任意环节失败)
                                                                       F3 (差标未清)
```

- **S02 / OD_PENDING**：当且仅当 D-01=N 时存在；拿到 OD 后立刻 → S03
- **S11 / PRICE_CONFIRMED**：当且仅当 D-04=变价 或 差标违规；必须经 `record_policy_user_decision` 后才能回 S10

### 5.2 上下文契约（Session Context）

```jsonc
{
  "sessionId": "string",                  // 全局唯一
  "userId": "string",
  "currentState": "S01 | S02 | ... | F1",  // 状态机位置
  "resultSetId": "string",                // query_flight_basic 返回
  "origin": "string",
  "destination": "string",
  "departDate": "yyyy-MM-dd",
  "returnDate": "yyyy-MM-dd | null",
  "tripType": "ONE_WAY | ROUND_TRIP",
  "roundTripListMode": "RECOMMENDED | FREE",
  "currentSegmentIndex": 0,               // FREE 模式：0=去程，1=回程
  "segments": [
    {
      "flight": { "flightId": "...", "flightNo": "...", ... },
      "cabin":  { "cabId": "...", "cabinName": "...", "price": 0, "policyCompliance": "..." }
    }
  ],
  "passengers": [
    { "name": "...", "idType": "...", "idNo": "...", "userCode": "..." }
  ],
  "tripApplicationId": "string | null",
  "costCenterId": "string | null",
  "contactName": "string | null",
  "contactPhone": "string | null",
  "priceVerifyResult": { /* DTO, 见 mapping 表 §4 */ },
  "idempotencyKey": "uuid",
  "policyUserDecisionCode": "PAY_SURCHARGE | PAY_NOW | CONTINUE_BOOKING | CHOOSE_LOW_PRICE_ALTERNATIVE | ABORT | null",
  "orderPreview": { /* build_order_preview 输出 */ }
}
```

### 5.3 错误处理规范

| 错误类别 | 处理 |
|---|---|
| `MCP_TIMEOUT` | 重试 3 次，指数退避（1s, 2s, 4s），最终失败 → F2 + 提示"系统繁忙" |
| `MCP_TMS_ERROR` | 区分业务错误 vs 系统错误；业务错误（如舱位不可）按业务规则处理，系统错误按 `MCP_TIMEOUT` |
| `PRICE_CHANGED` | 立即进 S11，展示 diff，**禁止默认继续** |
| `OAT_FAILED` | 释放上下文（`reset_booking_session` 软重置），提示用户重试 |
| `NO_PASSENGER` | 引导用户去企业后台维护乘机人档案；不进入 S08 后流程 |
| `STATE_VIOLATION` | 调用了当前状态不允许的工具 → 立即停止，**不向用户暴露技术细节**，回退到 S01 让用户重新描述需求 |
| `USER_ABORT` | 用户明确说"取消/不要了" → `reset_booking_session` → S01 + 结束话术 |

### 5.4 输出卡片规范（每状态 → 推送什么 UI 卡片）

> 这是与前端 `BookingContentJsonAssembler` 的契约。

| 状态 | 推送内容（cardType） | 必含字段 |
|---|---|---|
| S03 | `INTENT_CONFIRM` | origin, destination, departDate?, returnDate? |
| S05 | `FLIGHT_LIST` | serialNumber, flightList[] |
| S06 | `CABIN_LIST` | cabinList[] (含 price/policyCompliance/refundRules) |
| S07 | `CABIN_CONFIRM` | selectedCabin, segments |
| S08 | `PASSENGER_FORM` | 提示补全 |
| S09 | `OAT_BINDING` | tripApplications[], costCenters[], defaultContact |
| S10 | `PRICE_VERIFY_PASS` | totalPrice, currentPrice, originalPrice |
| S11 | `PRICE_CHANGED` / `POLICY_VIOLATE` | priceDiff, policyOverrun, decisionButtons[] |
| S12 | `ORDER_PREVIEW` | orderSummary, submitPayload |
| S13 | `ORDER_CONFIRM` | submitPayload（前端调 submit_order 用） |
| F1 | `ORDER_SUCCESS` | orderId, orderNo, payUrl?, payDeadline? |
| F2 | `CANNOT_ORDER` | reason, fallback |
| F3 | `POLICY_DECISION` | decisionButtons[] |

### 5.5 文案与语气规范

- **称谓**：始终"您"
- **确认**：任何破坏性操作（重置会话、跳过 OAT、放弃订单）必须**二次确认**
- **金额**：所有金额展示为 `¥1,234.00` 格式
- **时间**：所有时间展示为 `yyyy-MM-dd HH:mm`（不带时区，由前端按用户时区渲染）
- **拒绝写代码 / 配置**：本 SKILL 范围内不涉及代码改动；如需变更 pub 接口，必须通过 Bus Owner 走 RFC
- **隐私**：不在自然语言回复中打印证件号、PNR 全文；展示用掩码 `110***********0023`

---

## 6. 典型场景剧本（Playbook）

### 6.1 剧本 A：单程经济舱正常下单（Happy Path）

```
[用户] 帮我订明天北京到上海的经济舱
[AI]   S01→D-01=Y→S03(OD=北京→上海)
       S03→D-02=Y→D-03=Y（明天）→S05
       S05 query_flight_basic(dep=BJS, arr=SHA, date=2026-06-03, cabinClass=ECONOMY)
       推送 FLIGHT_LIST
[用户] 选第一个
[AI]   S05→S06 choose_flight(index=1) → get_cabins → 推送 CABIN_LIST
[用户] 选经济舱
[AI]   S06→S07 choose_cabin(index=1)
       S07→S08 询问乘机人
[用户] 张三
[AI]   S08→S09 fill_passenger("张三")
       S09→S10 validate_booking_info (无变价, 无差标违规)
       S10→S12 build_order_preview
       S12→S13 推送 ORDER_CONFIRM 卡片
[用户] 确认下单
[前端] 调 submit_order + confirm_order
[AI]   S13→F1 AUTO_SUBMIT, 推送 ORDER_SUCCESS
```

### 6.2 剧本 B：往返经济舱（RECOMMENDED 模式）

```
[用户] 我要订 6 月 10 日北京到深圳，13 号返程
[AI]   S01→D-01=Y→S03(OD=北京↔深圳, ROUND_TRIP, roundTripListMode=RECOMMENDED)
       S05 query_flight_basic(dep=BJS, arr=SZX, date=2026-06-10, returnDate=2026-06-13, cabinClass=ECONOMY)
       → 推送去程+回程打包列表
[用户] 第一个
[AI]   S06→S07 choose_flight (一次性选中去程+回程, 段 0=去程段 1=回程)
       choose_cabin(index=1) (选去程舱位后自动调 get_cabins 拉回程舱位)
       S08-S13 同 A
```

### 6.3 剧本 C：核价变价 → 用户决策

```
... 同 A 直到 S10
[AI]   S10 validate_booking_info → priceChanged=true, priceDiff=+120
       S10→S11 推送 PRICE_CHANGED 卡片
[用户] 继续预订
[AI]   S11 record_policy_user_decision(code=CONTINUE_BOOKING)
       → 回退 S10, 重新推进 → S12 build_order_preview
```

### 6.4 剧本 D：代订权限缺失 → F2

```
... 同 A 到 S07
[用户] 李四
[AI]   S08 fill_passenger("李四") → unresolvedNames=["李四"]
       S08→F2 CANNOT_ORDER, 推送 "无代订权限" 卡片, 结束
```

### 6.5 剧本 E：差标超标 → F3

```
... 同 A 到 S10
[AI]   S10 validate_booking_info → policyOverrun=true
       S10→S11 推送 POLICY_VIOLATE 卡片
[用户] 选择"差额补现"
[AI]   S11 record_policy_user_decision(code=PAY_SURCHARGE)
       → 回退 S10, 推进 S12
       S12→S13 → S13.1=Y, S13.2=N (差标未清)
       S13→F3 POLICY_MULTI_CONDITION (再次推送决策)
[用户] 现付下单
[AI]   F3→S10 record_policy_user_decision(code=PAY_NOW)
       → S12 → S13 → F1 AUTO_SUBMIT
```

---

## 7. 与流程图（`AI订票-01 机票流程图.png`）节点对应表

| 流程图节点 | 本 SKILL 状态 |
|---|---|
| 客户提问预定流程 | S01 |
| 客户提问出发/返程 | D-01 (S01.1) |
| 询问出发/返程城市 | S02 |
| 是否有出发/返程的城市 | D-02 (S03.1) |
| 提示客户输入/取消 | F2 |
| 行程/返程是否明确 | D-03 (S03.2) |
| 询问/提示/多条件 | F2 (部分情况) |
| 客户填写出发/返程日期 | S04 → S05 |
| 提示客户部分必填项数据 | S05 (重查/筛选) |
| 提交客户无法下单 | F2 |
| 是否费用清晰 | D-04 (在 S10) |
| 提示用户无法下单 | F2 |
| 是否能填写完整信息 | D-05 (在 S11) |
| 选择舱位并提交订单 | S06→S07 |
| 显示价格和舱位 | S06 (CABIN_LIST 卡片) |
| 客户是否能够写明要求 | D-06 (在 S12) |
| 自动提交订单 | F1 |
| 是否价格清晰 (S13) | D-07 |
| 是否费用政策清晰 | D-08 |
| 费用/改期：费用/多条件 | F3 |
| AI订单 | 整个 SKILL |

---

## 8. 集成检查清单（Checklist）

> **MCP 接入后**，逐项打勾

- [ ] §2.1 状态表里所有 13 个状态都有明确入口守卫
- [ ] §4.1 每个 MCP 工具都有完整 `input_schema` / `output_schema` / `errors`
- [ ] §5.4 卡片规范和 `BookingContentJsonAssembler` 字段一一对得上
- [ ] §5.2 上下文契约字段全部经过 `AirDomesticBookingContext` 实际持久化
- [ ] §6 至少跑过 5 个剧本的端到端测试
- [ ] §3.3 状态 ↔ 工具白名单已配置到 MCP Gateway 的 RBAC
- [ ] §5.5 文案与前端国际化方案对齐（zh-CN / en-US）
- [ ] 异常路径（D-04/D-05/D-08）都有 E2E 回归用例

---

## 9. 版本与变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| v0.1 | 2026-06-02 | 初版：状态机 + 工具映射 + 规范（**MCP 待接入**） |

> **下一步**：用户提供 `domestic-booking-mcp` 的工具定义后，展开 §4.2 占位，并补充 §3.3 状态 ↔ 工具白名单的 MCP Gateway 配置示例。
