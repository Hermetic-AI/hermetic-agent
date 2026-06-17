---
name: fh-domestic-flight-booking
description: Use when an OpenCode/Codex agent must complete China domestic flight search and booking by coordinating fh-travel MCP tools via the mcporter bridge with the Java booking state machine under fh.travel.ai.busi.air.domestic.booking; covers date/city normalization, flight search, result filtering, progressive disclosure, flight/cabin selection, passengers, trip applications, cost centers, policy overrun decisions, validation, order preview, and recovery.
---

# FH Domestic Flight Booking

## Purpose

Operate the existing fh-travel MCP service as the source of truth for domestic flight search and booking. MCP tools are accessed via the **mcporter bridge** (`mcporter` local MCP server in opencode), which exposes tools as `mcporter_feihe-travel__*`. This avoids loading all 21 fh-travel tools directly into opencode context, reducing tool pollution. Keep this skill thin: it sequences MCP calls, normalizes inputs, compacts outputs, and loads detailed guidance only when needed. Do not reimplement Java services, TMS adapters, Redis context, policy logic, or order creation inside the skill.

## Load Strategy

Start with this file only. Then load one resource based on the task:

- Architecture and boundaries: `references/architecture.md`
- Context memory governance: `references/context-memory-governance.md`
- MCP call map: `references/mcp-tool-map.md`
- OpenCode invocation guidance: `references/opencode-mcp.md`
- Java source alignment: `references/source-alignment.md`
- Intent & permission: `workflows/intent-and-permission.md`
- Query workflow: `workflows/progressive-search.md`
- Booking workflow: `workflows/booking-mainline.md`
- Round-trip workflow: `workflows/round-trip.md`
- Policy/OAT/recovery: `workflows/policy-oat-recovery.md`
- Order submit & completion: `workflows/order-submit.md`
- Stable schemas: `schemas/*.json`
- AUIP card schema: scenario `ask_user.schema.json`

## MCPorter Bridge Tool Names

MCP tools are accessed through the mcporter bridge, a local MCP server registered as `mcporter` in opencode config. opencode prefixes tools with the server name using `_`. Combined with mcporter's own `upstream__tool` namespace, the final tool names are:

| Native fh-travel tool | MCPorter bridge tool (opencode) |
| --- | --- |
| `queryFlightBasic` | `mcporter_feihe-travel__queryFlightBasic` |
| `filterFlightList` | `mcporter_feihe-travel__filterFlightList` |
| `chooseFlight` | `mcporter_feihe-travel__chooseFlight` |
| `chooseCabin` | `mcporter_feihe-travel__chooseCabin` |
| `fillPassenger` | `mcporter_feihe-travel__fillPassenger` |
| `validateBookingInfo` | `mcporter_feihe-travel__validateBookingInfo` |
| `buildOrderPreview` | `mcporter_feihe-travel__buildOrderPreview` |
| `resetBookingSession` | `mcporter_feihe-travel__resetBookingSession` |
| `checkProductAccess` | `mcporter_feihe-travel__checkProductAccess` |
| `getDateInfo` | `mcporter_feihe-travel__getDateInfo` |
| `getFlightPolicyInfo` | `mcporter_feihe-travel__getFlightPolicyInfo` |
| `chooseAlternativeCabin` | `mcporter_feihe-travel__chooseAlternativeCabin` |
| `listTripApplications` | `mcporter_feihe-travel__listTripApplications` |
| `getTripApplicationDetail` | `mcporter_feihe-travel__getTripApplicationDetail` |
| `listCostCenters` | `mcporter_feihe-travel__listCostCenters` |
| `bindCostCenter` | `mcporter_feihe-travel__bindCostCenter` |
| `getDefaultContact` | `mcporter_feihe-travel__getDefaultContact` |
| `recordPolicyUserDecision` | `mcporter_feihe-travel__recordPolicyUserDecision` |
| `getOrderDetail` | `mcporter_feihe-travel__getOrderDetail` |

For any other fh-travel MCP tool, apply the same rule: prefix with `mcporter_feihe-travel__`.

**Why mcporter bridge?** Directly loading fh-travel as a remote MCP server puts all 21 tools into the LLM context at once, polluting the tool list and consuming tokens. The mcporter bridge acts as a single local MCP server that proxies to fh-travel, and opencode's `allowedTools` in `mcporter.json` controls which tools are exposed — enabling per-scenario, on-demand tool loading.

## Fast Path For Clear Search

When the user's latest message already gives departure city, arrival city, and
departure date, do this first:

