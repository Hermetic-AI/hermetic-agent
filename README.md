# hermetic-agent

> **General-purpose Agent scheduling framework** built on [opencode](https://github.com/sst/opencode) SDK
> (with optional [claude-agent-sdk](https://github.com/anthropics/claude-agent-sdk-python) support).

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-554%20passed-green.svg)](#testing)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-261230.svg)](https://docs.astral.sh/ruff/)

---

## What is hermetic-agent?

hermetic-agent is a **Sanic-based** Agent scheduling hub. It owns the lifecycle of multiple
`opencode serve` (or `claude-agent` CLI) processes, exposes a unified REST + SSE chat API,
and lets third parties ship new business capabilities as **SKILLs** that the framework discovers
and loads at runtime — no core-code change required.

It is **engine-agnostic** (opencode / claude / future providers), **business-agnostic**
(no flight / booking / domain hard-codes in the core), and **storage-agnostic**
(MySQL / PostgreSQL / memory backends behind one interface).

---

## Features

- **5-layer architecture** (`api` / `scenarios` / `skill_runtime` / `providers` / `policy+store+config`)
  with strict downward dependencies — enforced by `scripts/ci_check.py`.
- **Unified chat entry** — exactly 2 endpoints, both in `chat_controller.py`:
  - `POST /agent/chat` (sync JSON)
  - `POST /agent/chat/stream` (SSE streaming)
- **SKILL system** with progressive loading (`none` / `all` / `on_demand` / `explicit`),
  token budget, state machine, and runtime self-registration of business `CardType`s.
- **CardType self-registration** — the core ships 4 protocol-level card types
  (`CHAT_FALLBACK` / `OD_INPUT` / `QUESTION` / `TODO_LIST`); every business card type
  is registered by its owning SKILL at startup via `register_card_type(name)`.
- **A2UI / AUIP** card protocol with optional `CardRenderer` / `MessageRewriter` plugins
  registered by SKILLs (base has zero business logic).
- **Dual-SDK** provider layer (`opencode-ai` HTTP / `claude-agent-sdk` CLI) routed by `agent_bridge`.
- **Sandbox isolation** — Hub + N `opencode` containers share a Docker network, with
  policy gates for path / network / command (L5).
- **Multi-tenant storage** — `memory` / `mysql` / `postgres` backends, swappable per env.
- **Nacos integration** (optional) — config center + AI registry (MCP/Agent/Skill/Prompt).
- **HITL** (Human-in-the-Loop) via `SuspendableScheduler` + `TurnStore` checkpointing.
- **12 standardized error codes** (see `docs/architecture-and-flow.md` §7) with actionable `detail`.

---

## Quick start (local, 5 minutes)

```bash
# 1. Clone + install (uv preferred; pip also works)
git clone https://github.com/lyzsniper/hermetic-agent.git
cd hermetic-agent
uv venv
uv pip install -e ".[dev]"

# 2. Copy env template
cp .env.example .env
# (default .env works for local dev: log_format=console, storage=memory, mock opencode base_url)

# 3. Start the Hub
hermetic-agent
# or:  python -m hermetic_agent.main
# Hub listens on http://localhost:8000  (override with AGENT_SCHEDULER_PORT in .env)

# 4. Smoke test
curl http://localhost:8000/health
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "hello", "scenario": "_default"}'
```

For Docker-based quick start (Hub + opencode sandbox in one shot), see [`docs/quickstart.md`](docs/quickstart.md).

---

## Architecture (5 layers)

```
┌──────────────────────────────────────────────────────────────┐
│  L1  api/             HTTP / SSE / chat_controller           │
│  ────────────────────────────────────────────────────────     │
│  L2  scenarios/       6-priority routing + scenario YAML     │
│  ────────────────────────────────────────────────────────     │
│  L3  skill_runtime/   SKILL loading, state machine, AUIP    │
│       auip/           (cards, renderers, message rewriters) │
│       core/           SuspendableScheduler, TurnStore        │
│  ────────────────────────────────────────────────────────     │
│  L4  providers/       opencode SDK / claude-agent CLI        │
│                      (adapters, launcher, agent_bridge)      │
│  ────────────────────────────────────────────────────────     │
│  L5  policy/  store/  sandbox/  config/                      │
│       (path / network / command policy, persistence)         │
└──────────────────────────────────────────────────────────────┘
```

**Dependency rule** (CI-enforced by `scripts/ci_check.py`): L1 → L2 → L3 → L4 → L5. Reverse or skipping imports fail the build.

Full architecture + sequence diagrams: [`docs/architecture.md`](docs/architecture.md) and
[`docs/architecture-and-flow.md`](docs/architecture-and-flow.md).

---

## Writing your first SKILL

```bash
mkdir -p work/shared/skills/my-skill && cd work/shared/skills/my-skill
```

`__init__.py` — register your card types + implement the renderer protocol:

```python
from hermetic_agent.auip import (
    register_card_type, CardRendererRegistry, MessageRewriterRegistry,
)

register_card_type("MY_GREETING")  # declare all card types you use

# (implement CardRenderer / MessageRewriter subclasses; see work/shared/skills/example-echo-skill)
```

`SKILL.md` — frontmatter + state machine + tool whitelist (Anthropic Skills-style):

```markdown
---
name: my-skill
version: 1.0.0
description: Greets the user and shows a card.
triggers: ["hello", "hi"]
---

# My Skill

## 1. State machine
| # | State ID | Name        | Description                  |
|---|----------|-------------|------------------------------|
| 1 | S01      | AwaitHello  | Wait for user to say hello   |
| 2 | F1       | Done        | Finished                     |

## 2. Tool whitelist
- `greet` (synthetic tool, Hub registers)
- `ask_user` (framework-level)
```

Reference: [`work/shared/skills/example-echo-skill/`](work/shared/skills/example-echo-skill/) is a
complete working example. To scaffold new skills, see [`docs/skills/skills-authoring-guide.md`](docs/skills/skills-authoring-guide.md) (or `docs/skills-development-guide.md` until the SKILL CLI ships).

---

## Configuration

`src/hermetic_agent/config/settings.py` is the single source of truth (pydantic-settings,
auto-loads `.env` in CWD). 15 sections:

| Section | Key fields | Purpose |
|---|---|---|
| Server | `host`, `port`, `workers`, CORS, Sanic timeouts | Process / HTTP config |
| OpenCode | `opencode_base_url`, `opencode_admin_port` | Engine client + admin |
| Logging | `log_level`, `log_format` (json/console), Redis log | 12-factor logs |
| Storage | `storage_backend` (memory/mysql/postgres), DSN | Persistence |
| Skill Runtime | `skill_paths`, `fragment_budget_tokens` | SKILL loading |
| MCP | `mcp_tools_config` (inline or path) | MCP tool registry |
| Agent | `auto_register_default_agents` | Auto-register |
| Sandbox | `sandbox_mem_limit`, `sandbox_cpu_limit` | Container limits |
| Policy | `network_allowed_local_ports`, `path_blocked_patterns` | L5 safety |
| Scenario | `scenario_paths`, `default_scenario` | Scenario routing |
| Launcher | `launcher_config_dir`, `launcher_forbidden_cwds` | opencode config render |
| Chat / SSE | `sse_keepalive_interval`, `opencode_client_timeout_*` | Streaming + httpx |
| App Metadata | `app_title`, `app_version`, license | OpenAPI doc |
| Nacos | `nacos_enabled`, `nacos_server_addr`, AI registry | External config |

**Two layers of overrides**: (1) `.env` (base, CWD), (2) Nacos (override, optional).
**Business secrets** (API keys, tokens) never go here — they go into
`work/scenarios/*.scenario.yaml` `env` field or `work/shared/skills/*/skill.yaml` `required_envs`.

---

## REST API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/agent/chat` | Sync chat (JSON) |
| `POST` | `/agent/chat/stream` | SSE streaming chat |
| `GET`  | `/agent/scenarios` | List scenarios |
| `POST` | `/agent/scenarios` | Register scenario |
| `GET`  | `/agent/pool` | Agent pool stats |
| `GET`  | `/agent/skills` | List skills |
| `GET`  | `/agent/mcp/tools` | List MCP tools |
| `GET`  | `/health` | Liveness |
| `GET`  | `/ready` | Readiness (pool + skills) |
| `GET`  | `/docs` | Swagger UI |

OpenAPI schema: `GET /openapi.json`. Full spec: [`docs/api.md`](docs/api.md).

---

## Testing

```bash
# Unit + integration (skips e2e by default — needs real opencode + credentials)
pytest -v

# E2E (requires running opencode + valid model API key)
pytest tests/test_e2e_* -v --run-e2e

# Quality gates
python scripts/ci_check.py                  # 5-layer + file size
python scripts/check_unified_chat_entry.py  # unified chat entry
ruff check src/                             # lint
mypy src/                                   # type check
```

---

## Deployment

```bash
# Full stack: Hub + 1 opencode sandbox + (optional) frontend
docker compose up -d --build

# Production: force image pull
PULL_POLICY=always docker compose up -d

# Frontend (separate profile)
docker compose --profile frontend up -d --build
```

3 services on `docker-compose.yml`:
- `hermetic-agent` — Hub (port `28000` → container `8000`)
- `opencode-1` — opencode sandbox (port `24096`; admin `27778`)
- `hermetic_agent-frontend` — nginx reverse proxy (port `23000`, `--profile frontend`)

Detailed deploy guide: [`docs/deploy.md`](docs/deploy.md). Build / cache: [`docs/BUILD.md`](docs/BUILD.md).

---

## Documentation index

| Doc | Purpose |
|---|---|
| [`docs/quickstart.md`](docs/quickstart.md) | 5-minute local + Docker quick start |
| [`docs/architecture.md`](docs/architecture.md) | 5-layer architecture + extension points |
| [`docs/architecture-and-flow.md`](docs/architecture-and-flow.md) | Deep dive: 5 layers + 4 conversation flows + 12 error codes |
| [`docs/api.md`](docs/api.md) | REST API contract (full) |
| [`docs/opencode-integration.md`](docs/opencode-integration.md) | opencode SDK integration + event mapping |
| [`docs/core-skill-boundary.md`](docs/core-skill-boundary.md) | Core vs SKILL boundary contract |
| [`docs/skills-development-guide.md`](docs/skills-development-guide.md) | SKILL authoring guide |
| [`docs/deploy.md`](docs/deploy.md) | Production deployment guide |
| [`docs/BUILD.md`](docs/BUILD.md) | Docker build + cache strategy |
| [`docs/hermetic-agent-open-source-evolution-plan.md`](docs/hermetic-agent-open-source-evolution-plan.md) | Open-source evolution roadmap (4 phases) |
| [`CHANGELOG.md`](CHANGELOG.md) | Release history (Keep a Changelog) |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | How to contribute |
| [`NOTICE`](NOTICE) | Third-party license attributions |
| [`LICENSE`](LICENSE) | Apache 2.0 full text |

---

## Project structure

```
hermetic-agent/
├── src/hermetic_agent/      # Hub main code (5-layer architecture, CI-enforced)
│   ├── api/                 # L1 — HTTP / SSE / chat_controller
│   ├── scenarios/           # L2 — routing, loader, injector
│   ├── skill_runtime/       # L3 — manifest, fragments, prompt builder
│   ├── auip/                # L3 — cards, events, renderers, rewriters
│   ├── core/                # L3 — SuspendableScheduler, TurnStore
│   ├── providers/           # L4 — opencode + claude adapters
│   ├── policy/              # L5 — path / network / command policy
│   ├── store/               # L5 — memory / mysql / postgres backends
│   ├── sandbox/             # L5 — Docker sandbox management
│   └── config/              # L5 — settings.py + Nacos client
├── frontend/                # React + Vite + TS frontend (active)
├── work/                    # Runtime: scenarios YAML / shared skills / mcp config / tenant dirs
├── docker/                  # 3 Dockerfiles + nginx + entrypoint + sandbox admin
├── docs/                    # All documentation
├── scripts/                 # ci_check + check_unified_chat_entry + verify_opencode_config
└── tests/                   # pytest (554 unit/integration + e2e with --run-e2e)
```

---

## Contributing

We welcome PRs. Read [`CONTRIBUTING.md`](CONTRIBUTING.md) first — it covers dev env setup,
code style (ruff + mypy), the 5-layer dependency rule, file-size limits, and SKILL contribution
guidelines.

Before opening a PR, run:

```bash
python scripts/ci_check.py && \
python scripts/check_unified_chat_entry.py && \
ruff check src/ && \
mypy src/ && \
pytest tests/ -v
```

All must pass.

---

## License

Apache License 2.0. See [`LICENSE`](LICENSE) for full text. Third-party attributions in [`NOTICE`](NOTICE).
