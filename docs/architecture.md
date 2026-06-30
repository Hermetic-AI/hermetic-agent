# Architecture

> Deep dive into hermetic-agent's 5-layer architecture, dependency rules, and
> extension points. For a high-level overview, see [`README.md`](../README.md).
> For the original v0.2 design, see [`architecture-and-flow.md`](architecture-and-flow.md).

---

## 1. The 5 layers

hermetic-agent splits into 5 strictly-downward-depending layers. The dependency
direction is **CI-enforced** by `scripts/ci_check.py` — any reverse or skipping
import fails the build.

```
┌──────────────────────────────────────────────────────────────────────┐
│ L1  api/             HTTP / SSE / chat_controller                    │
│     ────────────────────────────────────────────────────────        │
│ L2  scenarios/       6-priority routing, YAML loader, scenario inject│
│     ────────────────────────────────────────────────────────        │
│ L3  skill_runtime/   SKILL loading, state machine, prompt builder    │
│     auip/            (cards, renderers, rewriters, self-registry)    │
│     core/            SuspendableScheduler, TurnStore                 │
│     ────────────────────────────────────────────────────────        │
│ L4  providers/       opencode-ai + claude-agent SDK adapters         │
│                      (bridge, launcher)                             │
│     ────────────────────────────────────────────────────────        │
│ L5  policy/          path / network / command policy                 │
│     store/           memory / mysql / postgres                      │
│     sandbox/         Docker sandbox management                      │
│     audit/           structlog + BusiLog + Redis collector          │
│     config/          pydantic-settings + Nacos client               │
└──────────────────────────────────────────────────────────────────────┘
```

### What lives where

| Layer | Job | Examples |
|---|---|---|
| **L1** | Talk HTTP / SSE. Translate REST into engine-agnostic calls. Own the 2 chat endpoints. | `chat_controller`, `routes`, `middleware`, `extractors`, `streaming` |
| **L2** | Decide **which** scenario / SKILL a request maps to. Inject scenario-level system prompts / tool whitelists. | `router`, `loader`, `injector`, `registry`, `middleware` |
| **L3** | Run the conversation: load SKILL fragments, drive the state machine, intercept `ask_user` to push A2UI cards, checkpoint on HITL. | `SuspendableScheduler`, `SkillRegistry`, `Card`, `CardRenderer` |
| **L4** | Bridge L3 to the external LLM engine. Map hermetic `StreamEvent` ↔ engine-specific events. | `agent_bridge`, `opencode/adapter`, `claude_code/adapter`, `launcher` |
| **L5** | Cross-cutting infrastructure: policy gates, persistence, Docker sandbox control, structured logging, settings. | `policy/engine`, `store/mysql`, `sandbox/runtime`, `audit/log`, `config/settings` |

### Why these cuts?

- **L1-L2 are "request-shaped"** — they know about HTTP, scenarios, routing.
- **L3 is the heart** — engine-agnostic Agent orchestration. It can be driven by
  any L4 provider; its logic doesn't care which one.
- **L4 is the "wire"** — only this layer talks to external SDKs / CLIs.
- **L5 is "infrastructure"** — no domain logic, only cross-cutting concerns.

---

## 2. The data path (one `/agent/chat` request)

