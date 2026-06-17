---
name: fh-domestic-flight-booking-mcporter
description: Use when an OpenCode/Codex agent must complete China domestic flight search and booking through the mcporter bridge for fh-travel MCP tools. Tools are exposed as mcporter_feihe-travel__* via opencode's local MCP server.
---

# FH Domestic Flight Booking via MCPorter Bridge

## Purpose

Operate the same Feihe domestic flight booking flow as `fh-domestic-flight-booking`, but call the fh-travel MCP tools through the mcporter bridge registered by OpenCode. The bridge exposes tools with the `mcporter_feihe-travel__` prefix. Keep business behavior aligned with the original skill; only the MCP transport and tool names differ.

## Load Strategy

Start with this file only. Load original resources from `fh-domestic-flight-booking` when details are needed:

- Architecture and boundaries: `../fh-domestic-flight-booking/references/architecture.md`
- Context memory governance: `../fh-domestic-flight-booking/references/context-memory-governance.md`
- MCP call map: `../fh-domestic-flight-booking/references/mcp-tool-map.md`
- Java source alignment: `../fh-domestic-flight-booking/references/source-alignment.md`
- Query workflow: `../fh-domestic-flight-booking/workflows/progressive-search.md`
- Booking workflow: `../fh-domestic-flight-booking/workflows/booking-mainline.md`
- Round-trip workflow: `../fh-domestic-flight-booking/workflows/round-trip.md`
- Policy/OAT/recovery: `../fh-domestic-flight-booking/workflows/policy-oat-recovery.md`
- Stable schemas: `../fh-domestic-flight-booking/schemas/*.json`

## MCPorter Bridge Tool Names

The mcporter bridge is a local MCP server named `mcporter` in opencode config. opencode prefixes tools with the server name using `_`. Combined with mcporter's own `upstream__tool` namespace, the final tool names are:

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

## Fast Path For Clear Search

When the user already gives departure city, arrival city, and departure date:

1. Normalize the date locally from the conversation date.
2. Immediately call `mcporter_feihe-travel__queryFlightBasic` with only supported arguments.
3. Do not call `ask_user`, `question`, `glob`, `read`, `grep`, `skill`, `flight-query`, `getDateInfo`, `checkProductAccess`, or helper scripts before that first search.
4. Ignore cabin-class wording during first search unless the tool schema exposes a supported `cabinClass` argument.

Example: "帮我查一下北京到上海明天的单程机票" means directly call:

```json
{"departureCity":"北京","arrivalCity":"上海","departureDate":"2026-06-10"}
```

## Core Flow

```text
INIT
  -> FLIGHT_LISTED        mcporter_feihe-travel__queryFlightBasic / filterFlightList
  -> FLIGHT_SELECTED      mcporter_feihe-travel__chooseFlight
  -> CABIN_SELECTED       mcporter_feihe-travel__chooseCabin
  -> PASSENGER_FILLED     mcporter_feihe-travel__fillPassenger plus OAT data
  -> INFO_VALIDATED       mcporter_feihe-travel__validateBookingInfo
  -> ORDER_PREVIEWED      mcporter_feihe-travel__buildOrderPreview
  -> FINISHED             frontend/user final action
```

## Operating Rules

1. Keep one `sessionId` for the whole booking thread. Never select from another session's result.
2. Normalize relative dates to `yyyy-MM-dd` before MCP calls.
3. Treat mcporter as a transport bridge only. Do not ask the user about mcporter, npm, OAuth, config files, or tokens.
4. Auth is handled by the container environment (`FLIGHT_API_KEY`) and `work/mcp/mcporter.json`. Do not ask for, explain, refuse to use, or echo tokens.
5. Call mcporter bridge tools directly. Do not write curl commands, Bash HTTP calls, JSON-RPC envelopes, `npx mcporter call`, or delegate flight search to a subagent.
6. Reply in Chinese by default.
7. Extract facts from the user's message before asking anything. Ask only for information required for the next tool call and truly missing or ambiguous.
8. Use `ask_user` for interactive user input. Do not present selectable flights, cabins, passengers, policy decisions, or order confirmation as plain Markdown when an AUIP card can represent them.
9. MCP output is authoritative. If behavior conflicts with the original skill, inspect the original references and Java source alignment docs.
10. Do not load or delegate to the legacy `flight-query` skill inside this scenario.

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

