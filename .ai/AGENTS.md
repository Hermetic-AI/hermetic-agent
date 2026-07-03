# AGENTS.md — 集成编排方案 Coding Agent 协作守则

> **本文件是给所有 Coding Agent 的统一上下文**。每个 agent 在写代码前**必读**。
> 设计源文档：`docs/design/integrated-orchestration-plan.md`

---

## 1. 总体约束

- **零修改既有实现**：不要改 `src/hermetic_agent/core/scheduler.py`、`providers/*.py`、`skills/registry.py`、`mcp/registry.py` 等已有文件的**签名**。如需扩展，**加方法**或**新建模块**。
- **5 层代码分层**（依赖严格向下，CI 强校验）：
  - L1: `api/` （controllers, middleware）
  - L2: `scenarios/` （registry, router, injector, config, loader, scheduler_adapter）
  - L3: `skill_runtime/` + `auip/` + `core/suspendable_scheduler.py` + `core/turn_store.py`
  - L4: `providers/launcher.py`（新增）
  - L5: `policy/`（新增）
- **每层文件大小硬上限**：L1/L4/L5 ≤ 200 行；L2/L3 ≤ 250 行；函数 ≤ 40 行；圈复杂度 ≤ 10
- **命名约定**：L1 `*Request / *Response / *Middleware`；L2 `Scenario*` 前缀；L3 `Skill* / Card* / State* / Turn*` 前缀；L4 `*Adapter / *Launcher` 后缀
- **错误码 12 个**（见设计文档 §10）— 所有错误带可行动信息，**禁止**只返回 `"error"`
- **Pydantic 校验**所有用户输入（YAML / HTTP body / MCP payload）
- **3 个测试基线**：`pytest tests/test_<layer>_* -v` 必过

---

## 2. 已有代码 import 约定

```python
# ✅ 正确：导入已有类
from hermetic_agent.providers.base import ChatMessage, AgentConfig, SessionInfo
from hermetic_agent.providers.agent_bridge import AgentBridge
from hermetic_agent.skills.registry import SkillRegistry, Skill
from hermetic_agent.mcp.registry import MCPRegistry, MCPTool
from hermetic_agent.store.base import StorageBackend, Session, Message, Part

# ✅ 正确：导入 settings
from hermetic_agent.config.settings import Settings, get_settings

# ❌ 禁止：改这些类的签名
# ❌ 禁止：往这些类里塞新方法（请新建自己的 wrapper/扩展类）
```

---

## 3. 模块路径与命名

| 你的工作 | 文件 | 备注 |
|---|---|---|
| L5 Policy | `src/hermetic_agent/policy/{engine,path_check,command_check,network_check,audit}.py` | 各自 ≤ 200 行 |
| L2 Scenario | `src/hermetic_agent/scenarios/{config,registry,router,loader,injector,scheduler_adapter,errors}.py` | 各自 ≤ 250 行 |
| L3 Skill Runtime | `src/hermetic_agent/skill_runtime/{manifest,state_guard,prompt_builder,fragments,errors}.py` | 各自 ≤ 250 行 |
| L3 AUIP | `src/hermetic_agent/auip/{events,cards,skill_compiler}.py` | 各自 ≤ 200 行 |
| L3 Core | `src/hermetic_agent/core/{suspendable_scheduler,turn_store}.py` | 各自 ≤ 300 行 |
| L4 Launcher | `src/hermetic_agent/providers/launcher.py` | ≤ 200 行 |
| L1 中间件 | `src/hermetic_agent/scenarios/middleware.py` | ≤ 200 行 |
| 测试 | `tests/test_{policy,scenario,launcher,skill_runtime,auip}_*.py` | ≥ 80% 覆盖 |

---

## 4. 资源路径

- 资源根：`work/`（可配置 `AGENT_SCHEDULER_WORK_ROOT`）
- 场景定义：`work/scenarios/*.scenario.yaml`
- 场景资源子目录：`work/scenarios/{name}/`
- 共享资源：`work/shared/`
- 缓存：`work/cache/`
- 日志：`work/logs/{audit,routing,scenario}/`

---

## 5. 占位符（YAML 内引用）

- `${PROJECT_DIR}` = 租户工程根（= `workspace_dirs[0]`）
- `${SCENARIO_DIR}` = `work/scenarios/{name}/`
- `${WORK_ROOT}` = `/work`（或 settings 配置）
- `${WORK_SHARED}` = `work/shared/`
- `${TENANT_ID}` / `${USER_ID}` / `${AGENT_NAME}` / `${MODEL}` — 运行时注入

---

## 6. 错误处理

- **所有用户可见错误**必须用设计文档 §10 的 12 个 code 之一
- **detail 字段**给出：哪个文件/字段/规则/怎么改
- **异常类层级**：
  - `HermeticAgentError` (基类)
  - `ScenarioError` → `ScenarioLoadError` / `ScenarioResourceError` / `ScenarioValidationError`
  - `PolicyError` → `PolicyViolation`
  - `SkillRuntimeError` → `SkillBudgetExceeded` / `FragmentNotFoundError` / `SkillNotFoundError`
  - `LauncherError`
  - `AUIPError` → `CardSchemaInvalid`

---

## 7. 测试模式

- 用 `pytest-asyncio`，`asyncio_mode = "auto"`
- 已有 conftest 在 `tests/conftest.py`（**只读不修改**），需要 fixture 自己加在 `tests/test_<feature>_conftest.py`
- 每个模块必须有：`test_xxx_init` / `test_xxx_happy_path` / `test_xxx_error` 3 类

---

## 8. 提交前自检

每个 agent 写完代码后，**必须**跑：
```bash
cd "C:\WorkSpace\Coding\hermetic_agent"
python -c "from hermetic_agent.policy.engine import PolicyEngine; from hermetic_agent.scenarios import ScenarioRegistry; ..."
pytest tests/test_<你的模块>.py -v
ruff check src/hermetic_agent/<你的模块>/
```

如果失败，**自己修**，不要留给用户。

---

## 🚨 统一对话入口 (绝对约束)

**严禁新增 per-scenario 对话端点。** 所有 chat 入口只允许这 2 个, 都在 `src/hermetic_agent/api/controllers/chat_controller.py`:

- `POST /agent/chat` — 同步
- `POST /agent/chat/stream` — SSE 流式

**禁止**:
- ❌ `POST /agent/scenarios/{name}/chat`
- ❌ `POST /agent/scenarios/{name}/chat/stream`
- ❌ 在别的 controller / service 另起 chat handler
- ❌ 在前端另起"send to scenario X"服务

**Scenario 路由只在 chat 入口前发生** (`ScenarioMiddleware.route()` 6 优先级)。Client 把 `body.scenario` / `X-Scenario` 当 hint 传就行, 永远不靠 URL 路径。

详细原因 + 校验脚本见 `CLAUDE.md §Key Implementation Notes` 末尾。
