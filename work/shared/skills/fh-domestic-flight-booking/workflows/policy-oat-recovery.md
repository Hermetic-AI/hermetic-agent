# Policy, OAT, And Recovery Workflow

## OAT Fields

OAT is a substep layer orthogonal to the main stage. Java enum values include:

`AWAIT_PASSENGERS -> NEED_TRIP_BIND -> NEED_COST_CENTER -> NEED_CONTACT -> OAT_READY`

The current implementation may jump from passenger fill to OAT ready. Trust MCP's returned missing-field messages over this reference.

## Policy Overrun

After `validateBookingInfo`, do not reinterpret the policy rules in the skill. Present MCP/UI options and call `recordPolicyUserDecision` only with a code exposed by MCP or UI payload.

When the user must decide how to handle an overrun, call `ask_user` with
`card_type=POLICY_DECISION`. Put the available choices in top-level
`decision_buttons[]`; each button should include `id`, `label`, and the MCP
decision `code` if one is provided. Include `surcharge` only when MCP exposes a
numeric surcharge.

Possible user paths:

- Continue/pay/accept: record the matching decision code and validate/preview again.
- Choose lower-price alternative: call `chooseAlternativeCabin` if a `cabId` is present, otherwise return to search/filter/choose.
- Transfer human: record transfer code if available, then stop automated booking.
- Abort/reselect: return to `FLIGHT_LISTED` workflow or reset by user confirmation.

## Price Change

If validation reports price change, show original price, current price, and the user action required. Continue only after explicit user acceptance or MCP-provided action result.

Use `ask_user` with `card_type=PRICE_VERIFY` and top-level `current_price`,
`original_price`, `price_diff`, and `policy_overrun` when explicit user
acceptance is required.

## Recovery

Use `resetBookingSession` when:

- The user says restart, clear, change whole itinerary, or context is wrong.
- MCP reports session context mismatch and requery cannot repair it.
- A selected flight/cabin no longer exists and the user wants a clean start.

Do not reset silently after a single transient MCP error.

If recovery cannot continue in the current conversation, call `ask_user` with
`card_type=CANNOT_ORDER`, top-level `reason`, and `fallback` before ending the
flow.
