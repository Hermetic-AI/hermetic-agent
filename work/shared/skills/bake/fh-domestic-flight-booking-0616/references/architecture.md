# Architecture

## Role Split

This skill is an execution guide for an OpenCode agent. It should not become a shadow booking engine.

- OpenCode agent: understands user intent, chooses the next resource, calls scripts, invokes MCP tools, and asks for missing confirmations.
- Skill: stores stable workflow knowledge, schema contracts, and deterministic utility scripts.
- fh-travel MCP: owns tool behavior and side effects. Java source path: `src/main/java/fh/travel/mcp`.
- Java booking runtime: owns Redis context, state transitions, policy mapping, validation, and order preview. Main package: `fh.travel.ai.busi.air.domestic.booking`.

## Public Layer Extracted Into Skill

The reusable layer contains only non-authoritative helpers:

- `schemas/tool-contracts.json`: compact MCP tool index for agent planning.
- `schemas/state-machine.json`: state names and legal high-level flow copied from Java source for guard checks.
- `schemas/booking-plan.schema.json`: normalized user plan before MCP mutation.
- `schemas/compact-flight.schema.json`: output shape for model-friendly flight options.
- `scripts/normalize_request.py`: date/time/cabin normalization and plan validation.
- `scripts/compact_mcp_payload.py`: remove noisy MCP fields and keep decision fields.
- `scripts/stage_guard.py`: pre-call stage guard from schema.
- `scripts/render_options.py`: render compact options for progressive disclosure.

## What Must Stay In MCP/Java

Do not implement these in the skill:

- TMS flight search or fare logic.
- Redis `AirDomesticBookingContext` persistence.
- `AirDomesticBookingContext.advanceTo` and `rollbackTo` behavior.
- Policy overrun computation and decision-code effects.
- Passenger authorization and default contact lookup.
- Order save/preview idempotency.

## Progressive Disclosure

The agent should reveal information in layers:

1. Search summary: count, cheapest price, top options.
2. Comparison fields: airline, time, duration, price, stops, baggage/meal.
3. Details: refund/change rules, policy, cabin ids, cost center/trip application fields.
4. Commit step: validation result and order preview.

Large MCP payloads should never be pasted directly into the conversation.
