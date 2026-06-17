# Intent Recognition and Permission Check

Use before starting any flight search or booking flow. Covers business flow Step 1: intent identification and product access verification.

## 1. Domestic Flight Intent

This skill handles domestic flight queries only.

If the user clearly intends to book or search a domestic flight (mentions flights, airlines, cities, dates, or booking keywords like "订票", "机票", "查航班"), proceed to Step 2.

If the user mentions hotels ("酒店"), trains ("火车", "高铁"), international flights, or other non-domestic-flight products, call `ask_user` with `card_type=CHAT_FALLBACK` and `message` explaining this assistant handles domestic flight booking only.

Ambiguous intents ("我要出差", "帮我订票", "买票") are acceptable as domestic flight — proceed to clarify route and date.

## 2. Product Access Check

Call `mcporter_feihe-travel__checkProductAccess(sessionId)` before the first search for a new session.

Outcomes:

| MCP Response | Action |
|---|---|
| Access granted | Proceed to search. Load `workflows/progressive-search.md`. |
| Access denied | Call `ask_user` with `card_type=CANNOT_ORDER`, `reason: "未开通国内机票预订权限"`, `fallback: "请联系管理员开通机票预订权限"`. Stop the flow. |
| Error / unavailable | Call `ask_user` with `card_type=CANNOT_ORDER`, `reason: "暂时无法验证预订权限，请稍后重试"`. |

Do not call `checkProductAccess` again for subsequent searches within the same session. If the session was reset via `resetBookingSession`, call `checkProductAccess` again.

## 3. Trip and Date Clarity

If the user's message already contains departure city, arrival city, and departure date, skip `ask_user` and proceed directly to `mcporter_feihe-travel__queryFlightBasic`. See `workflows/progressive-search.md` Fast Path.

If any required field (departure city, arrival city, departure date) is missing, call `ask_user` with `card_type=OD_INPUT`. Include only the missing fields in `fields[]`. Use Chinese labels (`出发城市`, `到达城市`, `出发日期`).

Do not ask for cabin class, airline preference, or optional filters before the first search.

## Transition

After access is granted and required inputs are available, load `workflows/progressive-search.md` for search, then `workflows/booking-mainline.md` for selection and data filling.

## MCP Connection Failure

If `checkProductAccess` or any `mcporter_feihe-travel__*` tool call fails with a connection error, timeout, or network failure:

1. Do NOT retry with `webfetch`, `curl`, Bash HTTP calls, or any other HTTP fallback.
2. Do NOT emit a `FLIGHT_RESULT` card with empty `flightList` then try webfetch.
3. Emit `ask_user` with `card_type=CANNOT_ORDER`, Chinese `reason`, and `fallback`:

```json
{
  "card_type": "CANNOT_ORDER",
  "title": "服务暂时不可用",
  "body": {
    "reason": "航班查询服务暂时无法连接，请稍后重试。",
    "fallback": "如持续无法连接，请联系管理员检查 MCP 服务状态。"
  }
}
```

4. End the conversation turn. Do not silently retry or switch transport.