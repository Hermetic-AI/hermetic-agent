# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **CardType self-registration** — base ships 4 protocol-level card types
  (`CHAT_FALLBACK` / `OD_INPUT` / `QUESTION` / `TODO_LIST`); business card types
  are registered by SKILLs at startup via `register_card_type(name)`.
  See `auip/_card_type_registry.py` and the new `auip/cards.py` design.
- 4-layer example SKILL at `work/shared/skills/example-echo-skill/` showing
  the registration pattern (`ECHO_RESULT` registered at import time).
- `docs/quickstart.md` — 5-minute local + Docker quick start.
- `docs/architecture.md` — 5-layer architecture with extension points.
- `docs/opencode-integration.md` — opencode SDK + event mapping table.
- `CONTRIBUTING.md` — dev env setup, code style, PR process, SKILL contribution rules.
- `LICENSE` (Apache-2.0) and `NOTICE` (third-party attributions).
- `CHANGELOG.md` (this file).
- `.github/workflows/ci.yml` — lint + mypy + pytest + skill validate on PR.
- `.github/workflows/release.yml` — Docker build + push on `v*` tag.

### Changed
- **`auip/cards.py` refactor** — `CardType` enum shrunk from 17 to 4 built-in values;
  business types removed from base. `Card.card_type` field is now `str` (validated
  against `BUILTIN_CARD_TYPES ∪ registered`). `CardType` retained as a backward-compat
  alias for `BuiltinCardType`. `CARD_TYPES_SET` is now a dynamic shim that always
  reflects the current registered set.
- **`auip/stream_interceptor.py`** — uses `card.card_type` (str) directly; no more
  `.value` access.
- **`auip/renderer.py`** — docstring example updated to show `register_card_type()`
  + `card_type="<registered_name>"` pattern.
- **`api/lifecycle/lifecycle.py`** — `ask_user` tool description updated to be
  business-agnostic; no more `FLIGHT_RESULT` / `FlightResultCard` references.
- **`scenarios/config.py`** — `card_schemas` comment updated; no more
  `flight_query` / `FLIGHT_RESULT` / `CANNOT_ORDER` example.
- **`README.md`** — full rewrite: 5-layer architecture, dual-SDK, SKILL system,
  CardType self-registration, Docker compose, error codes, 12 error codes.
- **License** — project relicensed from MIT (stated in old README) to Apache-2.0
  (consistent with `pyproject.toml`).

### Fixed
- `tests/test_auip_*` and related tests updated for the new CardType API.
- AUIP test suite: 65 → 65 passing, 0 regressions.

### Removed
- 14 business card types from the base `CardType` enum: `FLIGHT_RESULT`,
  `FLIGHT_LIST`, `CABIN_LIST`, `PASSENGER_FORM`, `OAT_BINDING`, `PRICE_VERIFY`,
  `POLICY_DECISION`, `ORDER_CONFIRM`, `ORDER_SUCCESS`, `CANNOT_ORDER`,
  `PRICE_LIST`, `RULE_DETAIL`, `PRICING_VERIFY`. These now belong to their
  owning SKILLs and are registered at startup.

## [0.1.0] - 2024-06-24

### Added
- Initial 5-layer architecture (api / scenarios / skill_runtime / providers / policy+store+config).
- Dual-SDK provider support (`opencode-ai` HTTP / `claude-agent-sdk` CLI).
- Unified chat entry (`POST /agent/chat` + `POST /agent/chat/stream`).
- SKILL system with progressive loading + token budget + state machine.
- AUIP card protocol with built-in types + business types (later refactored out).
- HITL via `SuspendableScheduler` + `TurnStore` checkpointing.
- Storage backends: memory / MySQL / PostgreSQL.
- Nacos config center + AI registry integration.
- Docker Compose stack (Hub + opencode-1 + optional frontend).
- 12 standardized error codes with actionable `detail` field.
- 5-layer CI check (`scripts/ci_check.py`) + unified chat entry check
  (`scripts/check_unified_chat_entry.py`).

[Unreleased]: https://github.com/lyzsniper/hermetic-agent/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/lyzsniper/hermetic-agent/releases/tag/v0.1.0
