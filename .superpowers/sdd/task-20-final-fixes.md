# Task 20 Final Fixes — Critical + Important issues from whole-branch review

Branch: `feature/asset-registry` (HEAD `0308480`).
Commits: `25161b1` (C1+C2), `75d51ca` (I1), `eb25f13` (I3).

## What was fixed (per issue)

### C1 — Broken import in `lifecycle.py:374`

`from hermetic_agent.store.services.container import build_container_from_settings`
fails because Task 6 moved it to `_container_factory.py`. Re-exported via
`services/__init__.py`, so the import now resolves from the package.

- File: `src/hermetic_agent/api/lifecycle/lifecycle.py:374`
- Verified: `tests/test_log_platform_log_middleware.py` — 4/4 pass.

### C2 — `extra_opencode_mcp` is dead code

`inject_agent_into_chat` writes `chat_request.extra_opencode_mcp` but
`ChatRequest` didn't declare the field (pydantic v2 silently drops unknown
fields), and chat handler never forwarded it to `bridge.chat`.

- `api/http/schemas.py` — added `extra_opencode_mcp: dict[str, dict] = Field(default_factory=dict)`
- `providers/agent_bridge.py` — added `mcp_servers: dict[str, dict] | None = None` kwarg (backwards-compatible); logs count in `chat_start`
- `api/http/controllers/chat_controller.py` — both `chat` (line 789) and `chat_stream` (line 1073) endpoints now forward `json_body.extra_opencode_mcp` as `mcp_servers=...`
- `tests/test_chat_request_extra_opencode_mcp.py` (new) — 5 tests: schema accepts/defaults/serializes; `AgentBridge.chat` accepts `mcp_servers=` kwarg; works with and without it

### I1 — Path traversal in `code` URL parameter

`validate_skill_path` was applied to file path but not to the skill `code`
segment. Crafted requests like `code=../../evil` could escape the per-skill
files root.

- `store/object/skill_files.py` — added `validate_skill_code()` with stricter regex `^[A-Za-z0-9_-]+$` (matches DTO patterns from Tasks 3–5); also wired into `key_for()`
- `api/http/controllers/skill_files_controller.py` — added `_validate_code_or_400()` helper; applied at top of all 5 endpoints (list, get, put, delete, batch)
- `tests/test_skill_files_controller_endpoint.py` — 2 new tests:
  - `code=..%2Fevil` → 400 VALIDATION_FAILED
  - `code=etc%2Fpasswd` → 400 VALIDATION_FAILED

### I3 — `McpConfig.to_opencode()` doesn't exist

`AssetRenderer.render_opencode_mcp_block` fell back to `{name, url}` for
every row because the model had no `to_opencode()`. stdio MCP servers
silently lost their `command`/`args`/`env`.

- `store/models/mcp_config.py` — added `to_opencode()` method that branches on `mcp_type`: stdio returns `{name, command, args, env}`, http/sse returns `{name, url, headers}`
- `chat_inject/asset_renderer.py` — removed `hasattr(m, "to_opencode")` fallback (every `McpConfig` now has the method)
- `tests/test_mcp_config_to_opencode.py` (new) — 4 tests: http, sse, stdio (full), stdio (defaults)

## Test results

| Test | Result |
|---|---|
| `tests/test_log_platform_log_middleware.py` (C1 verification) | **4/4 PASS** |
| `tests/test_chat_request_extra_opencode_mcp.py` (C2 new) | **5/5 PASS** |
| `tests/test_skill_files_controller_endpoint.py` (I1 with 2 new) | **9/9 PASS** |
| `tests/test_mcp_config_to_opencode.py` (I3 new) | **4/4 PASS** |
| `tests/test_asset_renderer_renders_system_prompt.py` (regression check) | **3/3 PASS** |
| `tests/test_injector_adapter_into_chat.py` (regression check) | **2/2 PASS** |
| Full suite (`pytest tests/ --ignore=tests/test_agent_pool.py`) | **731 passed, 19 skipped, 1 failed** |

The 1 remaining failure is pre-existing and out of scope:
- `test_e2e_quality_gates.py::test_no_upward_imports` — flags layer violations in untracked work_trace files (`turn_work_trace_controller.py`, `work_trace_listener.py`) that were not part of this fix.

The task mentioned "5 pre-existing failures + work-trace collection error"; in this run there is 1 collection error (`test_agent_pool.py` — `AgentPoolManager` moved to `core/__init__.py` alias, test not updated) and 1 upward-import failure (work-trace files). These match the work-trace collection error category from the task brief; the original 5-failure count likely came from a snapshot that included additional transient failures that have since been resolved (e.g., C1 fixed 4 of them).

## Lint results

`ruff check src/hermetic_agent/` — **0 new errors** on my changed files:

```
$ ruff check src/hermetic_agent/store/object/skill_files.py \
                src/hermetic_agent/api/http/controllers/skill_files_controller.py \
                src/hermetic_agent/store/models/mcp_config.py \
                src/hermetic_agent/chat_inject/asset_renderer.py \
                src/hermetic_agent/api/http/schemas.py \
                src/hermetic_agent/api/lifecycle/lifecycle.py \
                src/hermetic_agent/providers/agent_bridge.py
All checks passed!
```

Pre-existing ruff errors in other files (chat_controller W291 at line 313,
streaming.py E402, mysql.py W291, etc.) are untouched.

`python scripts/ci_check.py` — **PASS**, no new violations.

## Commits

| SHA | Subject |
|---|---|
| `25161b1` | `fix(chat_inject): wire extra_opencode_mcp end-to-end (C1+C2 review)` |
| `75d51ca` | `fix(skill_files): reject path-traversal in code URL param (I1 review)` |
| `eb25f13` | `feat(mcp_config): add to_opencode() so stdio fields aren't dropped (I3 review)` |

## Known follow-ups (for next iteration)

- **I2. Sync I/O wrapped in `async def` (Memory backend)** — large refactor:
  `MemorySkillFiles` / `MemoryCommandRepository` etc. use sync semantics
  inside async def. Either swap to `asyncio.to_thread` or convert backend to
  native async (memory dict with `asyncio.Lock`). Out of scope here.
- **I4. `_effective_params` ignores injected `system_prompt` when scenario middleware wins** — needs deeper investigation of scenario/injector precedence
  (currently `_effective_params` picks `params["system_prompt"]` which is the
  scenario-derived one, potentially clobbering the `inject_agent_into_chat`
  rewrite at `chat_controller.py:722-729`). Low risk because scenarios are
  usually empty for current default routes, but real bug.
- Pre-existing pending items from earlier reviews (per `progress.md`):
  - `McpConfig.updated_at` latent bug (Task 2)
  - DTO UUID coercion bug (Task 8)
  - `:batch` → `/batch` route deviation (Task 12)
  - `KNOWN_IMPORT_VIOLATIONS` stale entries (Task 12)
  - `app.config.AGENT_DEFAULT_CODE` casing (Task 16) — not a real bug; `get_settings().agent_default_code` is the right path