1. Normalize the date locally from the conversation date. For example, on
   2026-06-09, "明天" is `2026-06-10`.
2. For a new session, call `mcporter_feihe-travel__checkProductAccess` first. If
   access is denied, stop with `CANNOT_ORDER`. See `workflows/intent-and-permission.md`.
3. Call `mcporter_feihe-travel__queryFlightBasic` with only supported arguments.
4. Do not call `ask_user`, `question`, `glob`, `read`, `grep`, `skill`,
   `flight-query`, `getDateInfo`, or helper scripts before that first search.
5. Ignore cabin-class wording during first search unless the MCP tool schema
   exposes a supported `cabinClass` argument. Never ask for cabin class before
   first results.

Example: "帮我查一下北京到上海明天的单程机票" means directly call:

```json
{"departureCity":"北京","arrivalCity":"上海","departureDate":"2026-06-10"}
```

## Core Flow (Business Flow Alignment)

| Business Step | State | Tool / Action | Workflow |
|---|---|---|---|
| 1. Intent & Permission | INIT → TRIP_CONFIRMED | `checkProductAccess` | `intent-and-permission.md` |
| 2. Search & Select | FLIGHT_LISTED | `queryFlightBasic` / `filterFlightList` | `progressive-search.md` |
| 3. Flight & Cabin | FLIGHT_SELECTED | `chooseFlight` | `booking-mainline.md` |
| 3. Cabin | CABIN_SELECTED | `chooseCabin` | `booking-mainline.md` |
| 3. Passenger & OAT | PASSENGER_FILLED | `fillPassenger` + OAT | `booking-mainline.md` |
| 4. Policy & Risk | INFO_VALIDATED | `validateBookingInfo` | `order-submit.md` |
| 4. Policy Decision | PRICE_CONFIRMED | `recordPolicyUserDecision` | `policy-oat-recovery.md` |
| 5. Order Submit | ORDER_PREVIEWED | `buildOrderPreview` (creates order) | `order-submit.md` |
| | FINISHED | `ORDER_SUCCESS` card | `order-submit.md` |

Branches: `CABIN_SELECTED → FLIGHT_LISTED` (round-trip return leg), `PASSENGER_FILLED → PRICE_CONFIRMED` (price change), `resetBookingSession` (recovery), `CANNOT_ORDER` (terminal block at any step where permission or risk control fails).

## Operating Rules

1. Call `checkProductAccess` before the first search in a new session. See `workflows/intent-and-permission.md`.
2. Keep one `sessionId` for the whole booking thread. Never select from another session's result.
3. Normalize relative dates to `yyyy-MM-dd` before MCP calls. Do not pass "tomorrow" or "next Friday" to MCP.
4. Use `mcporter_feihe-travel__queryFlightBasic` when route, date, cabin class, baggage/refund/policy filters, or round-trip mode changes.
5. Use `mcporter_feihe-travel__filterFlightList` only for narrowing an already loaded list by local list filters.
6. Show compact summaries first, then reveal details only after the user asks or must choose.
7. Auth is handled by the container environment (`FLIGHT_API_KEY`) and `work/mcp/mcporter.json`. Do not ask for, explain, refuse to use, or echo tokens.
8. Call mcporter bridge tools directly. Do not write curl commands, Bash HTTP calls, JSON-RPC envelopes, `npx mcporter call`, webfetch, or delegate flight search to the `task` subagent. If a `mcporter_feihe-travel__*` tool call fails with a connection or network error, do NOT fall back to HTTP/webfetch/curl. Instead, emit `ask_user` with `card_type=CANNOT_ORDER`, `reason: "航班查询服务暂时无法连接"`, `fallback: "请稍后重试"`.
9. Reply in Chinese by default. Use Chinese titles, field labels, option labels, button text, explanations, and error messages unless the user explicitly asks for another language.
10. Extract facts from the user's message before asking anything. If the user already provided route, date, cabin class, passenger, budget, time preference, baggage/refund/policy preference, trip application, or cost center, use it directly.
11. Ask only for information that is required for the next tool call and is truly missing or ambiguous. Combine missing fields into one `ask_user` card instead of asking one-by-one.
12. Use `ask_user` for interactive user input. Do not present selectable flights, cabins, passengers, policy decisions, or order confirmation as plain Markdown when an AUIP card can represent them.
13. Call tools in state order. Run `scripts/stage_guard.py` when stage is known and the next tool is uncertain.
14. Treat MCP output as authoritative. If the skill conflicts with MCP behavior, inspect Java source and update the skill.
15. Do not load or delegate to the legacy `flight-query` skill inside this scenario. This scenario owns search and booking.
16. Before reusing route, date, passenger, selected flight, cabin, or `sessionId` from history, apply `references/context-memory-governance.md`; a new origin-destination/date intent starts a new search context and must not inherit stale flight-selection state.
17. `validateBookingInfo` covers permission checks (出行人数据权限, 预订下单权限) and final risk control (风控拦截). Do not add separate permission or risk tools. See `workflows/order-submit.md`.
18. `buildOrderPreview` creates the order. There is no separate submit tool. See `workflows/order-submit.md`.
19. If any step returns a permission or risk block, emit `CANNOT_ORDER` immediately. Do not retry or override.
20. If any `mcporter_feihe-travel__*` tool call returns a connection error, timeout, or network failure, do NOT retry with `webfetch`, `curl`, `Bash`, or any HTTP fallback. Emit `ask_user` with `card_type=CANNOT_ORDER`, Chinese `reason`, and `fallback` suggesting the user retry later. See `workflows/intent-and-permission.md` for details.

