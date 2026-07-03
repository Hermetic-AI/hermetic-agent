# Asset Registry — Subagent-Driven Progress

Branch: `feature/asset-registry` (off `main` @ `dee148d`).
Plan files: `docs/designs/2026-06-30-asset-registry-plan{-2,-3,}.md`.
Spec: `docs/designs/2026-06-30-asset-registry-design.md`.
Tables: `docs/designs/2026-06-30-asset-registry-tables.md`.

Pre-flight note: Task 16 references `request.app.config["AGENT_DEFAULT_CODE"]` — should be `get_settings().agent_default_code` instead. Implementer will be told.

Phase / Task / status / commits.

- Task 1: complete (commits dee148d..1012b92, review clean; brief had internal contradictions — implementer added `created_at`/`updated_at` for sort, `_find()` for str/UUID key mismatch; reviewer approved).
- Task 2: complete (commits 1012b92..6b8e1d4, review clean; implementer used cleaner `await repo.create(s)` path; **flagged for final review**: pre-existing latent bug in `McpConfig.list` / `list_active` — they sort by `m.updated_at` but `updated_at` field is not on the `McpConfig` model; brief said 2 fields only so correctly out-of-scope).
- Task 3: complete (commits 6b8e1d4..131a22f, review clean; Memory subclass uses base-class inheritance to avoid brief's UUID-vs-str mismatch; MySQL `update` explicitly stamps `updated_at` because Tortoise `auto_now` doesn't trigger on `.update()`).
- Task 4: complete (commits 131a22f..721eea7, review clean; Command model has 15 fields per design doc §2.4, brief's "13" was a checklist typo; Memory base-class pattern continues; MySQL `update` stamps `updated_at`).
- Task 5: complete (commits 721eea7..952d20f, review clean; Agent model has 20 fields per design doc §2.5; same patterns as Task 3/4).
- Task 6: complete after fix (commits 952d20f..e2b4d02 → fix 49e84f1; review initially flagged Important issues — DSN regression in `_container_factory.py:74`, dead code block, duplicate import — all fixed; architecture approved, 12/12 new tests + 617/621 full suite green).
- Task 7: complete (commits 49e84f1..14481cc, review clean; ActorContextMiddleware correctly uses brief-mandated L1→L5 import; whitelist entry follows precedent set by `mcp_controller.py` / `skill_controller.py` / `scenarios/middleware.py`).
- Task 8: complete (commits 14481cc..81c5134, review clean with notes; **flagged for final review**: pre-existing DTO bug in `CommandResponse.from_model` / `AgentResponse.from_model` (UUID `id` not coerced to str; only affects in-memory repo path; tests wrap to compensate); also `trace_bp` registered in same commit — scope creep).
- Task 9: complete after fix (commits 81c5134..4ddb6bb → fix e96495e; review found Critical regression — new `list(actor=...)` replaced old `list()` signature, breaking `skill_controller.py:42` and `mcp_controller.py:40`; fix restored old `list()` and renamed new method to `list_for_actor`; 6/6 visibility tests pass; 684/684 full suite green).
- Task 10: complete (commits e96495e..9017db1, review clean; 14 settings fields + `MinioClient` + `build_asset_clients` factory + `pyproject.toml`/`requirements.txt` synced; created minimal `memory_skill_files.py` + `minio_skill_files.py` stubs since factory lazy-imports them — Task 11 fills in).
- Task 11: complete (commits 9017db1..b311b41, review clean; SkillFilesClient abstract + MemorySkillFiles + MinioSkillFiles full implementations replacing stubs; 12/12 path + sync tests pass; 696/696 full suite green).
- Task 12: complete (commits b311b41..bea0b1c, review clean with notes; **flagged for final review**: `:batch` → `/batch` route deviation due to Sanic `:` parsing rule; unnecessary `KNOWN_IMPORT_VIOLATIONS` entry for `skill_files_controller.py` — actually has zero L1→L5 imports; reviewer suggests cleaning up parallel stale entries).
- Task 13: complete (commits bea0b1c..211e466, review clean; AssetRenderer pure-function rendering with 3 tests; minor: no test for `to_opencode()` fallback path; `chat_inject/` not in `ci_check.py` LAYER_PATTERNS yet — manual 250-line cap respect).
- Task 14: complete (commits 211e466..41f01fe, review clean; AgentResolver 38-line wrapper; 4/4 tests pass; **flagged for final review**: `AgentService.update()` UUID/str key bug — discovered via Task 14 test workaround where implementer had to bypass `update()` and mutate `a.status` directly).
- Task 15: complete after fix (commits 41f01fe..2cbc37f → fix 9df62c6; review flagged Important — implementer silently changed `ReloadQueue` debounce from time-bucket to single-flight semantics while misreporting it as a bug fix; fix restored brief-intent time-bucket semantics; 4/4 tests pass).
- Task 16: complete (commits 9df62c6..988fd75, review clean; injector_adapter + 9-line addition to chat_controller.py; brief's `app.ctx.service_container` was wrong, implementer correctly used `app.ctx.services` per actual lifecycle.py; **flagged for final review**: only `chat` handler wired, `chat_stream` SSE not wired yet — silent skip for streaming clients; `AGENT_DEFAULT_CODE` casing mismatch — `app.config.AGENT_DEFAULT_CODE` doesn't exist, should use `get_settings().agent_default_code`).
- Task 17: complete after fix (commits 988fd75..67e312d → fix cc9f256; review found Important issue — Assets page was registered in App.tsx but no Sidebar button to navigate; fix added Sidebar button; 8 brief deliverables shipped + 6-line Sidebar fix).
- Task 18: complete after fix (commits cc9f256..cb36df7 → fix 0308480; review flagged race condition — `hermetic-agent` didn't `depends_on` `minio-init`, so hub started before bucket creation; fix added `service_completed_successfully` condition; docker-compose YAML valid).
- Task 19: complete (no NEW violations to fix; 716/716 baseline tests pass; 5 pre-existing failures unchanged; ruff + mypy + ci_check.py + check_unified_chat_entry.py all clean for new code; final review next).

## Final Review (Task 20)

- Task 20: complete (commits 0308480 → 25161b1 (C1+C2) → 75d51ca (I1) → eb25f13 (I3); full review in `.superpowers/sdd/task-20-final-fixes.md`).
  - C1: `lifecycle.py:374` import path fixed (Task 6 moved fn to `_container_factory.py`); 4/4 log_platform tests now pass.
  - C2: `ChatRequest.extra_opencode_mcp` declared; both `chat` + `chat_stream` endpoints forward to `bridge.chat(mcp_servers=...)`; new `AgentBridge.chat` kwarg; 5/5 round-trip tests pass.
  - I1: `validate_skill_code` + `_validate_code_or_400` helper applied to all 5 skill_files endpoints; 2 new traversal tests pass.
  - I3: `McpConfig.to_opencode()` branches on `mcp_type`; `asset_renderer` fallback removed; 4 new tests pass.
  - Full suite: 731 passed, 19 skipped, 1 pre-existing failure (`test_e2e_quality_gates.py::test_no_upward_imports` — untracked work_trace files).
  - No new ruff errors; ci_check.py clean.

## Known Follow-ups (post-Task 20)

- **I2.** Sync I/O wrapped in `async def` (Memory backend) — large refactor.
- **I4.** `_effective_params` ignores injected `system_prompt` when scenario middleware wins — needs deeper investigation of scenario/injector precedence.
- Pre-existing from earlier reviews:
  - `McpConfig.updated_at` latent bug (Task 2 reviewer)
  - DTO bug in `CommandResponse.from_model` / `AgentResponse.from_model` (UUID id not coerced to str) (Task 8 reviewer)
  - `:batch` → `/batch` route deviation (Task 12 reviewer)
  - `chat_stream` handler not wired for asset injection — **superseded by Task 20 C2 fix** (both endpoints now wire `extra_opencode_mcp`)
  - Unnecessary `KNOWN_IMPORT_VIOLATIONS` entries for `skill_files_controller.py` and parallel stale entries (Task 12 reviewer)
  - `app.config.AGENT_DEFAULT_CODE` casing mismatch (Task 16 reviewer)
  - MySQL implementations not tested against real DB (recurring pattern across Tasks 1–5)