```
┌──────┐  HTTP POST   ┌──────────┐  scenario  ┌───────────┐
│ UI   │ ───────────▶ │ L1       │ ──────────▶│ L2        │
│      │              │ chat_    │             │ router    │
│      │              │ controller│             │ injector  │
└──────┘              └────┬─────┘             └─────┬─────┘
       ▲                    │                        │
       │ SSE events         │ SkillManifest +        │
       │                    │ scenario.system_prompt │
       │                    ▼                        ▼
       │              ┌────────────────────────────────┐
       │              │ L3 SuspendableScheduler        │
       │              │  ├─ SkillRegistry (fragments)  │
       │              │  ├─ StateGuard (tool whitelist)│
       │              │  └─ AUIP (cards / rewriters)   │
       │              └────┬───────────────────────────┘
       │                   │ StreamEvent iterator
       │                   ▼
       │              ┌────────────────────────────────┐
       │              │ L4 agent_bridge                 │
       │              │  ├─ opencode adapter (HTTP)    │
       │              │  └─ claude_code adapter (CLI)  │
       │              └────┬───────────────────────────┘
       │                   │ engine protocol
       │                   ▼
       │              ┌────────────────────────────────┐
       │              │ External engine                 │
       │              │  (opencode serve / claude CLI)  │
       │              └────┬───────────────────────────┘
       │                   │ tool calls
       │                   ▼
       │              ┌────────────────────────────────┐
       │              │ L5 sandbox + policy             │
       │              │  ├─ path_check                  │
       │              │  ├─ network_check               │
       │              │  └─ command_check               │
       │              └────────────────────────────────┘
       │
       │ text / reasoning / tool_use / card / suspend / done
       ◀─────────────────────────────────────────────────────
```

For the full event taxonomy (12 StreamEvent types), see
[`architecture-and-flow.md` §3](architecture-and-flow.md).

---

## 3. Extension points

This is where you add capabilities **without touching core**.

### 3.1 Add a new SKILL (primary extension point)

A SKILL is a self-contained directory under `work/shared/skills/<your-skill>/`:

```
my-skill/
├── __init__.py                # register card types + register_renderers() / register_rewriters()
├── SKILL.md                   # frontmatter + state machine + tool whitelist
├── skill.yaml                 # mcp_tools, required_envs, fragment budget
└── (optional)
    ├── card_renderers/        # CardRenderer subclasses
    └── message_rewriters/     # MessageRewriter subclasses
```

The Hub auto-discovers SKILL directories at startup. No core-code change.

**SKILL contract**: see [`core-skill-boundary.md`](core-skill-boundary.md) and
[`skills/skills-authoring-guide.md`](skills/skills-authoring-guide.md).

**Scaffolding tool (planned)**: `hermetic-skill init my-skill` and
`hermetic-skill validate my-skill/` — see [§6 of the evolution plan](hermetic-agent-open-source-evolution-plan.md).

### 3.2 Add a new CardType

The base ships 4 protocol-level card types:

- `CHAT_FALLBACK` — generic chat reply card
- `OD_INPUT` — generic one-direction input form (SuspendableScheduler default)
- `QUESTION` — maps to opencode's `question` tool
- `TODO_LIST` — maps to opencode's `todo` tool

To add a **business** card type, your SKILL just calls at startup:

```python
from hermetic_agent.auip import register_card_type
register_card_type("FLIGHT_LIST")
register_card_type("FLIGHT_RESULT")
```

The Card is validated against `BUILTIN_CARD_TYPES ∪ registered` (see
`auip/cards.py` and `auip/_card_type_registry.py`).

### 3.3 Add a new LLM Provider

Implement the `AgentProvider` ABC from `providers/base.py`:

```python
# src/hermetic_agent/providers/my_engine/adapter.py
from hermetic_agent.providers.base import AgentProvider

class MyEngineProvider(AgentProvider):
    async def stream_chat(self, ...): ...
    async def blocking_chat(self, ...): ...
    async def create_session(self, ...): ...
    async def get_session(self, ...): ...
    async def delete_session(self, ...): ...
    async def list_sessions(self, ...): ...
    async def abort_session(self, ...): ...
    async def health_check(self, ...): ...
```

Register in `agent_bridge.py`'s dispatch, then add a `Provider` enum value
if your config layer needs to distinguish it.

**Do not** modify `providers/base.py` signatures. Add new abstract methods
as default-implemented (no-op) so existing adapters keep working.

### 3.4 Add a new policy gate

`policy/` has 3 sub-engines: `path_check`, `network_check`, `command_check`.
Add a new one by:

