# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**hermetic-agent** — a dual-SDK AI Agent scheduling platform supporting both OpenCode SDK and Claude Code SDK (claude-agent-sdk). It manages a pool of agent instances and provides a unified REST API for dispatching tasks, with Skills/MCP support, SSE streaming, and PostgreSQL persistence.

## Architecture

```
hermetic_agent/
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
python -m hermetic_agent.main             # or: hermetic-agent

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
- **SSE streaming**: Both SDK adapters yield unified `StreamEvent` objects. See `src/hermetic_agent/streaming.py` for the 12 supported event types: `scenario`, `session`, `text`, `reasoning`, `tool_use`, `tool_result`, `card`, `state`, `suspend`, `resume`, `done`, `error`.
- **Structured logging**: Uses `structlog` with JSON/text output controlled by `AGENT_SCHEDULER_LOG_FORMAT`.

## 🚨 HARD CONSTRAINT: 统一对话入口

> **对话 chat 入口必须全局统一**. 严禁新增任何 per-scenario chat 端点.

**只有 2 个对话端点, 都集中在 `src/hermetic_agent/api/controllers/chat_controller.py`:**

| 端点 | 用途 | 备注 |
|---|---|---|
| `POST /agent/chat` | 同步 chat, 返回 JSON | F2 已接 `ScenarioMiddleware` + `ScenarioInjector` + `SuspendableScheduler` |
| `POST /agent/chat/stream` | 流式 SSE chat | 同上, 开头 emit `scenario` 事件; HITL 走 `SuspendableScheduler` 推 `card` + `suspend` |

**严禁**:
- ❌ `POST /agent/scenarios/{name}/chat` (已删除)
- ❌ `POST /agent/scenarios/{name}/chat/stream` (已删除)
- ❌ 任何把"scenario 名塞进 URL"另开对话入口的做法
- ❌ 在 scenario_controller.py / skill runtime / 别处另起一个 chat handler
- ❌ 在 frontend 另起一个"send to scenario X"的服务, 绕开 /agent/chat

**Scenario 路由只在 chat 入口前发生** (`ScenarioMiddleware.route()` 6 优先级), 不应该让 client 主动"挑 scenario URL"。client 的全部对话请求都发到 `/agent/chat[/stream]`, scenario 由 `body.scenario` / `X-Scenario` / keyword 推断决定。

**校验方式** (CI 必跑):

```python
# scripts/check_unified_chat_entry.py
import re, pathlib
forbidden_paths = [r"/agent/scenarios/[^/]+/chat", r"/agent/scenarios/[^/]+/chat/stream"]
# 扫所有 controller 文件, 任何匹配 → CI fail
```

`tests/test_scenario_controller.py::test_no_per_scenario_chat_endpoint` 必过, 否则 PR 拒绝。

**为什么**:
1. 入口分散导致 routing / injection / 审计 / turn lifecycle 无法统一
2. Skill 状态机依赖"同一个 turn 内 token 流连续", 多入口破坏这个不变量
3. 测试 mock 需要写 N 份, 维护成本高
4. OpenAPI 文档变冗长, 客户端要选 endpoint

**历史教训**: 2026-06-03 P6 阶段在 `scenario_controller.py` 加了 `/agent/scenarios/{name}/chat` + `/chat/stream` 两个 stub 端点, 2026-06-03 立刻删掉 (F10)。
- **File limits** (per .skills guidelines): Python modules ≤ 300 lines, functions ≤ 40 lines, complexity ≤ 10.
