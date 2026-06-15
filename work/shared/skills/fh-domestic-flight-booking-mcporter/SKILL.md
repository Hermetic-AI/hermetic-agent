---
name: fh-domestic-flight-booking-mcporter
description: Use when an OpenCode/Codex agent must complete China domestic flight search and booking through the mcporter bridge for fh-travel MCP tools. This is the mcporter-backed variant of fh-domestic-flight-booking and keeps MCP server discovery/tool filtering in work/mcp/mcporter.json.
---

# FH Domestic Flight Booking via MCPorter

## Purpose

Operate the same Feihe domestic flight booking flow as `fh-domestic-flight-booking`, but call the fh-travel MCP tools through the `mcporter-feihe-travel` bridge registered by OpenCode. Keep business behavior aligned with the original skill; only the MCP transport and tool names differ.

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

## MCPorter Tool Names

The mcporter bridge exposes tools with the `<server>__<tool>` namespace. For this scenario use these names:

| Native fh-travel tool | MCPorter bridge tool |
| --- | --- |
| `queryFlightBasic` | `feihe-travel__queryFlightBasic` |
| `filterFlightList` | `feihe-travel__filterFlightList` |
| `chooseFlight` | `feihe-travel__chooseFlight` |
| `chooseCabin` | `feihe-travel__chooseCabin` |
| `fillPassenger` | `feihe-travel__fillPassenger` |
| `validateBookingInfo` | `feihe-travel__validateBookingInfo` |
| `buildOrderPreview` | `feihe-travel__buildOrderPreview` |
| `resetBookingSession` | `feihe-travel__resetBookingSession` |

For any other fh-travel MCP tool, apply the same rule: prefix it with `feihe-travel__`.

## Fast Path For Clear Search

When the user already gives departure city, arrival city, and departure date:

1. Normalize the date locally from the conversation date.
2. Immediately call `feihe-travel__queryFlightBasic` with only supported arguments.
3. Do not call `ask_user`, `question`, `glob`, `read`, `grep`, `skill`, `flight-query`, `getDateInfo`, `checkProductAccess`, or helper scripts before that first search.
4. Ignore cabin-class wording during first search unless the tool schema exposes a supported `cabinClass` argument.

Example: "帮我查一下北京到上海明天的单程机票" means directly call:

```json
{"departureCity":"北京","arrivalCity":"上海","departureDate":"2026-06-10"}
```

## Core Flow

```text
INIT
  -> FLIGHT_LISTED        feihe-travel__queryFlightBasic / feihe-travel__filterFlightList
  -> FLIGHT_SELECTED      feihe-travel__chooseFlight
  -> CABIN_SELECTED       feihe-travel__chooseCabin
  -> PASSENGER_FILLED     feihe-travel__fillPassenger plus OAT data
  -> INFO_VALIDATED       feihe-travel__validateBookingInfo
  -> ORDER_PREVIEWED      feihe-travel__buildOrderPreview
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

## AUIP / ask_user Contract

This mcporter variant uses the **AGUI v2 domestic booking contract** for flight-facing cards. The frontend renderer is aligned with `docs/agui/agui-schema.md` and the sample payloads in `docs/agui/`.

Keep the outer `ask_user.card_type` compatible with the existing AUIP schema, but put the AGUI payload under `body.agui`:

| Business scene | `ask_user.card_type` | `body.agui.data.sceneId` | Required `contentJson.dataList` order |
| --- | --- | --- | --- |
| Flight list | `FLIGHT_RESULT` | `DOMESTIC_BOOKING_FLIGHT_LIST` | `AIR_DOMESTIC_FLIGHT_LIST` → optional `PLAIN_TEXT` → optional `AIR_DOMESTIC_FLIGHT_SUGGEST` × N |
| Cabin list | `CABIN_LIST` | `DOMESTIC_BOOKING_CABIN_LIST` | optional `PLAIN_TEXT` → `AIR_DOMESTIC_CABIN_LIST` |
| Order confirmation | `ORDER_CONFIRM` | `DOMESTIC_BOOKING_ORDER_CONFIRM` | optional `PLAIN_TEXT` → `AIR_DOMESTIC_ORDER_SUMMARY` → optional `BUTTON` |

`body.agui` must be either the full envelope from `docs/agui/*.json` or its `data` object. Prefer the full envelope when a `requestSeqNo` is available.

Minimum shape:

```json
{
  "card_type": "FLIGHT_RESULT",
  "title": "机票已发送",
  "body": {
    "agui": {
      "tmsErrorCode": "",
      "errorCode": "0",
      "errorMsg": "",
      "enErrorMsg": "",
      "requestSeqNo": "T260615114050B00000001",
      "delay": 0,
      "data": {
        "recordId": "T260615114050B00000001",
        "sessionId": "S260615114027B00000001",
        "role": "assistant",
        "intent": "BOOKING:DOMESTIC_BOOKING/air_domestic_booking",
        "sceneId": "DOMESTIC_BOOKING_FLIGHT_LIST",
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
        },
        "reason": "已按您的行程条件查询航班并整理列表",
        "chatTime": "2026-06-15T03:40:57.032094018Z",
        "correlationId": ""
      }
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