1. Creating `policy/<your_check>.py` with a `check(...) -> bool` function.
2. Wiring it into `policy/engine.py` `PolicyEngine.evaluate()`.
3. Adding a setting in `config/settings.py` for its parameters.

### 3.5 Add a new storage backend

Implement the `StorageBackend` ABC in `store/base.py` with all the repository
interfaces (`SessionRepository`, `MessageRepository`, `PartRepository`,
`SkillRepository`, `MCPConfigRepository`, `ScenarioRepository`, `AuditLogRepository`).

Wire it in `store/services/container.py` based on `settings.storage_backend`.

### 3.6 Add a new Nacos-driven config

Add the field to `config/settings.py` `Settings` (Section 15) and a
`NacosSource` subclass in `config/nacos_client.py` to fetch + cache the
remote value at startup.

---

## 4. Layer dependency rules (hard)

| From | Can import | Cannot import |
|---|---|---|
| L1 `api/` | L2, L3, L4, L5 | (nothing) |
| L2 `scenarios/` | L3, L5 | L1, L4 |
| L3 `skill_runtime/`, `auip/`, `core/` | L4, L5 | L1, L2 |
| L4 `providers/` | L5 | L1, L2, L3 |
| L5 `policy/`, `store/`, `sandbox/`, `audit/`, `config/` | (nothing) | any higher layer |

**Why this matters**: cycle prevention + clear ownership. A code review can
answer "where does this go?" purely by looking at which layer it depends on.

Enforcement: `scripts/ci_check.py` (`python scripts/ci_check.py` in CI).

---

## 5. File-size hard limits

| Layer | Max file lines | Max function lines | Max complexity |
|---|---|---|---|
| L1 | 200 | 40 | 10 |
| L2 | 250 | 40 | 10 |
| L3 | 250 | 40 | 10 |
| L4 | 200 | 40 | 10 |
| L5 | 200 | 40 | 10 |

**If your code grows past the limit**, split it — extract helpers / new
modules. Never let a file bloat; small files are easier to navigate, test,
and AI-assist.

---

## 6. The 12 error codes

All user-visible errors come from one of 12 standardized codes. The pattern:

```json
{
  "code": "SCENARIO_NOT_FOUND",
  "detail": "scenario 'flight_query' not found in any of [work/scenarios, work/shared/scenarios]. Check spelling and file extension.",
  "field": "scenario",
  "rule": "scenario_yaml_required"
}
```

Full table: [`architecture-and-flow.md` §7](architecture-and-flow.md).

---

## 7. Cardinality / scale targets

| Dimension | Target | Why |
|---|---|---|
| Concurrent SSE chats per Hub | 100+ | httpx pool default = 100; bump via `opencode_client_max_connections` |
| Concurrent opencode sandboxes | 1-N | Linear; just add `opencode-2`, `opencode-3`, ... to compose |
| Single SKILL fragment budget | 4k tokens (configurable) | Anthropic Skills spec |
| SKILL state count | ~20 states per SKILL | Linear complexity of state machine |
| Storage tables | 8 (session, message, part, skill, mcp, scenario, audit_log, chat_turn) | Flat schema, no joins in hot path |
| Card type registry | unbounded | SKILLs register at startup; thread-safe |

---

## 8. Where to read more

- [`architecture-and-flow.md`](architecture-and-flow.md) — original v0.2 design with sequence diagrams
- [`core-skill-boundary.md`](core-skill-boundary.md) — the core-vs-SKILL contract (must-read for SKILL authors)
- [`skills/skills-authoring-guide.md`](skills/skills-authoring-guide.md) — SKILL authoring guide
- [`opencode-integration.md`](opencode-integration.md) — opencode SDK details + event mapping
- [`hermetic-agent-open-source-evolution-plan.md`](hermetic-agent-open-source-evolution-plan.md) — 4-phase roadmap to OSS 1.0
