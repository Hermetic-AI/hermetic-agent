---
name: fh-domestic-flight-booking
description: Use when an OpenCode/Codex agent must complete China domestic flight search and booking by coordinating fh-travel MCP tools from src/main/java/fh/travel/mcp with the Java booking state machine under fh.travel.ai.busi.air.domestic.booking; covers date/city normalization, flight search, result filtering, progressive disclosure, flight/cabin selection, passengers, trip applications, cost centers, policy overrun decisions, validation, order preview, and recovery.
---

# FH Domestic Flight Booking

## Purpose

Operate the existing fh-travel MCP service as the source of truth for domestic flight search and booking. Keep this skill thin: it sequences MCP calls, normalizes inputs, compacts outputs, and loads detailed guidance only when needed. Do not reimplement Java services, TMS adapters, Redis context, policy logic, or order creation inside the skill.

## Load Strategy

Start with this file only. Then load one resource based on the task:

- Architecture and boundaries: `references/architecture.md`
- MCP call map: `references/mcp-tool-map.md`
- OpenCode invocation guidance: `references/opencode-mcp.md`
- Java source alignment: `references/source-alignment.md`
- Query workflow: `workflows/progressive-search.md`
- Booking workflow: `workflows/booking-mainline.md`
- Round-trip workflow: `workflows/round-trip.md`
- Policy/OAT/recovery: `workflows/policy-oat-recovery.md`
- Stable schemas: `schemas/*.json`
- AUIP card schema: scenario `ask_user.schema.json`

## Fast Path For Clear Search

When the user's latest message already gives departure city, arrival city, and
departure date, do this first:

1. Normalize the date locally from the conversation date. For example, on
   2026-06-09, "明天" is `2026-06-10`.
2. Call native MCP `queryFlightBasic` or `feihe-travel_queryFlightBasic`
   immediately with only supported arguments.
3. Do not call `ask_user`, `question`, `glob`, `read`, `grep`, `skill`,
   `flight-query`, `getDateInfo`, `checkProductAccess`, or helper scripts before
   that first search.
4. Ignore cabin-class wording during first search unless the MCP tool schema
   exposes a supported `cabinClass` argument. Never ask for cabin class before
   first results.

Example: "帮我查一下北京到上海明天的单程机票" means directly call:

```json
{"departureCity":"北京","arrivalCity":"上海","departureDate":"2026-06-10"}
```

## Core Flow

```text
INIT
  -> FLIGHT_LISTED        queryFlightBasic / filterFlightList
  -> FLIGHT_SELECTED      chooseFlight
  -> CABIN_SELECTED       chooseCabin
  -> PASSENGER_FILLED     fillPassenger plus OAT data
  -> INFO_VALIDATED       validateBookingInfo
  -> ORDER_PREVIEWED      buildOrderPreview
  -> FINISHED             frontend/user final action
```

Branches: `PASSENGER_FILLED -> PRICE_CONFIRMED` for price changes, policy decisions before preview, `CABIN_SELECTED -> FLIGHT_LISTED` for FREE round-trip return-leg work, and `resetBookingSession` for corrupted context.

## Operating Rules

1. Keep one `sessionId` for the whole booking thread. Never select from another session's result.
2. Normalize relative dates to `yyyy-MM-dd` before MCP calls. Do not pass "tomorrow" or "next Friday" to MCP.
3. Use `queryFlightBasic` when route, date, cabin class, baggage/refund/policy filters, or round-trip mode changes.
4. Use `filterFlightList` only for narrowing an already loaded list by local list filters.
5. Show compact summaries first, then reveal details only after the user asks or must choose.
6. Auth is handled by the container environment (`FLIGHT_API_KEY`) and the native OpenCode MCP config. Do not ask for, explain, refuse to use, or echo tokens.
7. Call native MCP tools directly. In OpenCode they may appear as `feihe-travel_queryFlightBasic` / `feihe-travel_filterFlightList`; use those native tools when present. Do not write curl commands, Bash HTTP calls, JSON-RPC envelopes, or delegate flight search to the `task` subagent.
8. Reply in Chinese by default. Use Chinese titles, field labels, option labels, button text, explanations, and error messages unless the user explicitly asks for another language.
9. Extract facts from the user's message before asking anything. If the user already provided route, date, cabin class, passenger, budget, time preference, baggage/refund/policy preference, trip application, or cost center, use it directly.
10. Ask only for information that is required for the next tool call and is truly missing or ambiguous. Combine missing fields into one `ask_user` card instead of asking one-by-one.
11. Use `ask_user` for interactive user input. Do not present selectable flights, cabins, passengers, policy decisions, or order confirmation as plain Markdown when an AUIP card can represent them.
12. Call tools in state order. Run `scripts/stage_guard.py` when stage is known and the next tool is uncertain.
13. Treat MCP output as authoritative. If the skill conflicts with MCP behavior, inspect Java source and update the skill.
14. Do not load or delegate to the legacy `flight-query` skill inside this scenario. This scenario owns search and booking.

## AUIP / ask_user Contract

Use only the card types supported by this project:

| Stage | Card type | Required shape |
| --- | --- | --- |
| Missing search input | `OD_INPUT` | top-level `fields[]` |
| Flight search result | `FLIGHT_RESULT` | `body.summary` + `body.plans[]` |
| Direct flight selection | `FLIGHT_LIST` | top-level `flights[]` |
| Cabin selection | `CABIN_LIST` | top-level `cabins[]` |
| Passenger details | `PASSENGER_FORM` | top-level `fields[]` |
| Trip/cost/contact binding | `OAT_BINDING` | top-level `fields[]` or `options[]` |
| Price changed | `PRICE_VERIFY` | top-level `current_price`, `original_price`, `price_diff` |
| Policy overrun | `POLICY_DECISION` | top-level `decision_buttons[]` |
| Final preview | `ORDER_CONFIRM` | top-level `order_summary`, `total_price` |
| Order completed | `ORDER_SUCCESS` | top-level `order_no` or `order_summary` |
| Cannot continue | `CANNOT_ORDER` | top-level `reason`, `fallback` |
| Free-text fallback | `CHAT_FALLBACK` | top-level `message` |

Never emit unsupported aliases such as `CABIN_OPTIONS` or `ORDER_PREVIEW`.
Do not emit `OD_INPUT` when the user's message already contains departure city, arrival city, and departure date. Go directly to `queryFlightBasic`.
For all form cards, include only missing fields; do not ask the user to re-enter data already available in the conversation or MCP context.
For `FLIGHT_RESULT`, keep flight details inside `body.plans[].flights[]` because the frontend `FlightResultCard` reads from `card.body`.
For form/list/decision/preview cards, put fields at the card top level because the corresponding frontend components read `card.fields`, `card.flights`, `card.cabins`, `card.decision_buttons`, and `card.order_summary`.

## Public Utility Layer

Use scripts instead of rewriting prompt-side logic:

```powershell
python skills\fh-domestic-flight-booking\scripts\normalize_request.py plan.json
python skills\fh-domestic-flight-booking\scripts\stage_guard.py --stage FLIGHT_LISTED --tool chooseFlight
python skills\fh-domestic-flight-booking\scripts\compact_mcp_payload.py result.json --limit 8
python skills\fh-domestic-flight-booking\scripts\render_options.py compact.json
```

These scripts are deliberately small and dependency-free so OpenCode agents can reuse them across models.
