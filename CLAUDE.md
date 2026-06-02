# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**OpenCode Agent Scheduler Hub** — a dual-SDK AI Agent scheduling platform supporting both OpenCode SDK and Claude Code SDK (claude-agent-sdk). It manages a pool of agent instances and provides a unified REST API for dispatching tasks, with Skills/MCP support, SSE streaming, and PostgreSQL persistence.

## Architecture

```
openagent/
├── api/
│   ├── app.py          # Sanic app factory (create_app), structlog config
│   └── routes.py       # REST endpoints (Chat, Session, Skills, Tools, Pool)
├── config/
│   └── settings.py     # pydantic-settings (env prefix: AGENT_SCHEDULER_)
├── core/
│   ├── agent_pool.py   # AgentPoolManager — opencode instance lifecycle & health checks
│   └── scheduler.py    # Scheduler — unified orchestration (run / run_parallel / run_chain)
├── providers/           # Dual-SDK adapter layer
│   ├── base.py          # AgentProvider ABC + ChatMessage/Result/SessionInfo/AgentConfig
│   ├── opencode_adapter.py  # opencode-ai SDK adapter
│   ├── claude_code_adapter.py  # claude-agent-sdk adapter (local CLI)
│   └── agent_bridge.py  # Routes to correct adapter by sdk_type
├── skills/
│   └── registry.py    # SkillRegistry — SKILL.md parsing + prompt injection
├── mcp/
│   └── registry.py    # MCPRegistry — local handlers + remote MCP servers
├── store/              # Persistence layer
│   ├── base.py        # StorageBackend ABC + Session/Message/Part models
│   ├── postgres.py    # PostgresStorage (asyncpg)
│   └── memory.py     # MemoryStorage (dev/fallback)
├── streaming.py        # StreamEvent + SSE helpers + SDK event mappers
└── main.py             # Entrypoint

frontend/               # React + TypeScript + Vite frontend (AI booking/chat UI)
tests/
├── conftest.py         # pytest fixtures: storage, skill_registry, mcp_registry, bridge, scheduler
├── test_agent_pool.py
└── test_scheduler.py
```

**Data flow**: `Sanic request` → `routes.py` → `Scheduler` → `AgentBridge` → `OpenCodeAdapter | ClaudeCodeAdapter` → SDK

**Key pattern**: Core components (`bridge`, `storage`, `skill_registry`, `mcp_registry`, `scheduler`) are stored in `app.ctx` after `after_server_start`. Routes access them via helper functions (`get_bridge`, `get_storage`, etc.).

## SDK Support

| SDK | Package | Type | Model Config |
|-----|---------|------|-------------|
| `opencode-ai` | `opencode-ai>=0.1.0a0` | HTTP REST to opencode serve | opencode serve config |
| `claude-agent-sdk` | `claude-agent-sdk @ git+...` | Local CLI process | `ClaudeAgentOptions.model` |

**Claude Code SDK is local** — it invokes the Claude Code CLI locally, not via HTTP. The `base_url` field in AgentConfig is used for `cli_path` when set.

## Common Commands

### Backend (Python)

```bash
# Install dependencies (in project root)
uv pip install -e .                  # or: pip install -e .
uv pip install -e ".[dev]"           # with dev dependencies

# Run the server
python -m openagent.main             # or: agent-scheduler

# Run tests
pytest -v
pytest tests/test_scheduler.py -v     # single test file
pytest tests/ -k "test_init" -v     # single test

# Lint and type check
ruff check src/
ruff format src/
mypy src/

# Start opencode serve (required for opencode-ai SDK agents)
opencode serve --port 4096 --hostname 127.0.0.1
```

### Frontend (React)

```bash
cd frontend
pnpm install
pnpm dev          # dev server
pnpm build        # production build
pnpm typecheck    # TypeScript check
pnpm lint
```

## Key Implementation Notes

- **Settings**: All config via environment variables with `AGENT_SCHEDULER_` prefix (see `.env.example`). New fields: `storage_backend`, `postgres_dsn`, `skill_paths`, `mcp_tools_config`.
- **Async**: Uses `async`/`await` throughout. Tests use `pytest-asyncio` with `asyncio_mode = "auto"`.
- **Scheduler modes**: `run()` (single), `run_parallel()` (via `asyncio.gather`), `run_chain()` (sequential with accumulated context).
- **Storage backends**: `postgres` (default, asyncpg) or `memory` (dev/fallback). Set via `AGENT_SCHEDULER_STORAGE_BACKEND=memory`.
- **Skills**: Loaded from directories via `SkillRegistry.load_from_paths()`. Each skill is a `SKILL.md` file with frontmatter (`name`, `description`, `triggers`) and content.
- **MCP Tools**: Registered via `MCPRegistry.register_handler()` (local) or `register_remote()` (HTTP). Tools are format-converted per SDK (`to_opencode_format`, `to_claude_code_format`).
- **SSE streaming**: Both SDK adapters yield unified `StreamEvent` objects (`session`, `text`, `reasoning`, `tool_use`, `tool_result`, `done`, `error`).
- **Structured logging**: Uses `structlog` with JSON/text output controlled by `AGENT_SCHEDULER_LOG_FORMAT`.
- **File limits** (per .skills guidelines): Python modules ≤ 300 lines, functions ≤ 40 lines, complexity ≤ 10.
