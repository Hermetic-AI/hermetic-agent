# Order Validation, Submission, and Completion

Use after `PASSENGER_FILLED` stage. Covers business flow Steps 4–5: policy validation, risk control, info completion, and order creation.

## 1. Validate Booking Info

Precondition: stage `PASSENGER_FILLED` or later.

Call `mcporter_feihe-travel__validateBookingInfo(sessionId)`.

`validateBookingInfo` checks passenger data, OAT fields, travel policy compliance, booking permission, and price consistency in a single call. Do not add separate permission or risk checks; `validateBookingInfo` and `checkProductAccess` (pre-search) together cover all permission and risk scenarios defined in the business flow.

### Outcomes

| Outcome | Action |
|---|---|
| Success / no issues | Proceed to Step 3 (order submission) |
| Missing required fields | Fill fields (Step 2), then validate again |
| Policy overrun (差标违规) | Load `workflows/policy-oat-recovery.md` for policy decision |
| Price change | Load `workflows/policy-oat-recovery.md` for price verification |
| Permission block (出行人数据权限/预订权限) | Report with `CANNOT_ORDER` card (Step 5) |
| Risk control block (最终风控拦截) | Report with `CANNOT_ORDER` card (Step 5) |

### Permission and Risk Blocks

When `validateBookingInfo` returns that the passenger lacks booking permission or a final risk/status check blocks the order, call `ask_user` with `card_type=CANNOT_ORDER` and include `reason` from the MCP response. Common reasons:

- **出行人无预订权限**: the passenger is not authorized to book flights
- **最终风控拦截**: a risk control rule prevents this booking
- **差标不可逾越且无选择余地**: policy violation with no override option

Do not retry or override these blocks. Direct the user to their administrator or travel management system.

## 2. Fill Missing Required Fields

If `validateBookingInfo` reports missing required fields, fill them and validate again.

| Missing Field Type | Card Type | Action |
|---|---|---|
| Passenger fields | `PASSENGER_FORM` | Call `ask_user` with `fields[]` for missing passenger info |
| Trip application | `OAT_BINDING` | Call `mcporter_feihe-travel__listTripApplications` then `ask_user` |
| Cost center | `OAT_BINDING` | Call `mcporter_feihe-travel__listCostCenters` then `ask_user` |
| Contact | `OAT_BINDING` | Call `mcporter_feihe-travel__getDefaultContact` |
| Other fields | `CHAT_FALLBACK` | Ask for the missing info |

After filling, call `mcporter_feihe-travel__validateBookingInfo(sessionId)` again.

## 3. Handle Policy and Price Issues

If `validateBookingInfo` returns policy overrun or price changes, load `workflows/policy-oat-recovery.md` for detailed handling.

After resolving policy decisions (via `mcporter_feihe-travel__recordPolicyUserDecision`) or price acceptance, call `mcporter_feihe-travel__validateBookingInfo(sessionId)` again to re-validate.

Do not proceed to order submission until validation passes without policy or price issues.

## 4. Build Order Preview / Submit Order

**`mcporter_feihe-travel__buildOrderPreview` is the order creation call.** There is no separate submit tool. Calling `buildOrderPreview` creates the order in the backend.

Precondition: stage `INFO_VALIDATED` or `PRICE_CONFIRMED`.

Call `mcporter_feihe-travel__buildOrderPreview(sessionId)`.

### Present Order Preview

Call `ask_user` with `card_type=ORDER_CONFIRM` and `body.contentJson.dataList` containing:

1. **`AIR_DOMESTIC_ORDER_SUMMARY`** block with `orderId`, `orderNo`, `totalPrice`, `passengerCount`, `flightSummary`, `passengerLines`, `tripTypeLabel`, `createTime`.
2. Optional **`BUTTON`** block with `dataStr: "去支付"` and `linkUrl: "GO_PAY"`.

Also send a short Chinese text summary confirming the order details.

### After User Confirmation

Once the user confirms:
- Call `ask_user` with `card_type=ORDER_SUCCESS`, `order_no` from `buildOrderPreview` response, and `order_summary` with key details (passenger, route, price).
- Do **not** call `buildOrderPreview` again.

## 5. Order Cannot Be Placed

If at any validation or submission step the order cannot proceed, call `ask_user` with:

```json
{
  "card_type": "CANNOT_ORDER",
  "title": "无法完成订票",
  "body": {
    "reason": "<from MCP response>",
    "fallback": "<actionable guidance>"
  }
}
```

Common `CANNOT_ORDER` scenarios across the full flow:

| Scenario | Reason | Fallback |
|---|---|---|
| Product access denied | 未开通国内机票预订权限 | 请联系管理员开通权限 |
| Passenger data permission | 出行人无预订数据权限 | 请联系管理员开通权限 |
| Policy block (no override) | 差标不可逾越 | 请选择差标内舱位或申请特殊审批 |
| Risk control block | 最终风控拦截 | 请联系管理员或稍后重试 |
| Price change not accepted | 价格变动未确认 | 请重新搜索或确认新价格 |

If the user wants to start over, call `mcporter_feihe-travel__resetBookingSession(sessionId)` and load `workflows/intent-and-permission.md`.

## 6. Post-Order

After `ORDER_SUCCESS`:
- The booking flow is complete.
- If the user wants to check order details, call `mcporter_feihe-travel__getOrderDetail(orderId)`.
- If the user wants to book another flight, start a new session. Load `workflows/intent-and-permission.md`.
- For modifications or cancellations, direct the user to the travel management system. This skill does not handle post-order changes.