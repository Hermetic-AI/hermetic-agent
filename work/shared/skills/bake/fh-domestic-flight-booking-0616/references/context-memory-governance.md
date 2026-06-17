# Context Memory Governance

Use this file when deciding whether the latest user message should continue the
current flight-booking context or start a fresh search context. This complements
OpenCode's conversation memory strategy: use recent messages as working memory,
but re-derive task state from the latest user intent before reusing old facts.

## Principle

Treat flight booking state as scoped to one travel intent. A travel intent is
defined by route, travel date or date range, trip type, and booking stage. The
latest user message is authoritative when it introduces a new route, new date,
or a clear new search request.

Do not let old context silently contaminate a new search. Historical messages may
help resolve missing details only when they are compatible with the latest
intent.

## Context Buckets

Maintain these buckets conceptually:

- Search intent: departure city, arrival city, departure date, return date, trip
  type, cabin preference, filters, sort preference.
- Search result state: `sessionId`, listed flights, compacted option numbers,
  filters applied to the current list.
- Booking state: selected flight, selected cabin, passengers, trip application,
  cost center, contact, policy decision, order preview.
- Stable user profile hints: preferred passenger/contact only when explicitly
  provided in the current conversation and not contradicted by the latest
  message.

Only search intent may be partially inherited, and only after the checks below.
Search result state and booking state are never valid across a different route,
date, or trip type.

## Continue Existing Context

Continue the current context only when the latest message is a refinement,
selection, or booking step for the same search, for example:

- "只看早上的"
- "帮我筛一下直飞"
- "选第 2 个"
- "就订这个"
- "换成经济舱"
- "看一下退改签"

In continuation mode:

- Reuse the current `sessionId` only if the route, date, trip type, and result
  list still match the latest intent.
- Use `filterFlightList` for list-local refinements.
- Use `queryFlightBasic` again for route, date, trip type, cabin/refund/policy,
  or other core search changes.
- Preserve booking state only while the selected flight and cabin remain valid.

## Start A New Search Context

Start a new search context when the latest message provides a new origin and
destination, a new travel date, or asks for another flight search that is not a
minor refinement of the current result set.

Examples:

- Previous: "查上海到东京的机票". Latest: "再查长沙到南昌的机票".
- Previous: "查北京到上海明天的机票". Latest: "改查广州到成都后天".
- Previous: selected a flight. Latest: "查一下下周一深圳到杭州".

In new-search mode:

- Discard previous `sessionId`, listed flights, option indexes, selected flight,
  selected cabin, price verification, policy decision, and order preview.
- Rebuild search intent from the latest user message first.
- Inherit only explicitly compatible missing facts. For example, if the user says
  "同样日期再查长沙到南昌", the date may be inherited, but the old route,
  results, and booking state must be discarded.
- If the latest message already contains departure city, arrival city, and date,
  call `queryFlightBasic` directly after local date normalization.
- If required fields are missing, ask only for those missing fields with
  `OD_INPUT`; do not ask the user to restate fields already present in the latest
  message.

## Conflict Resolution

When latest-message facts conflict with history, prefer the latest message.

- New departure or arrival city overrides old route.
- New departure date or return date overrides old dates.
- "改查", "重新查", "再查", "换成", "查一下 X 到 Y" usually indicates a new
  search if it changes route/date/trip type.
- "同一天", "同样时间", "还是明天" may inherit only that named compatible field.
- A selected option number like "选第 2 个" applies only to the current visible
  list; if a new search has started or the visible list is ambiguous, ask the
  user to choose from the new list instead of using an old option number.

## Ambiguity Handling

Ask a concise clarification only when reuse would be unsafe and the latest
message lacks required fields.

Good clarification:

- "你是要继续筛选刚才北京到上海的结果，还是重新查询长沙到南昌？如果重新查，请补充出发日期。"

Avoid clarification when the latest message is already complete. For example,
"查长沙到南昌明天的机票" must trigger a fresh `queryFlightBasic` call, not a question
about whether to continue the old Shanghai-Tokyo search.

## Compaction Notes

When summarizing or compacting conversation state, preserve only the active
travel intent and active MCP state. Mark stale contexts as closed instead of
mixing them into the active state.

Suggested compact state shape:

```json
{
  "activeIntent": {
    "departureCity": "长沙",
    "arrivalCity": "南昌",
    "departureDate": "2026-06-12",
    "tripType": "oneWay"
  },
  "activeSessionId": "session-for-current-search-only",
  "stage": "FLIGHT_LISTED",
  "staleContexts": [
    {
      "route": "上海-东京",
      "status": "closed_by_new_search"
    }
  ]
}
```

Never compact multiple historical routes into one active route/date/session.
