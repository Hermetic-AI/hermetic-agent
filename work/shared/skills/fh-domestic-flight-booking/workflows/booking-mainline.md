# Booking Mainline Workflow

Use after the user chooses a flight or wants to continue to booking.

## 1. Select Flight

Precondition: stage should be `FLIGHT_LISTED` or `FLIGHT_SELECTED`.

Call:

```json
{"tool":"chooseFlight","arguments":{"sessionId":"...","index":1}}
```

Use `flightNo` if the user names a flight number. Use `listView` only for recommendation-block choices.

## 2. Select Cabin

After `chooseFlight`, show compact cabin options. Call `chooseCabin` with the most stable available selector:

1. `cabId`
2. `index`
3. `cabinName`
4. `price`

Present cabin choices by calling `ask_user` with `card_type=CABIN_LIST` and
top-level `cabins[]`. Each item should include `cabId` when MCP provides it,
plus `title` or `name`, `subtitle`, `price`, and `tags` when available.

## 3. Fill Enterprise/OAT Data

If enterprise config is unknown, call `checkProductAccess`.

If required by MCP result or context:

- Trip application: `listTripApplications` -> `getTripApplicationDetail`.
- Cost center: `listCostCenters` -> `bindCostCenter`.
- Contact: `getDefaultContact`.

Do not invent IDs for trip applications or cost centers.

When the user must choose or fill enterprise data, call `ask_user` with
`card_type=OAT_BINDING`. Use top-level `options[]` for choices and top-level
`fields[]` for manual input.

## 4. Fill Passenger

Call `fillPassenger(sessionId, names, ...)`. For self/default passenger, pass `本人`. For multiple passengers, comma-separate names.

If passenger data is missing, call `ask_user` with
`card_type=PASSENGER_FORM` and top-level `fields[]`.

## 5. Validate

Call `validateBookingInfo`. Outcomes:

- Success/no overrun: continue to preview.
- Missing fields: ask only for those fields, then fill and validate again.
- Policy overrun or price change: load `workflows/policy-oat-recovery.md`.

For a price change, call `ask_user` with `card_type=PRICE_VERIFY` and
top-level `current_price`, `original_price`, and `price_diff`.

## 6. Build Preview

Call `buildOrderPreview` only after validation is acceptable. Present order preview summary and wait for frontend/user final confirmation if the product flow requires it.

Present the final preview by calling `ask_user` with
`card_type=ORDER_CONFIRM`, top-level `order_summary`, and `total_price`.
After the backend confirms the order, call `ask_user` with
`card_type=ORDER_SUCCESS` and `order_no` or `order_summary`.
