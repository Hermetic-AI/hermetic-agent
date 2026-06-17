# Booking Mainline Workflow

Use after the user chooses a flight or wants to continue to booking. Covers business flow Steps 2–3: product selection and data filling.

Precondition: Product access has been verified. See `workflows/intent-and-permission.md`.

## 0. Verify Product Access

If not yet checked in this session, call `mcporter_feihe-travel__checkProductAccess(sessionId)`.

If access is denied, call `ask_user` with `card_type=CANNOT_ORDER` and `reason: "未开通国内机票预订权限"`. Do not proceed further. See `workflows/intent-and-permission.md` for full details.

## 1. Select Flight

Precondition: stage should be `FLIGHT_LISTED` or `FLIGHT_SELECTED`.

Call `mcporter_feihe-travel__chooseFlight` with `index` or `flightNo`.

Use `flightNo` if the user names a flight number. Use `listView` only for recommendation-block choices.

## 2. Select Cabin

After `chooseFlight`, show compact cabin options. Call `mcporter_feihe-travel__chooseCabin` with the most stable available selector:

1. `cabId`
2. `index`
3. `cabinName`
4. `price`

Present cabin choices by calling `ask_user` with `card_type=CABIN_LIST` and `body.contentJson.dataList` containing an `AIR_DOMESTIC_CABIN_LIST` block. Each cabin item should include `cabId` when MCP provides it, plus `title` or `name`, `subtitle`, `price`, and `tags`.

## 3. Fill Passenger

Call `mcporter_feihe-travel__fillPassenger(sessionId, names, ...)`. For self/default passenger, pass `本人`. For multiple passengers, comma-separate names.

If passenger data is missing, call `ask_user` with `card_type=PASSENGER_FORM` and top-level `fields[]`.

`checkProductAccess` (Step 0) already verifies booking permission. If `fillPassenger` or `validateBookingInfo` later reports passenger data permission issues, report via `ask_user` with `card_type=CANNOT_ORDER`.

## 4. Fill Enterprise/OAT Data

If enterprise config is unknown, call `mcporter_feihe-travel__checkProductAccess(sessionId)` (already done in Step 0).

If required by MCP result or context:

- Trip application: `mcporter_feihe-travel__listTripApplications` → `mcporter_feihe-travel__getTripApplicationDetail`.
- Cost center: `mcporter_feihe-travel__listCostCenters` → `mcporter_feihe-travel__bindCostCenter`.
- Contact: `mcporter_feihe-travel__getDefaultContact`.

Do not invent IDs for trip applications or cost centers.

When the user must choose or fill enterprise data, call `ask_user` with `card_type=OAT_BINDING`. Use `options[]` for choices and `fields[]` for manual input.

## 5. Next: Validate and Submit

After passenger and OAT data are filled, load `workflows/order-submit.md` for:
- Policy and risk validation (`validateBookingInfo`)
- Policy overrun and price change handling
- Order submission (`buildOrderPreview`)
- Order confirmation and completion