## MANDATORY: Flight Data Must Be Rendered in AUIP Card

**When `mcporter_feihe-travel__queryFlightBasic` or `mcporter_feihe-travel__filterFlightList` returns flight data, you MUST immediately emit an `ask_user` call with `card_type: "FLIGHT_RESULT"` and populate `body.contentJson` with the full flight list.**

DO NOT:
- Emit a `FLIGHT_RESULT` or `FLIGHT_LIST` card with empty `body: {}`
- Only show flights as plain Markdown text
- Skip the card and move to the next step without showing results

The MCP response contains `flightList[]` — map each entry into the AGUI v2 `AIR_DOMESTIC_FLIGHT_LIST` format and put it inside `ask_user`'s `body.contentJson.dataList[0].dataJson.flightList[]`.

Mapping from MCP response to card fields:

| MCP response field | Card field |
|---|---|
| `serialNumber` | `dataJson.serialNumber` |
| `flightCount` or `filteredCount` | `dataJson.totalCount` / `dataJson.filteredCount` |
| `flightList[].airId` | `flightList[].airId` |
| `flightList[].airName` | `flightList[].airlineName` |
| `flightList[].tripInfos[0].flightInfoList[0].flightId` | `flightList[].flightNo` |
| `flightList[].tripInfos[0].flightInfoList[0].depAirPortName` | `flightList[].depAirportName` |
| `flightList[].tripInfos[0].flightInfoList[0].arrAirPortName` | `flightList[].arrAirportName` |
| `flightList[].tripInfos[0].flightInfoList[0].depDate` + `depTime` | `flightList[].depDate` / `depTime` |
| `flightList[].tripInfos[0].flightInfoList[0].arrDate` + `arrTime` | `flightList[].arrDate` / `arrTime` |
| `flightList[].showPrice` or `totalPrice` | `flightList[].lowestPrice` / `totalPrice` |
| `flightList[].tripInfos[0].duration` | `flightList[].durationMin` / `totalDuration` |

After the card, also send a short Chinese text summary (1-2 sentences) confirming the search result count and cheapest option.

## AUIP / ask_user Contract (AGUI v2)

This skill uses the **AGUI v2 domestic booking contract** for flight-facing cards. The frontend renderer is aligned with `docs/agui/agui-schema.md` and the sample payloads in `docs/agui/`.

Put the **AGUI v2 渲染描述直接放在 `body.contentJson`** (schemaVersion + dataList)。**不要**包外层错误码壳 / 会话元数据 envelope — 这些由 Hub 内部维护, 不通过本协议传递。

### Card Types and AGUI v2 dataList Composition

