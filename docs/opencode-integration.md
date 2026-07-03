# opencode integration

> How hermetic-agent integrates with the [opencode](https://github.com/sst/opencode)
> SDK — install, event mapping, custom Provider writing.

---

## 1. Why opencode?

opencode is an open-source LLM coding agent that ships a programmatic SDK
([`opencode-ai`](https://pypi.org/project/opencode-ai/)) and a `serve` mode
that exposes its session / event API over HTTP. hermetic-agent wraps it as its
default Provider, with a clean event-mapping layer that any L4 adapter can
replicate.

Alternatives supported by hermetic-agent:

- `opencode-ai` (HTTP, **default**)
- `claude-agent-sdk` (CLI subprocess, optional, install with `pip install hermetic-agent[claude]`)

---

## 2. Install

### 2.1 The `opencode` CLI / daemon

The Hub calls `opencode serve` (typically inside a Docker sandbox). Install:

```bash
# macOS
brew install sst/tap/opencode

# Linux
curl -fsSL https://opencode.ai/install | bash

# Windows
irm https://opencode.ai/install.ps1 | iex

# Verify
opencode --version
```

### 2.2 The Python SDK

```bash
# With hermetic-agent
uv pip install -e ".[dev]"
# or
pip install -e ".[dev]"

# opencode-ai is a transitive dep of hermetic-agent
# (pinned to opencode-ai>=0.1.0a0 in pyproject.toml)
```

### 2.3 Quick verification

```bash
# Start opencode serve locally
opencode serve --port 4096 --hostname 127.0.0.1

# In another terminal
curl http://localhost:4096/global/health
# {"ok":true}
```

Then point hermetic-agent at it:

```bash
# .env
OPENCODE_BASE_URL=http://localhost:4096
```

---

## 3. The Provider layer

The L4 provider layer is the only place that talks to the engine SDK.
Everything above (L1 / L2 / L3) sees only hermetic's own `StreamEvent`
(12 event types, see §4).

```
                    hermetic StreamEvent (12 types)
                    ──────────────────────
                              ▲
                              │ map
                              │
┌──────────────────┐  ┌───────┴──────────┐  ┌──────────────────┐
│ opencode adapter │  │  agent_bridge    │  │ claude adapter   │
│ (HTTP, opencode- │◀─│  (route by       │─▶│ (CLI, claude-    │
│  ai SDK)         │  │   sdk_type)      │  │  agent-sdk)      │
└────────┬─────────┘  └──────────────────┘  └─────────┬────────┘
         │                                            │
         ▼                                            ▼
   opencode serve                                claude CLI
   (HTTP REST)                                   (subprocess)
```

For a new provider, see [`architecture.md` §3.3](architecture.md#33-add-a-new-llm-provider).

---

## 4. Event mapping (opencode → hermetic `StreamEvent`)

`hermetic-agent/providers/streaming.py` defines the 12 canonical event
types. The opencode adapter maps opencode-specific events into these.

| hermetic `StreamEvent` | opencode SDK event | Notes |
|---|---|---|
| `scenario` | (injected by L2 router) | Pre-emit at chat start |
| `session` | `SessionCreated` / `SessionUpdated` | Carries `session_id` |
| `text` | `MessagePartUpdated` (type=text) | Streamed LLM text delta |
| `reasoning` | `MessagePartUpdated` (type=reasoning) | Model reasoning / CoT |
| `tool_use` | `MessagePartUpdated` (type=tool_use) | LLM invoked a tool |
| `tool_result` | `MessagePartUpdated` (type=tool_result) | Tool returned output |
| `card` | (intercepted from `ask_user` tool_use) | LLM's UI card intent |
| `state` | (injected by L3 StateGuard) | State transitions |
| `suspend` | (injected by SuspendableScheduler) | HITL pause point |
| `resume` | (injected by SuspendableScheduler) | HITL resume |
| `done` | `SessionIdle` / `SessionCompleted` | Stream end |
| `error` | any error | With `code` + `detail` |

**Code reference**: `src/hermetic_agent/providers/opencode/chat.py` and
`src/hermetic_agent/providers/streaming.py`.

---

## 5. Configuration knobs

`src/hermetic_agent/config/settings.py` Section 2 (OpenCode) and Section 12 (Chat / SSE):

| Setting | Default | Purpose |
|---|---|---|
| `opencode_base_url` | `http://localhost:4096` | Engine URL |
| `opencode_admin_port` | `7778` | opencode sandbox admin server (env / reload) |
| `opencode_reload_settle_seconds` | `1.0` | Pause after triggering engine reload |
| `opencode_wait_health_timeout` | `8.0` | Engine startup health-probe timeout |
| `opencode_wait_health_interval` | `0.25` | Engine health-probe interval |
| `opencode_client_timeout_connect` | `10.0` | httpx connect timeout (seconds) |
| `opencode_client_timeout_read` | `300.0` | httpx read timeout (LLM calls can be long) |
| `opencode_client_timeout_write` | `10.0` | httpx write timeout |
| `opencode_client_max_connections` | `100` | httpx connection pool size |
| `opencode_client_max_keepalive` | `100` | keepalive connection count |
| `opencode_client_keepalive_expiry` | `120.0` | keepalive expiry (seconds) |
| `sse_keepalive_interval` | `15.0` | SSE `: keepalive` injection interval |
| `agent_pool_health_check_http_timeout` | `5.0` | `/health` probe timeout per opencode node |

**Tuning tips**:

- If you see "LLM call timed out" frequently, raise `opencode_client_timeout_read`.
  Default 300s handles most models; reasoning models may want 600s+.
- High concurrency → bump `opencode_client_max_connections`.
- Slow Vite proxy / corporate network → raise `sse_keepalive_interval` (default 15s
  is safe for most reverse proxies; nginx default is 60s).

---

## 6. Sandbox mode (production)

For production, the opencode engine runs in a **Docker sandbox** (not on the
host). `docker-compose.yml` has the canonical layout:

- Service `opencode-1` runs `opencode serve` inside a container
- Exposed on host port `24096` → container `14096`
- Admin server on container port `7778`, host port `27778` (Hub pushes env + triggers reload via this)
- Shared Docker network `hermetic_agent-sandbox-net` lets Hub talk to it

The Hub's `sandbox/runtime.py` manages:

- `docker run` lifecycle (memory, CPU, pids limits from `settings.sandbox_*`)
- `health_server.py` probe (sandbox-internal HTTP `/healthz`)
- Per-scenario env-var injection (token push for SKILL `required_envs`)

**Adding a new opencode node**: copy the `opencode-1` block in `docker-compose.yml`,
increment the suffix, change the host port, add an `agent_pool.register()` call
in the Hub startup (auto-discovery via Docker DNS is the preferred path).

---

## 7. Common pitfalls

| Symptom | Likely cause | Fix |
|---|---|---|
| `ProviderModelNotFoundError` | opencode version too new/old for hermetic-agent | `python scripts/verify_opencode_config.py` (3-step diagnostic + fix commands) |
| OpenCode HTTP 5xx in stream | engine crashed or model API key invalid | check engine logs; verify `OPENAI_API_KEY` in `.env` |
| SSE drops at ~30-60s | Vite proxy / nginx closing idle | raise `sse_keepalive_interval` or check proxy `proxy_read_timeout` |
| Hub "Cannot connect to opencode" | `OPENCODE_BASE_URL` wrong; engine not started | check `curl $OPENCODE_BASE_URL/global/health` |
| "Provider model not found" after opencode upgrade | cached opencode config | restart opencode; `docker compose build opencode-1 --no-cache` |

---

## 8. Verifying the opencode config

```bash
# 3-step diagnostic: source check, container config, chat smoke test
python scripts/verify_opencode_config.py
```

Output if all OK:
```
[1/3] source check               OK
[2/3] container config           OK  (opencode-1: healthy)
[3/3] chat smoke test            OK  (received text event in 2.3s)
```

Output if a fix is needed, the script prints the exact command:
```
[1/3] source check               FAIL
  → .env missing OPENAI_API_KEY. Run: cp .env.example .env && edit.
```

---

## 9. Writing a custom Provider

If opencode doesn't fit, you can write your own L4 adapter against the
`AgentProvider` ABC. Steps:

1. Create `src/hermetic_agent/providers/<your_engine>/`:
   - `adapter.py` — `class YourEngineProvider(AgentProvider)`
   - `chat.py` — wire your engine's session/event API
   - `lifecycle.py` — start / stop / health
   - `__init__.py` — re-exports

2. Add the import + dispatch case in `providers/agent_bridge.py`:
   ```python
   if sdk_type == "your_engine":
       return YourEngineProvider(...)
   ```

3. (Optional) add a `Provider` enum value in your scenario YAML config layer
   if you want scenarios to be engine-bound.

4. Add integration tests in `tests/test_<your_engine>_*`. Use a mock SDK
   (e.g. an in-process HTTP server) so tests don't require a real engine.

**Do not** modify `providers/base.py` signatures. Add new abstract methods as
default no-ops to preserve backward compat.

---

## 10. Further reading

- opencode GitHub: <https://github.com/sst/opencode>
- `relate_project/opencode/` (in-repo read-only reference, may be out of date)
- `relate_project/opencode-sdk-python/` (in-repo read-only reference)
- `src/hermetic_agent/providers/opencode/` (the actual adapter code)
- `docs/architecture-and-flow.md` §3 (event flow details)
