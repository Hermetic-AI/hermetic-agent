# Progressive Search Workflow

Use for "find flights", "cheapest flight", "morning flight", "direct flight", and similar queries.
Use native MCP tools only. Authentication is already configured by the runtime;
do not ask for tokens, mention tokens, call MCP through Bash/curl, or delegate
flight search to the `task` subagent.

## 0. Fast Path

If the latest user message already contains departure city, arrival city, and a
departure date or relative date, call `queryFlightBasic` first. Do not call
`ask_user`, `question`, `skill`, `glob`, `read`, `grep`, `getDateInfo`,
`checkProductAccess`, or helper scripts before the first search.

For "帮我查一下北京到上海明天的单程机票" on 2026-06-09, call:

```json
{"departureCity":"北京","arrivalCity":"上海","departureDate":"2026-06-10"}
```

Treat cabin class as a result-selection concern unless the native MCP schema
supports a `cabinClass` argument. Never ask for cabin class before this first
search.

## 1. Parse And Gather Minimal Search Inputs

First parse the user's message and conversation history. Treat explicit city,
date, cabin class, passenger, time bucket, airline, price, baggage, meal,
refund, direct-flight, and policy preference as usable structured facts. Do not
ask the user to repeat facts that are already present.

Required:

- departure city
- arrival city
- departure date as `yyyy-MM-dd`

Optional:

- return date
- cabin class
- cheapest only
- airline include/exclude
- departure time bucket or time range
- direct flight
- max price
- baggage/meal/refund/policy filters
- sort preference

Ask only for missing required fields. If departure city, arrival city, and
departure date are already known, skip `ask_user` and call `queryFlightBasic`
directly. Use the helper only when normalization is not obvious from the current
conversation date:

```powershell
python skills\fh-domestic-flight-booking\scripts\normalize_request.py plan.json
```

If required fields are missing, call `ask_user` with `card_type=OD_INPUT`.
Use Chinese card title and labels. Put only the missing fields in top-level
`fields[]`, with ids such as `departureCity`, `arrivalCity`, and
`departureDate`.

## 2. Call Search

Use `queryFlightBasic` for first search. Include all strong filters known at this point. Use `returnDate` for round trip. Use `roundTripListMode=FREE` only when the user explicitly wants separate outbound/return choices.

## 3. Compact Result

Run:

```powershell
python skills\fh-domestic-flight-booking\scripts\compact_mcp_payload.py result.json --limit 8
python skills\fh-domestic-flight-booking\scripts\render_options.py compact.json
```

Show top options and mention omitted count if any. Do not expose raw vendor fields.

Return options through AUIP:

- Preferred: call `ask_user` with `card_type=FLIGHT_RESULT`, `title`, and
  `body.summary` plus `body.plans[]`.
- If the user needs one plain list instead of grouped plans, call `ask_user`
  with `card_type=FLIGHT_LIST` and top-level `flights[]`.
- If MCP returns no usable option, call `ask_user` with
  `card_type=CANNOT_ORDER`, `reason`, and `fallback`.

## 4. Refine

- Use `filterFlightList` for local narrowing: max price, airline, exclude airline, day part, non-stop, meal, plane size, max duration, cheapest.
- Use `queryFlightBasic` again for route/date/cabin/refund/policy/core search changes.
- Use `getFlightPolicyInfo` when the user asks about refund/change, baggage, meal, or fees for a specific option.

## 5. Move To Booking

When the user chooses "book this", "select number N", or a flight number, load `workflows/booking-mainline.md`.
