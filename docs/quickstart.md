# Quick start

> 5 minutes from `git clone` to your first `/agent/chat` response. Two paths:
> **local** (no Docker) and **docker compose** (one-shot stack).

---

## Path A — Local (no Docker)

### 0. Prerequisites

- **Python 3.10+** (3.11 recommended)
- **Git**
- An LLM credential. Two options:
  - **OpenAI-compatible** (DeepSeek / Qwen / GLM / Ollama / OpenAI itself): set `OPENAI_API_KEY` + `OPENAI_BASE_URL`
  - **Anthropic**: set `ANTHROPIC_API_KEY`
- An **`opencode` binary** for the engine. See [opencode install](https://github.com/sst/opencode#install).
  - On macOS: `brew install sst/tap/opencode`
  - On Linux: `curl -fsSL https://opencode.ai/install | bash`
  - On Windows: `irm https://opencode.ai/install.ps1 | iex`

### 1. Clone + install

```bash
git clone https://github.com/lyzsniper/hermetic-agent.git
cd hermetic-agent
```

**With uv (recommended)**:
```bash
uv venv
uv pip install -e ".[dev]"
```

**With pip**:
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows
pip install -e ".[dev]"
```

### 2. Configure

```bash
cp .env.example .env
```

Open `.env` and set at minimum:

```bash
# Pick ONE of the LLM credential sets
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=sk-...

# Storage (memory is fine for first run)
STORAGE_BACKEND=memory

# Where Hub listens
AGENT_SCHEDULER_PORT=8000
```

### 3. Start the opencode engine (separate terminal)

```bash
opencode serve --port 4096 --hostname 127.0.0.1
```

You should see something like:
```
opencode server listening on http://127.0.0.1:4096
```

In `.env`, point the Hub at it:
```bash
OPENCODE_BASE_URL=http://localhost:4096
```

### 4. Start the Hub

In the repo root:
```bash
hermetic-agent
```

(or `python -m hermetic_agent.main`)

You should see:
```
[INFO] hermetic-agent starting on 0.0.0.0:8000
[INFO] opencode_base_url=http://localhost:4096
[INFO] skills_loaded count=1 paths=['work/shared/skills']
[INFO] auip_ask_user_tool_registered card_types=['CHAT_FALLBACK', 'OD_INPUT', 'QUESTION', 'TODO_LIST']
[INFO] server_ready
```

### 5. Smoke test

```bash
# Health
curl http://localhost:8000/health
# {"status":"ok"}

# First chat
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "hi, what can you do?"}'
```

If you see a `text` event with the LLM's reply — you're done.

### 6. (Optional) Add your first SKILL

```bash
mkdir -p work/shared/skills/my-skill
cd work/shared/skills/my-skill
```

Create `__init__.py`:
```python
from hermetic_agent.auip import register_card_type

register_card_type("MY_GREETING")


def register_renderers(registry):
    """Hub discovers this and calls it at startup."""
    pass
```

Create `SKILL.md`:
```markdown
---
name: my-skill
version: 1.0.0
description: My first SKILL
triggers: ["hello", "hi"]
---

# My Skill

## 1. State machine
| # | State ID | Name | Description |
|---|----------|------|-------------|
| 1 | S01 | AwaitHello | Wait for user greeting |
| 2 | F1 | Done | Finished |

## 2. Tool whitelist
- `ask_user` (framework)
```

Restart `hermetic-agent` and the SKILL auto-loads. See [`docs/skills/skills-authoring-guide.md`](skills/skills-authoring-guide.md) for the full contract.

---

## Path B — Docker Compose (one-shot stack)

### 0. Prerequisites

- **Docker** + **Docker Compose v2**
- An LLM credential (same as Path A)

### 1. Clone + configure

```bash
git clone https://github.com/lyzsniper/hermetic-agent.git
cd hermetic-agent
cp .env.example .env
# edit .env — set OPENAI_API_KEY / OPENAI_BASE_URL
```

### 2. Start the stack

```bash
# Hub + 1 opencode sandbox (the minimum)
docker compose up -d --build

# Add the frontend (optional)
docker compose --profile frontend up -d --build
```

Wait for health:
```bash
docker compose ps
# hermetic-agent    running (healthy)
# opencode-1        running (healthy)
```

### 3. Smoke test

The Hub is now on **`http://localhost:28000`** (note the port mapping; `28000 → 8000`):

```bash
curl http://localhost:28000/health
curl -X POST http://localhost:28000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "hi from docker"}'
```

The frontend (if enabled) is on `http://localhost:23000`.

### 4. Tear down

```bash
docker compose down              # stop, keep volumes
docker compose down -v           # stop, delete volumes (reset state)
```

### 5. Multi-node scale (more opencode sandboxes)

Open `docker-compose.yml`, copy the `opencode-1` block to `opencode-2` / `opencode-3` /
etc., change `hostname:` and the `24096` host port to `24097` / `24098`. Then:

```bash
docker compose up -d --build
```

The Hub auto-discovers all `opencode-*` services via the shared Docker network.

---

## What to read next

| If you want to... | Read |
|---|---|
| Understand the architecture | [`docs/architecture.md`](architecture.md) |
| Add a SKILL | [`docs/skills/skills-authoring-guide.md`](../skills/skills-authoring-guide.md) (or `skills-development-guide.md` for the legacy path) |
| Add a new LLM provider | [`docs/opencode-integration.md`](opencode-integration.md) + [`docs/architecture.md`](architecture.md) §"Extension points" |
| Deploy to production | [`docs/deploy.md`](../deploy.md) |
| Contribute | [`CONTRIBUTING.md`](../../CONTRIBUTING.md) |
| Get help | [GitHub Discussions](https://github.com/lyzsniper/hermetic-agent/discussions) |
