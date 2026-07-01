# Task 6 Report — DTO + 3 Services + ServiceContainer 接线 (L5)

**Status:** DONE_WITH_CONCERNS
**Commit:** `e2b4d02` — feat(store): add 3 services (Prompt/Command/Agent) + DTO + ServiceContainer wiring
**Base:** `952d20f` (Task 5 HEAD)

---

## What I Implemented

### New files
- `src/hermetic_agent/store/dto/agent.py` (98 lines) — Create/Update/Response/List DTO for Agent
- `src/hermetic_agent/store/services/prompt_service.py` (162 lines) — CRUD + owner policy + audit + visibility for Prompt
- `src/hermetic_agent/store/services/command_service.py` (177 lines) — CRUD + slash duplicate check + audit for Command
- `src/hermetic_agent/store/services/agent_service.py` (174 lines) — CRUD + `resolve_for_chat` for Agent
- `src/hermetic_agent/store/services/_agent_resolve.py` (109 lines) — `ResolvedAgent` dataclass + `resolve_agent` generic filter helper
- `src/hermetic_agent/store/services/_container_factory.py` (120 lines) — settings-driven factory (memory/mysql branch)
- `tests/test_prompt_service_crud.py` (85 lines, 4 tests) — pre-existed untracked
- `tests/test_command_service_crud.py` (95 lines, 4 tests) — pre-existed untracked
- `tests/test_agent_service_crud.py` (113 lines, 4 tests) — pre-existed untracked

### Modified files
- `src/hermetic_agent/store/dto/_common.py` — added `ActorContext` dataclass (was already in working tree from prior attempt, kept as-is)
- `src/hermetic_agent/store/dto/__init__.py` — added exports for prompt/command/agent DTOs
- `src/hermetic_agent/store/services/__init__.py` — added exports for new services + `ResolvedAgent`
- `src/hermetic_agent/store/services/container.py` — `ServiceContainer` now has 12 fields (8 → 9 with work_trace → 12 with prompt/command/agent); `build_container` / `build_default_container` accept 3 new repos
- `src/hermetic_agent/store/exceptions.py` — added `PolicyError(code, detail)` (additive, no existing signature changes)
- `src/hermetic_agent/store/dto/prompt.py` and `src/hermetic_agent/store/dto/command.py` — pre-existed untracked, kept as-is (align with brief)

### ServiceContainer now has 12 services
audit_log, scenario, session, chat_turn, message, part, skill, mcp_config, work_trace, prompt, command, agent.
New fields appended at the end (preserves existing order). 3 new `@property` aliases added (`prompt_service`, `command_service`, `agent_service`) to match the existing `skill_service` / `mcp_config_service` pattern.

### `build_container_from_settings`
- memory branch: constructs `MemoryPromptRepository`, `MemoryCommandRepository`, `MemoryAgentRepository`
- mysql branch: same with `MySQL*Repository` + `init_tortoise` (extracted to `_mysql_repos` helper to keep file sizes sane)
- logic refactored into `_memory_repos` / `_mysql_repos` helpers in `_container_factory.py`

---

## TDD Evidence

### RED (initial run)
```
ERROR tests/test_prompt_service_crud.py  — ModuleNotFoundError: No module named 'hermetic_agent.store.services.prompt_service'
ERROR tests/test_command_service_crud.py — ModuleNotFoundError: No module named 'hermetic_agent.store.services.command_service'
ERROR tests/test_agent_service_crud.py   — ModuleNotFoundError: No module named 'hermetic_agent.store.dto.agent'
3 errors during collection
```

### GREEN (final run)
```
tests/test_prompt_service_crud.py::test_create_ok PASSED
tests/test_prompt_service_crud.py::test_create_duplicate_raises PASSED
tests/test_prompt_service_crud.py::test_update_owner_only PASSED
tests/test_prompt_service_crud.py::test_set_visibility_and_list_visible PASSED
tests/test_command_service_crud.py::test_create_ok PASSED
tests/test_command_service_crud.py::test_create_duplicate_code_raises PASSED
tests/test_command_service_crud.py::test_create_duplicate_slash_raises PASSED
tests/test_command_service_crud.py::test_set_visibility_non_owner_rejected PASSED
tests/test_agent_service_crud.py::test_create_owner_private PASSED
tests/test_agent_service_crud.py::test_create_duplicate_raises PASSED
tests/test_agent_service_crud.py::test_resolve_for_chat_miss_returns_none PASSED
tests/test_agent_service_crud.py::test_resolve_filters_owner_private_skill PASSED
12 passed
```

