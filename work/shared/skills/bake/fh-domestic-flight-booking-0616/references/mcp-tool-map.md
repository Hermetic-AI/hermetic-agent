# MCP Tool Map

The Java annotations under `src/main/java/fh/travel/mcp` are authoritative. This map is a compact planning index.

## L0 Preparation

- `checkProductAccess(sessionId)`: check domestic flight booking permission and write enterprise config into context.
- `resetBookingSession(sessionId)`: clear dirty booking context when user restarts or context is inconsistent.

## L1 Search

- `queryFlightBasic(departureCity, arrivalCity, departureDate, ...)`: TMS domestic flight search. Use for first search and all core search changes.
- `filterFlightList(sessionId, ...)`: local filtering of current context list. Use after `queryFlightBasic`, not as a replacement for changed OD/date/cabin/refund/policy search.
- Helpers: `getDateInfo(date)`, `listUpcomingHolidays(limit)`, `getHolidayDate(holidayName)`.

Key `queryFlightBasic` option values:

- `roundTripListMode`: `RECOMMENDED` or `FREE`.
- `cabinClass`: `ECONOMY`, `FULL_ECONOMY`, `BUSINESS`, `FIRST`.
- `departureDayPart`: `MORNING`, `AFTERNOON`, `EVENING`.
- `sortBy`: `PRICE`, `ARRIVAL_TIME`, `DURATION`, `REFUND_FLEXIBILITY`.
- Boolean filters: `cheapest`, `baggage`, `requireMeal`, `nonStop`, `freeRefund`, `refundable`, `policyCompliant`.

## L2 Flight Selection

- `chooseFlight(sessionId, index?, flightNo?, listView?)`: select a flight and load cabins.
- `getFlightPolicyInfo(sessionId, index)`: read details for refund/change, baggage, meal, and fee information without advancing booking stage.

Use `listView` only when selecting from a recommendation block; otherwise prefer the displayed list index or exact `flightNo`.

## L3 Cabin Selection

- `chooseCabin(sessionId, index?, cabinName?, cabId?, price?)`: choose cabin for the selected flight.
- `chooseAlternativeCabin(sessionId, cabId)`: choose a policy-compliant or lower-price alternative cabin when MCP exposes one.

Prefer identifiers in this order: `cabId`, `index`, `cabinName`, `price`.

## L4 OAT And Passenger Data

- `listTripApplications(sessionId, destCity?, departDate?)`: list applicable trip applications.
- `getTripApplicationDetail(sessionId, tripApplicationId)`: bind one trip application.
- `listCostCenters(sessionId)`: list selectable cost centers.
- `bindCostCenter(sessionId, costCenterId, costCenterName?)`: bind selected cost center.
- `getDefaultContact(sessionId)`: load default contact.
- `fillPassenger(sessionId, names, phone?, idType?, idNo?)`: bind passengers; pass `本人` for self/default passenger intent.

## L5 Validation And Preview

- `validateBookingInfo(sessionId)`: validate passenger, cabin, enterprise fields, price, and policy.
- `recordPolicyUserDecision(sessionId, decisionCode)`: record overrun or price decision. Use only codes presented by MCP/UI payload.
- `buildOrderPreview(sessionId)`: create order preview/order save payload after validation.

## L6 Existing Order

- `getOrderDetail(orderId)`: query existing order details.

## Planning Rule

All stateful booking tools require `sessionId` except calendar helpers and `getOrderDetail`. If a tool returns missing context, recover by requerying with the same session or resetting by explicit user intent.
