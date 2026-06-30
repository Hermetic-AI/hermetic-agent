# Contributing to hermetic-agent

First off — thank you for investing time in hermetic-agent. This document covers
how to set up a dev environment, the project's code style, the absolute
constraints, and how to add a new SKILL.

## Table of contents

1. [Code of conduct](#code-of-conduct)
2. [Development setup](#development-setup)
3. [Project layout](#project-layout)
4. [Code style](#code-style)
5. [Absolute constraints (CI-enforced)](#absolute-constraints-ci-enforced)
6. [Testing](#testing)
7. [Submitting a PR](#submitting-a-pr)
8. [Adding a new SKILL](#adding-a-new-skill)
9. [Adding a new Provider](#adding-a-new-provider)
10. [Release process](#release-process)

---

## Code of conduct

Be kind. We follow the [Contributor Covenant](https://www.contributor-covenant.org/)
in spirit. Disagreements happen; personal attacks don't.

---

## Development setup

Requires **Python 3.10+**, **Git**, and (optionally) **Docker** for the integration
test stack. We strongly recommend [**uv**](https://docs.astral.sh/uv/) for dependency
management.

```bash
# 1. Clone
git clone https://github.com/lyzsniper/hermetic-agent.git
cd hermetic-agent

# 2. Create venv + install (dev extras included)
uv venv
uv pip install -e ".[dev]"

# 3. Copy env template + smoke test
cp .env.example .env
hermetic-agent
# Hub should be listening on http://localhost:8000
```

> **Windows users**: prefer `uv venv` over `python -m venv` — it's faster and
> handles the path / encoding edge cases (UTF-8 vs GBK) that have bitten us before.

---

## Project layout

```
src/hermetic_agent/
├── api/             L1 — HTTP / SSE / chat_controller
├── scenarios/       L2 — routing, loader, injector
├── skill_runtime/   L3 — manifest, fragments, prompt builder
├── auip/            L3 — cards, events, renderers, rewriters, self-registry
├── core/            L3 — SuspendableScheduler, TurnStore
├── providers/       L4 — opencode + claude adapters
├── policy/          L5 — path / network / command policy
├── store/           L5 — memory / mysql / postgres backends
├── sandbox/         L5 — Docker sandbox management
├── audit/           L5 — structlog + BusiLog / Redis collector
└── config/          L5 — settings.py + Nacos client
```

The 5-layer rule is enforced by `scripts/ci_check.py`. See
[`docs/architecture.md`](docs/architecture.md) for details.

---

## Code style

- **Formatter / linter**: [ruff](https://docs.astral.sh/ruff/) (line-length 100, ignores E501).
- **Type checker**: [mypy](https://mypy-lang.org/) in strict mode.
- **Docstrings**: Google style on all public functions / classes.
- **Comments**: only when the code itself can't say it. No decorative noise.
- **Logging**: use `structlog.get_logger(__name__)`. Never `print()`. Never raw
  `logging.getLogger()` outside `audit/log/`.

Pre-commit (optional but recommended):

```bash
uv pip install pre-commit
pre-commit install
```

---

## Absolute constraints (CI-enforced)

These are checked by `python scripts/ci_check.py` and
`python scripts/check_unified_chat_entry.py`. Violations block the PR.

### 1. Unified chat entry

Exactly **2 chat endpoints**, both in `src/hermetic_agent/api/http/controllers/chat_controller.py`:

- `POST /agent/chat` (sync JSON)
- `POST /agent/chat/stream` (SSE streaming)

**No** per-scenario chat endpoints. No "send to scenario X" in any other
controller / frontend service. Scenario routing happens *inside* the chat handler
via `ScenarioMiddleware` (6 priorities).

### 2. 5-layer dependency rule

L1 → L2 → L3 → L4 → L5. Reverse or skipping imports fail.

```python
# ✓ allowed:
from hermetic_agent.scenarios import ScenarioRegistry   # L1 → L2
from hermetic_agent.core.suspendable_scheduler import SuspendableScheduler  # L1 → L3

# ✗ blocked:
from hermetic_agent.api import chat_controller         # L3 → L1 (reverse)
from hermetic_agent.providers import opencode_adapter  # L2 → L4 (skipping L3)
```

### 3. File size limits

- L1 / L4 / L5: ≤ 200 lines
- L2 / L3: ≤ 250 lines
- Functions: ≤ 40 lines
- Complexity: ≤ 10 (mccabe)

### 4. No modifying core signatures

These classes keep stable signatures — extend by adding methods, never mutate:

- `core/scheduler.py` — `Scheduler`
- `providers/base.py` — `AgentProvider` ABC
- `providers/agent_bridge.py` — `AgentBridge`
- `skills/registry.py` — `SkillRegistry`, `Skill`
- `mcp/registry.py` — `MCPRegistry`, `MCPTool`

### 5. 12 error codes

All user-visible errors must use one of the 12 codes defined in
[`docs/architecture-and-flow.md` §7](docs/architecture-and-flow.md), with
`code` + `detail` (file / field / rule / how-to-fix). Never bare `"error"`.

---

## Testing

```bash
# Unit + integration (fast; ~3s)
pytest -v

# E2E (requires running opencode + valid model API key)
pytest tests/test_e2e_* -v --run-e2e

# Specific layer
pytest tests/test_auip_*.py -v
pytest tests/test_scenario*.py -v

# Single test by name
pytest -k "test_ask_user_tool" -v
```

**Naming convention**: `test_<module>_{init,happy_path,error}_*`.

**Conftest rules**:
- `tests/conftest.py` is **read-only** — do not modify.
- Per-feature fixtures go in `tests/test_<feature>_conftest.py`.

---

## Submitting a PR

1. **Fork + branch** off `main`. Use a descriptive branch name:
   `feat/skill-cli-scaffold`, `fix/auip-card-encoding`, `docs/architecture-update`.
2. **Small, focused PRs** are easier to review. One logical change per PR.
3. **All four gates must pass** before requesting review:

   ```bash
   python scripts/ci_check.py && \
   python scripts/check_unified_chat_entry.py && \
   ruff check src/ && \
   mypy src/ && \
   pytest tests/ -v
   ```

4. **Add a CHANGELOG entry** under `[Unreleased]`. Use the existing
   `Added` / `Changed` / `Fixed` / `Removed` sections.
5. **Update docs** if your change touches architecture, public API, or SKILL
   contracts. Use `docs/` for the deep stuff; README stays high-signal.
6. **Reference any related issue** in the PR description (`Fixes #123`).
7. **Expect review** within 2 business days. Be ready to iterate.

---

## Adding a new SKILL

SKILLs are the primary extension point. They're self-contained directories
under `work/shared/skills/<your-skill>/` that the Hub auto-discovers.

**Minimum files**:

```
my-skill/
├── __init__.py          # register card types + register_renderers() / register_rewriters()
├── SKILL.md             # frontmatter (name/version/description/triggers) + state machine + tool list
├── skill.yaml           # mcp_tools, required_envs, fragment budget
└── (optional) card_renderers/  # CardRenderer subclasses
```

**Step-by-step**:

1. **Copy the template**: `cp -r work/shared/skills/example-echo-skill work/shared/skills/my-skill`.
2. **Edit `SKILL.md`** — change `name`, `description`, `triggers`, rewrite the
   state machine table for your domain.
3. **Edit `skill.yaml`** — declare `mcp_tools` (server + tool list) and
   `required_envs` (secrets the SKILL needs to call external APIs).
4. **Edit `__init__.py`**:
   - `register_card_type("YOUR_CARD_TYPE_1")` for every business card type you'll emit.
   - Implement `register_renderers(registry)` to register your `CardRenderer` subclass.
   - Implement `register_rewriters(registry)` to register your `MessageRewriter` subclass.
5. **Wire it into a scenario** at `work/scenarios/<scenario-name>.scenario.yaml`:

   ```yaml
   name: my-scenario
   description: ...
   system_prompt: ...
   skills:
     - my-skill
   ```

6. **Test it** with `curl -X POST /agent/chat -d '{"message": "..."}'`.
7. **(Future)** `hermetic-skill validate work/shared/skills/my-skill/` to lint
   your SKILL before opening a PR.

Full contract: [`docs/core-skill-boundary.md`](docs/core-skill-boundary.md) and
[`docs/skills/skills-authoring-guide.md`](docs/skills/skills-authoring-guide.md).

---

## Adding a new Provider

Providers (L4) wrap external LLM engines. To add a new one:

1. Create `src/hermetic_agent/providers/<your-provider>/` with:
   - `adapter.py` — implements the `AgentProvider` ABC from `providers/base.py`
   - `chat.py` — protocol mapping to your engine's event types
   - `lifecycle.py` — start / stop / health
   - `__init__.py` — re-exports
2. Register in `providers/agent_bridge.py` `AgentBridge.route()` dispatch.
3. Add a `Provider` enum value in `provider_bridge.py` if needed.
4. Add an integration test in `tests/test_<your_provider>_*`.

**Do not** modify `providers/base.py` signatures. If you need a new
abstract method, add it as default-implemented (no-op) so existing adapters
keep working.

---

## Release process

(For maintainers.)

1. Bump version in `pyproject.toml` + `src/hermetic_agent/config/settings.py`
   `app_version`. Keep them in sync.
2. Add a `CHANGELOG.md` entry under a new version section; move items from
   `[Unreleased]`.
3. Tag: `git tag -a v0.2.0 -m "v0.2.0" && git push --tags`.
4. CI publishes Docker images to GHCR (`.github/workflows/release.yml`).
5. Update `docs/hermetic-agent-open-source-evolution-plan.md` to mark
   completed milestones.

---

Questions? Open a discussion on GitHub Discussions, or ask in the PR you're
about to open. We're friendly.