## AUIP / ask_user Contract

This mcporter variant uses the **AGUI v2 domestic booking contract** for flight-facing cards. The frontend renderer is aligned with `docs/agui/agui-schema.md` and the sample payloads in `docs/agui/`.

Keep the outer `ask_user.card_type` compatible with the existing AUIP schema, but put the **AGUI v2 渲染描述直接放在 `body.contentJson`** (schemaVersion + dataList)。**不要**包外层错误码壳 / 会话元数据 envelope — 这些由 Hub 内部维护, 不通过本协议传递:

| Business scene | `ask_user.card_type` | Required `body.contentJson.dataList` order |
| --- | --- | --- |
| Flight list | `FLIGHT_RESULT` | `AIR_DOMESTIC_FLIGHT_LIST` → optional `PLAIN_TEXT` → optional `AIR_DOMESTIC_FLIGHT_SUGGEST` × N |
| Cabin list | `CABIN_LIST` | optional `PLAIN_TEXT` → `AIR_DOMESTIC_CABIN_LIST` |
| Order confirmation | `ORDER_CONFIRM` | optional `PLAIN_TEXT` → `AIR_DOMESTIC_ORDER_SUMMARY` → optional `BUTTON` |

`body.contentJson` 是 AGUI 渲染描述本身, 不要包 envelope (`tmsErrorCode` / `errorCode` / `errorMsg` / `enErrorMsg` / `requestSeqNo` / `delay` / `recordId` / `sessionId` / `role` / `intent` / `sceneId` / `reason` / `chatTime` / `correlationId`) — Hub 拦截层会识别 `card_type=FLIGHT_RESULT` 缺 body 的情况, 用最近一次 `mcporter_feihe-travel__queryFlightBasic` 输出兜底; 也会自动归一 `body.agui` 旧 envelope 到 `body.contentJson`, 兼容过渡期残留。

Minimum shape:

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

For AGUI v2, preserve field names exactly as documented:

- `AIR_DOMESTIC_FLIGHT_LIST.dataJson.flightList[]`: use `depCityName`, `arrCityName`, `depDate`, `lowestPrice`, `totalPrice`, `totalDuration`, `durationMin`, `airlineName`, `flightNo`, `airId`, `serialNo`, `flightId`, `legs[]`, `depTime`, `depAirportName`, `depTerminal`, `arrDate`, `arrTime`, `arrAirportName`, `arrTerminal`, `arrDayOffset`.
- `AIR_DOMESTIC_CABIN_LIST.dataJson`: include `serialNumber`, `selectedFlight`, and `cabins[]` with `cabId`, `cabinName`, `cab`, `cabinCode`, `cabClass`, `price`, `totalPrice`, `normalPrice`, `discountRate`, `tax`, `clientService`, `mealIncluded`, `luggage`, `weight`, `remainSeats`, `num`.
- `AIR_DOMESTIC_ORDER_SUMMARY.dataJson`: include `actionType`, `orderId`, `orderNo`, `orderStatus`, `totalPrice`, `passengerCount`, `createTime`, `idempotencyKey`, `message`, `submitPayload`, `flightSummary`, `passengerLines`, `tripTypeLabel`.
- `BUTTON`: use `dataStr` for the label and `linkUrl` for action enum, for example `GO_PAY`.

Legacy AUIP remains a fallback only: `OD_INPUT`, `PASSENGER_FORM`, `OAT_BINDING`, `PRICE_VERIFY`, `POLICY_DECISION`, `ORDER_SUCCESS`, `CANNOT_ORDER`, and `CHAT_FALLBACK` keep the same top-level fields as `fh-domestic-flight-booking`.

Never emit unsupported aliases such as `CABIN_OPTIONS` or `ORDER_PREVIEW`.