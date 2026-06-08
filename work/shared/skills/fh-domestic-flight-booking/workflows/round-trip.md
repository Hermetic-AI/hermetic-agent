# Round Trip Workflow

Use when the user requests a return trip.

## RECOMMENDED Mode

Default mode. Use when the user wants packaged outbound/return recommendations.

Call `queryFlightBasic` with:

- `departureDate`
- `returnDate`
- `roundTripListMode=RECOMMENDED` or omit if default

After selecting a recommended group, `chooseFlight` can bind the packaged choice and load cabins.

## FREE Mode

Use only when the user explicitly wants independent outbound and return selection, such as "book the outbound first" or "I want to choose the return separately".

Call `queryFlightBasic` with:

- `departureDate`
- `returnDate`
- `roundTripListMode=FREE`

Expected behavior from Java context:

- Outbound cabin selection can move the flow back to `FLIGHT_LISTED` for return-leg work.
- Keep the same `sessionId`.
- Do not reset between outbound and return unless user explicitly restarts.

## Display

For round-trip options, compact each option with both outbound and return times/prices when present. If the payload does not expose return fields, show the fields available and rely on MCP details before selection.