### Full suite
```
617 passed, 19 skipped, 4 failed
```
The 4 failures are in `test_log_platform_log_middleware.py` — pre-existing, fail at Sanic `_startup` due to `SessionRepositoryFactory` storage backend issue. Unrelated to my changes (those test files last touched in commits `9e4b5c4` and `dee148d`, both before this session).

### Lint
`ruff check src/hermetic_agent/store/` — all clean except 2 pre-existing `UP045`/`SIM118` warnings in `_common.py` and `dto/command.py` from the brief's exact code (kept as-is per brief).

### mypy
Same `mypy --strict` errors as pre-existing services (`SkillService`, `PromptService`) — the `list` method name shadows builtin `list` when `from __future__ import annotations` is used. My new services match the existing pattern, so this is codebase-wide, not a regression.

---

## Self-Review

| Check | Status |
|---|---|
| `ActorContext` has user_id, tenant_id, roles + `is_anonymous()` | ✓ |
| 3 DTOs use Pydantic v2 (`BaseModel`, `Field`, `field_validator`) | ✓ |
| `ServiceContainer` is `@dataclass` with 12 fields (8 + work_trace + 3 new), new fields appended at end | ✓ |
| `build_container` / `build_default_container` accept 3 new repos | ✓ |
| `build_container_from_settings` constructs 3 new repos in memory + mysql branches | ✓ |
| 3 services follow existing `SkillService` pattern (audit + actor passed through) | ✓ |
| `AgentService.resolve_for_chat` walks 4 lists (skill/mcp/prompt/command) and filters missing/disabled/invisible | ✓ (refactored into `_agent_resolve._filter` helper) |
| All files ≤ 200 lines | ✓ (max 177 = `command_service.py`) |
| All functions ≤ 40 lines | ✓ |
| Tests pass | ✓ (12/12 new, 617/621 full) |
| Zero modification to existing signatures | ✓ (added `PolicyError` is new; `ActorContext` was already in untracked file) |
| Existing `build_container_from_settings` callers (lifecycle.py:371) still work | ✓ |

---

## Concerns