| Business scene | `card_type` | Required `body.contentJson.dataList` order |
| --- | --- | --- |
| Missing search input | `OD_INPUT` | top-level `fields[]` (no contentJson) |
| Flight search result | `FLIGHT_RESULT` | `AIR_DOMESTIC_FLIGHT_LIST` → optional `PLAIN_TEXT` → optional `AIR_DOMESTIC_FLIGHT_SUGGEST` × N |
| Direct flight selection | `FLIGHT_LIST` | `AIR_DOMESTIC_FLIGHT_LIST` (same structure) |
| Cabin selection | `CABIN_LIST` | optional `PLAIN_TEXT` → `AIR_DOMESTIC_CABIN_LIST` |
| Passenger details | `PASSENGER_FORM` | top-level `fields[]` (no contentJson) |
| Trip/cost/contact binding | `OAT_BINDING` | top-level `fields[]` or `options[]` |
| Price changed | `PRICE_VERIFY` | top-level `current_price`, `original_price`, `price_diff` |
| Policy overrun | `POLICY_DECISION` | top-level `decision_buttons[]` |
| Final preview | `ORDER_CONFIRM` | optional `PLAIN_TEXT` → `AIR_DOMESTIC_ORDER_SUMMARY` → optional `BUTTON` |
| Order completed | `ORDER_SUCCESS` | top-level `order_no` or `order_summary` |
| Cannot continue | `CANNOT_ORDER` | top-level `reason`, `fallback` |
| Free-text fallback | `CHAT_FALLBACK` | top-level `message` |

`body.contentJson` 是 AGUI 渲染描述本身, 不要包 envelope (`tmsErrorCode` / `errorCode` / `errorMsg` / `enErrorMsg` / `requestSeqNo` / `delay` / `recordId` / `sessionId` / `role` / `intent` / `sceneId` / `reason` / `chatTime` / `correlationId`) — Hub 拦截层会识别 `card_type=FLIGHT_RESULT` 缺 body 的情况, 用最近一次 `mcporter_feihe-travel__queryFlightBasic` 输出兜底; 也会自动归一 `body.agui` 旧 envelope 到 `body.contentJson`, 兼容过渡期残留。

### Minimum FLIGHT_RESULT Shape

```json
{
  "card_type": "FLIGHT_RESULT",
  "title": "机票已发送",
  "body": {
    "contentJson": {
      "schemaVersion": "2",
      "dataList": [
        {
          "basicType": "AIR_DOMESTIC_FLIGHT_LIST",
          "dataStr": "共查询到133个航班最后筛选出133个",
          "dataJson": {
            "serialNumber": "260615114056A00000001",
            "totalCount": 133,
            "filteredCount": 133,
            "flightList": []
          },
          "linkUrl": ""
        }
      ],
      "thinkingSteps": ["已按您的行程条件查询航班并整理列表"]
    }
  }
}
```

### AGUI v2 Field Reference

- `AIR_DOMESTIC_FLIGHT_LIST.dataJson.flightList[]`: use `depCityName`, `arrCityName`, `depDate`, `lowestPrice`, `totalPrice`, `totalDuration`, `durationMin`, `airlineName`, `flightNo`, `airId`, `serialNo`, `flightId`, `legs[]`, `depTime`, `depAirportName`, `depTerminal`, `arrDate`, `arrTime`, `arrAirportName`, `arrTerminal`, `arrDayOffset`.
- `AIR_DOMESTIC_CABIN_LIST.dataJson`: include `serialNumber`, `selectedFlight`, and `cabins[]` with `cabId`, `cabinName`, `cab`, `cabinCode`, `cabClass`, `price`, `totalPrice`, `normalPrice`, `discountRate`, `tax`, `clientService`, `mealIncluded`, `luggage`, `weight`, `remainSeats`, `num`.
- `AIR_DOMESTIC_ORDER_SUMMARY.dataJson`: include `actionType`, `orderId`, `orderNo`, `orderStatus`, `totalPrice`, `passengerCount`, `createTime`, `idempotencyKey`, `message`, `submitPayload`, `flightSummary`, `passengerLines`, `tripTypeLabel`.
- `BUTTON`: use `dataStr` for the label and `linkUrl` for action enum, for example `GO_PAY`.

Never emit unsupported aliases such as `CABIN_OPTIONS` or `ORDER_PREVIEW`.
Do not emit `OD_INPUT` when the user's message already contains departure city, arrival city, and departure date. Go directly to `mcporter_feihe-travel__queryFlightBasic`.
For all form cards (OD_INPUT, PASSENGER_FORM, OAT_BINDING), include only missing fields; do not ask the user to re-enter data already available in the conversation or MCP context.

## Public Utility Layer

Use scripts instead of rewriting prompt-side logic:

```powershell
python skills\fh-domestic-flight-booking\scripts\normalize_request.py plan.json
python skills\fh-domestic-flight-booking\scripts\stage_guard.py --stage FLIGHT_LISTED --tool chooseFlight
python skills\fh-domestic-flight-booking\scripts\compact_mcp_payload.py result.json --limit 8
python skills\fh-domestic-flight-booking\scripts\render_options.py compact.json
```

These scripts are deliberately small and dependency-free so OpenCode agents can reuse them across models.