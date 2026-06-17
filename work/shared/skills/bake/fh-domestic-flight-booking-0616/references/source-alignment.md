# Source Alignment

Use this file when checking whether the skill matches the Java project.

## Authoritative Source Paths

- MCP adapters: `src/main/java/fh/travel/mcp`
- Search MCP: `src/main/java/fh/travel/mcp/product/air/domestic/FlightSearchMcp.java`
- Filter/date/holiday MCP: `src/main/java/fh/travel/mcp/product/air/domestic`
- Booking MCP: `src/main/java/fh/travel/mcp/booking/domestic`
- Booking state: `src/main/java/fh/travel/ai/busi/air/domestic/booking/AirDomesticBookingStage.java`
- Transitions: `src/main/java/fh/travel/ai/busi/air/domestic/booking/AirDomesticBookingTransitions.java`
- Context: `src/main/java/fh/travel/ai/busi/air/domestic/booking/AirDomesticBookingContext.java`
- Scene derivation: `src/main/java/fh/travel/ai/busi/air/domestic/booking/BookingSceneDeriver.java`
- Java-side LLM projection: `src/main/java/fh/travel/ai/busi/air/domestic/booking/tool/FlightSearchToolLlmProjection.java`

## Source-Derived Facts

- Main stages: `INIT`, `TRIP_CONFIRMED`, `FLIGHT_LISTED`, `FLIGHT_SELECTED`, `CABIN_SELECTED`, `PASSENGER_FILLED`, `INFO_VALIDATED`, `PRICE_CONFIRMED`, `ORDER_PREVIEWED`, `READY_TO_SUBMIT`, `FINISHED`, `CANCELLED`.
- OAT substeps: `AWAIT_PASSENGERS`, `NEED_TRIP_BIND`, `NEED_COST_CENTER`, `NEED_CONTACT`, `OAT_READY`.
- Round-trip modes: `RECOMMENDED`, `FREE`.
- Departure day parts: `MORNING`, `AFTERNOON`, `EVENING`.
- `queryFlightBasic` writes search context and supports route/date/cabin/refund/policy/search constraints.
- `filterFlightList` narrows current context and requires `sessionId`.
- `rollbackTo(INIT)` can be a no-op if already at `INIT`; `resetBookingSession` is the safer recovery tool for dirty sessions.

## Update Rule

When Java source changes, update resources in this order:

1. `schemas/tool-contracts.json`
2. `schemas/state-machine.json`
3. `references/mcp-tool-map.md`
4. `workflows/*.md`
5. scripts only if payload shape or enums changed.