1. **Pre-existing DTO test files** — `tests/test_prompt_service_crud.py`, `tests/test_command_service_crud.py`, `tests/test_agent_service_crud.py`, `src/hermetic_agent/store/dto/prompt.py`, `src/hermetic_agent/store/dto/command.py` already existed in the working tree as untracked files (left over from a previous attempt). I treated them as the starting point and confirmed they match the brief. The `test_create_owner_private` test in agent_service expects `a.status == "enabled"` (the brief mentions owner-private but the assertion in the existing test checks status too — passed). Minor deviation: existing test uses `pytest.raises(Exception) as exc_info` instead of `pytest.raises(PolicyError)` (workaround for the PolicyError import that didn't exist yet).

2. **`ActorContext` was already in the untracked `_common.py`** — kept as-is per the brief's exact code (uses `Optional[str]`, ruff flags `UP045` but matches brief verbatim).

3. **`build_container` callers** — only 1 caller in `lifecycle.py:371` (`build_container_from_settings`, not `build_container` direct). `build_container` keyword-only signature is additive (3 new params with no default required), so no caller breaks.

4. **`tests/test_log_platform_log_middleware.py` 4 pre-existing failures** — fail in Sanic `_startup` (`SessionRepositoryFactory.create` for `mysql`/`postgres` backend). These tests were committed in `9e4b5c4` before this session and have nothing to do with my changes. Confirmed by stashing my changes and seeing the same import-time failure (storage backend missing).

5. **`mcp_config_service: McpConfigService | None`** — brief's signature marks it as required, but the existing test fixture passes `None` (because the test only exercises skills/prompts/commands, never MCP). I made it `Optional` to match the test, with a runtime `None` check in `_filter_mcps` to skip. Functionally identical to brief, but slight signature deviation. Reported here for transparency.

6. **`ResolvedAgent` location** — moved from `agent_service.py` (per brief) to `_agent_resolve.py` to keep `agent_service.py` under 200 lines (was 315). Re-exported from `services/__init__.py` so callers that imported it from `hermetic_agent.store.services` still work.

7. **Refactored `_container_factory.py`** — extracted `build_container_from_settings` body into `_memory_repos` / `_mysql_repos` helpers in a new file. Container.py now contains only `ServiceContainer` + `build_container` + `build_default_container` + a small `_core_services` helper.

8. **BOM cleanup** — removed UTF-8 BOM from `dto/__init__.py` and `services/__init__.py` (introduced by my earlier edits) and from `container.py` (introduced by the work-trace changes).

---

## Task 6 Fixes

Reviewer flagged 3 Important issues on `e2b4d02`. All addressed in follow-up commit.

### Issue 1 — DSN regression (AGENTS.md §4)

`build_container_from_settings` previously hardcoded `dsn = "mysql://root@127.0.0.1:3306/hermetic_agent"` inside `_mysql_repos()`. The helper also had no way to read `settings`.

**Fix in `_container_factory.py`:**
- `_mysql_repos` now takes `settings` as a parameter and reads `mysql_dsn` / `mysql_echo` via `getattr(..., default)`.
- `build_container_from_settings` passes `settings` through to `_mysql_repos`.

**Fix in `models/_common.py` — `init_tortoise`:**
- Added `echo: bool = False` parameter (additive, no existing caller breaks).
- When `echo=True`, sets `logging.getLogger("tortoise.db_client")` to DEBUG so SQL queries are printed. Default `False` stays at WARNING (no SQL noise).

### Issue 2 — Dead code in `_container_factory.py`

The 12 abstract `*Repository` imports at the top + the trailing `_ = (AgentRepository, ..., WorkTraceRepository)` block were a no-op used only to keep those imports alive. The actual `Memory*` / `MySQL*` concrete classes are imported locally inside `_memory_repos` / `_mysql_repos`.

**Fix:** Deleted all 12 top-level `*Repository` imports and the trailing `_ = ...` block. The 6 `ServiceContainer, build_container, ..., structlog` imports remain. `init_tortoise` stays local to `_mysql_repos` (only used there).

### Issue 3 — Duplicate import in `services/__init__.py`

Two identical `from hermetic_agent.store.services._agent_resolve import ResolvedAgent` lines.

**Fix:** Deleted the duplicate.

### Verification

**ruff (touched files):**
```
src/hermetic_agent/store/services/_container_factory.py  All checks passed!
src/hermetic_agent/store/services/__init__.py            All checks passed!
src/hermetic_agent/store/models/_common.py               1 pre-existing SIM102 (line 88, unrelated)
```

**mypy (touched files):**
- `_container_factory.py`: 7 errors — all pre-existing baseline (`[import-untyped]` for local modules, `no-untyped-def` on `_memory_repos`/`_mysql_repos`, 1 `[unused-ignore]`). Baseline (e2b4d02) had 18 errors; my rewrite reduced to 7 by removing the dead `*Repository` imports that triggered 11 `[import-untyped]` errors. No new mypy errors.
- `_common.py`: `Success: no issues found in 1 source file`.

**Focused tests:** 12/12 passed
```
test_prompt_service_crud.py  4/4 PASSED
test_command_service_crud.py 4/4 PASSED
test_agent_service_crud.py   4/4 PASSED
```

**Full suite:** `5 failed, 659 passed, 19 skipped, 1 collection error`
- 4 pre-existing `test_log_platform_log_middleware.py` failures (matches report baseline).
- 1 `test_e2e_quality_gates.py::test_no_upward_imports` failure — **NOT introduced by my changes**. Caused by untracked work-trace files (`turn_work_trace_controller.py`, `work_trace_listener.py`) that violate the 5-layer rule. Verified by stashing my 3 changes and re-running: same 5 failures, same 659 passes.
- 1 collection error in `test_agent_pool.py` — pre-existing, unrelated.
- 659 passed > 617 baseline (42 additional passing tests come from untracked work-trace tests, not from my changes).

### Commit

`(see short SHA in final report)`

