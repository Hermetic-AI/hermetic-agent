# hermetic-agent

Enterprise-grade AI Agent scheduling platform based on the OpenCode engine. It manages agent pools, session lifecycles, and complex task orchestration (scenarios/skills).

## Project Overview

- **Purpose:** A private hub for scheduling and managing AI Agents.
- **Backend Architecture:**
    - **Framework:** [Sanic](https://sanic.dev/) (Python 3.10+)
    - **Dual-SDK Support:** Supports both `opencode-ai` SDK (HTTP REST to opencode serve) and `claude-agent-sdk` (local CLI process).
    - **Core Components:**
        - `AgentPoolManager`: Manages multiple OpenCode serve instances.
        - `SessionManager`: Handles agent session lifecycles.
        - `Scheduler`: Unified orchestration (`run`, `run_parallel`, `run_chain`).
        - `Policy Engine`: Evaluates security and access control policies.
        - `Skill Runtime`: Executes specialized agent skills.
        - `Scenario Engine`: Manages complex, multi-step conversation flows.
    - **Storage Backends:** Supports `postgres` (asyncpg) and `memory` (dev/fallback).
- **Frontend Architecture:**
    - **Framework:** [Vite](https://vitejs.dev/) + [React](https://react.dev/) + TypeScript
- **Integration:** Communicates with `opencode serve` instances via HTTP REST.

## 🚨 Hard Constraints

### Unified Chat Entry Point
**Dialogue chat entry must be globally unified.** Do NOT add any per-scenario chat endpoints.
There are only two chat endpoints, located in `src/hermetic_agent/api/controllers/chat_controller.py`:
- `POST /agent/chat`: Synchronous chat, returns JSON.
- `POST /agent/chat/stream`: Streaming SSE chat.

**Forbidden:**
- ❌ `/agent/scenarios/{name}/chat`
- ❌ `/agent/scenarios/{name}/chat/stream`
- ❌ Any endpoint that puts the scenario name in the URL.
- ❌ Any chat handler outside `chat_controller.py`.

### Coding Standards
- Python modules ≤ 300 lines.
- Functions ≤ 40 lines.
- Cyclomatic complexity ≤ 10.
- Strict typing with Mypy.
- Structured logging with `structlog`.

## Key Directories

- `src/hermetic_agent/`: Core backend source code.
    - `api/`: REST API layer (controllers, routes, schemas).
    - `core/`: Fundamental logic (pool, session, scheduler).
    - `providers/`: Dual-SDK adapter layer (`opencode_adapter.py`, `claude_code_adapter.py`).
    - `mcp/`: Model Context Protocol integration.
    - `policy/`: Policy enforcement logic.
    - `sandbox/`: Code execution sandbox.
    - `skills/` & `skill_runtime/`: Skill management and execution.
    - `scenarios/`: Task-specific scenario definitions.
    - `store/`: Persistence layer (Postgres/Memory).
- `frontend/`: React-based user interface.
- `docs/`: Comprehensive project documentation.
- `tests/`: Extensive test suite (integration, e2e, unit).
- `.skills/`: External skill definitions.

## Getting Started

### Backend (Python)

Recommended tool: `uv` (or `pip`)

1. **Install dependencies:**
   ```bash
   uv pip install -e ".[dev]"
   uv pip install --pre opencode-ai
   ```
2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration (prefix: AGENT_SCHEDULER_)
   ```
3. **Run the server:**
   ```bash
   # Via CLI command
    hermetic-agent
   # Or via module
   python -m hermetic_agent.main
   ```
4. **API Documentation:**
   Accessible at `http://localhost:8000/docs` (when running).

### Frontend (React)

1. **Navigate to directory:**
   ```bash
   cd frontend
   ```
2. **Install dependencies:**
   ```bash
   npm install # or pnpm install
   ```
3. **Run development server:**
   ```bash
   npm run dev
   ```

## Development Conventions

### Python Backend

- **Linting & Formatting:** [Ruff](https://beta.ruff.rs/docs/).
  ```bash
  ruff check .
  ruff format .
  ```
- **Type Checking:** [Mypy](http://mypy-lang.org/).
  ```bash
  mypy src
  ```
- **Testing:** [Pytest](https://docs.pytest.org/).
  ```bash
  pytest
  ```
- **Imports:** Absolute imports from `hermetic_agent`.
- **Async:** Heavily asynchronous; use `async/await`.

### SSE Event Types
The system supports the following 12 event types for streaming:
`scenario`, `session`, `text`, `reasoning`, `tool_use`, `tool_result`, `card`, `state`, `suspend`, `resume`, `done`, `error`.

## Build and Deployment

- **Docker:**
    - Backend: `docker/hermetic-agent/Dockerfile`
    - Frontend: `docker/frontend/Dockerfile`
    - Sandbox: `docker/opencode/Dockerfile`
- **Orchestration:** Use `docker-compose.yml` for full stack deployment.
- **Build command:**
  ```bash
  docker-compose build
  ```
