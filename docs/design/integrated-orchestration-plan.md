# Integrated Orchestration Plan：场景化路由 × 沙箱权限 × HITL/A2UI 整合方案

> 版本：v0.1  状态：**整合设计稿**  最后更新：2026-06-02
>
> **关联 3 份既有方案**（**不改动**）：
> - `docs/design/agent-sandbox-plan.md` — 沙箱 + 工具权限分层
> - `docs/skill/book-flight-skill.md` — 13 状态机票 SKILL
> - `docs/design/scenario-routing-proposal.md` — 场景化 Agent 路由
> - `docs/design/book-flight-hitl-design.md` — AUIP / SuspendableScheduler
>
> **用户 5 项明确诉求**：
> 1. **场景化路由为主**，不同场景不同安全策略 + 临时工作区（**暂不用 Docker**）+ A2UI 交互协议
> 2. **要有通用场景**（兜底）
> 3. **opencode / claudecode 启动在当前项目路径**，不要在根目录
> 4. **场景资源（prompts / mcp / skill / tools）统一管理位置**，不要乱放
> 5. **SKILL 调用遵循渐进式加载策略**
>
> **本文硬约束**：
> - ✅ 4 份既有方案**零修改**（如需改另起 PR 修订原文档）
> - ✅ 提供**不互相影响**的分阶段计划
> - ✅ 提供**代码分层 + 质量约束**，防止实现时模型自由发挥
> - ✅ Scenario 是**整合点**（不是新轮子），用配置驱动把 4 份方案拼起来

---

## 0. 摘要：Scenario = 配置包 = 整合点

> **一句话**：把"一次 chat 的执行策略"打包成一个 YAML，**Scenario** 这个抽象把 4 份既有方案用**配置 + DI** 串起来，不动它们的实现。

```
                            ┌────────────────────────────┐
                            │   Scenario YAML (1 个文件)   │
                            │                            │
                            │  routing: { ... }          │
                            │  execution: { ... }        │
                            │  security: { ... }    ← 来自 sandbox
                            │  workspace: { ... }   ← 来自 sandbox
                            │  a2ui: { ... }        ← 来自 HITL
                            │  progressive_skill: ← 用户诉求 5
                            │  resource_dirs:       ← 用户诉求 4
                            │  resources: { agent }       │
                            │  metadata: { ... }          │
                            └────────────┬───────────────┘
                                         │ 加载
                                         ▼
   ┌────────────────┐  ┌──────────────────────┐  ┌────────────────────┐
   │ ScenarioRegistry│  │  ScenarioInjector     │  │  SchedulerAdapter  │
   │  + Router       │  │  (白名单 + 注入)      │  │  (5 编排策略)       │
   │  场景路由        │  │  ← 来自 scenario-routing │  │  ← 来自 routing     │
   └────────┬───────┘  └──────────┬───────────┘  └────────┬───────────┘
            │                     │                        │
            └────────────┬────────┴────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
   ┌─────────┐    ┌──────────────┐   ┌──────────────┐
   │PolicyEng│    │SkillRuntime  │   │Providers     │
   │(安全)   │    │+ StateGuard  │   │(opencode|    │
   │← sandbox│    │+ AUIP        │   │ claude_code) │
   └─────────┘    │+ ProgressLoad│   └──────────────┘
                  │← HITL+user5  │
                  └──────────────┘
```

**关键判断**：

| 既有方案 | 在新方案中的角色 | 改动量 |
|---|---|---|
| `agent-sandbox-plan.md` | 提供 `PolicyEngine` 库（路径/命令/网络/审计） | 0（实现层） |
| `scenario-routing-proposal.md` | 提供 `ScenarioConfig` / `Registry` / `Router` / `Injector` 基线 | 0（实现层） |
| `book-flight-skill.md` | 提供 **具体业务 Skill**（flight_booking 场景加载它） | 0 |
| `book-flight-hitl-design.md` | 提供 `SuspendableScheduler` / `AUIP` 库（card + turn + checkpoint） | 0（实现层） |
| **本文** | **Schema 扩展 + 资源目录约定 + 集成指南 + 质量约束** | 全部为新增 |

> **绝对禁区**：不修改上述 4 份文档的实现层代码，只在 **新文件** / **新 schema 块** 做扩展。

---

## 1. 关系矩阵：3 方案 × 8 维度

> 用来一眼看清哪些点有覆盖、哪些点有缺口、哪些点是**整合缝**。

| 维度 | agent-sandbox | scenario-routing | book-flight + hitl | **整合后归属** |
|---|---|---|---|---|
| **D1 路由决策** | ❌ | ✅ 6 优先级（URL/Header/Body/Keyword/Intent/Default） | ❌ | **L2 ScenarioRouter**（来自 routing） |
| **D2 安全策略** | ✅ 3 档工具级 + 网络 + 审计 | ❌（只引用 `allowed_tools` 字段） | ❌ | **L5 PolicyEngine**（来自 sandbox） |
| **D3 工作区** | ✅ workspace_dirs / readonly_dirs / deny_paths | ❌ | ❌ | **L5 + L4 Launcher**（来自 sandbox） |
| **D4 Skill 加载** | ❌ | ✅ 白名单过滤 | ❌ | **L2 Injector**（来自 routing） |
| **D5 Skill 渐进式** | ❌ | ❌ | ❌ | **L3 ProgressiveLoader**（**新增**） |
| **D6 MCP 工具管理** | ❌（只在 allowed_tools 引用） | ✅ 白名单 | ❌ | **L2 Injector**（来自 routing） |
| **D7 A2UI/HITL 协议** | ❌ | ❌（只引用 `orchestration: hitl`） | ✅ AUIP / Card / Suspend | **L3 SuspendableScheduler**（来自 hitl） |
| **D8 状态机** | ❌ | ❌ | ✅ 13 状态 + 工具白名单 | **L3 StateGuard**（来自 hitl） |
| **D9 资源目录** | ⚠️ `/work/tenants/...` 草案 | ❌ | ❌ | **新增 `work/` 完整布局**（本文 §4） |
| **D10 引擎启动 cwd** | ⚠️ `cwd=workspace_dirs[0]` 一笔带过 | ❌ | ❌ | **新增 `LaunchStrategy` 字段**（本文 §3.3） |

**结论**：

- **4 份方案没有任何相互冲突**——它们是**正交**的：sandbox 管"权限"，routing 管"策略打包"，hitl 管"对话协议"，book-flight 是"业务用例"
- **3 个缺口**（D5 / D9 / D10）需要本文**新增**
- **5 个整合缝**（D1/D2/D3/D4/D6/D7/D8）需要 Scenario 显式桥接

---

## 2. 设计原则（评审 PR 时的判断标准）

| # | 原则 | 含义 | 反例 |
|---|---|---|---|
| **P1** | **Scenario 是配置，不是代码** | 所有"策略"用 YAML 声明，**不要**在 Python 里 `if scenario == ...` | 把 Scenario 写成 if-elif 链 |
| **P2** | **场景隔离是逻辑隔离，不是物理隔离（暂时）** | 不同 tenant 用 `workspace_dirs` 划清，**不用 Docker** | 引入 docker 跑 agent |
| **P3** | **整合而不修改** | 4 份既有方案**零修改**；新功能通过**新模块 + DI** 接入 | 直接改 `Scheduler.run()` 签名 |
| **P4** | **5 层依赖严格向下** | L1 → L2 → L3 → L4 → L5；**禁止**反向 import | L5 import L2 工具 |
| **P5** | **占位符而非绝对路径** | Scenario YAML 里的路径用 `${PROJECT_DIR}` 等占位符，运行时解析 | `/work/tenants/A/proj-1` 硬编码 |
| **P6** | **渐进式加载有 budget 强制** | skill 片段总 token 超过预算 → 报错，不是截断 | 静默丢弃片段 |
| **P7** | **每个 Phase 独立 shippable** | 任一 Phase 失败回滚不影响其他 Phase | 8 个 Phase 互相依赖卡死 |
| **P8** | **配置即文档** | Scenario YAML 自带注释，**能**直接给业务方阅读 | 文档和 YAML 漂移 |
| **P9** | **错误带可行动信息** | 配置错时给"哪个字段、哪条规则、怎么改" | "YAML parse error" 一句话 |
| **P10** | **三档可观测** | routing_log + audit_log + scenario_log **统一字段** | 3 套日志格式各异 |

---

## 3. 5 层代码架构 + 质量约束

### 3.1 5 层架构图

```
┌──────────────────────────────────────────────────────────────────────────┐
│ L1: API Layer                                                            │
│ ─────────────                                                            │
│  - api/app.py                          Sanic app 工厂                      │
│  - api/routes.py                       现有 chat / session / skills      │
│  - api/scenario_routes.py              /agent/scenarios/*  CRUD           │
│  - api/turn_routes.py                  /agent/turn/*  HITL                │
│  - scenarios/middleware.py             ScenarioMiddleware 拦截 /agent/*   │
│                                                                          │
│  责任: HTTP 解析 + 路由 + 注入 + 响应封装                                   │
│  严禁: 直接调 provider / 写 store                                          │
└────────────────────────┬─────────────────────────────────────────────────┘
                         │ 调用
┌────────────────────────┴─────────────────────────────────────────────────┐
│ L2: Scenario Orchestration Layer                                        │
│ ──────────────────────────────────                                       │
│  - scenarios/registry.py              ScenarioRegistry (YAML 加载)        │
│  - scenarios/router.py                ScenarioRouter (6 优先级)           │
│  - scenarios/injector.py              ScenarioInjector (白名单 + 注入)   │
│  - scenarios/config.py                ScenarioConfig + 扩展 schema       │
│  - scenarios/loader.py                占位符解析 + 路径校验               │
│  - scenarios/scheduler_adapter.py     5 编排策略 → Scheduler 映射         │
│  - scenarios/_generic/                通用场景资源                       │
│  - store/scenario_store.py            场景持久化                         │
│                                                                          │
│  责任: "这次 chat 走哪一套策略"                                           │
│  严禁: 直接调 provider, 写 Store 原表                                     │
└────────────────────────┬─────────────────────────────────────────────────┘
                         │ 调用
┌────────────────────────┴─────────────────────────────────────────────────┐
│ L3: Skill Runtime Layer                                                 │
│ ────────────────────────                                                 │
│  - skill_runtime/manifest.py          SkillManifest 加载                 │
│  - skill_runtime/state_guard.py       StateGuard (13 状态 × 工具)        │
│  - skill_runtime/prompt_builder.py    渐进式片段拼装                      │
│  - skill_runtime/fragments.py         片段加载器 + budget 控制            │
│  - auip/events.py                     TurnEvent (替代 StreamEvent)        │
│  - auip/cards.py                      Card 模型 + JSON Schema 校验       │
│  - auip/skill_compiler.py             SKILL.md → manifest 编译器          │
│  - core/suspendable_scheduler.py      可中断调度器                        │
│  - core/turn_store.py                 Checkpoint 持久化                  │
│                                                                          │
│  责任: "AI 在什么状态 / 该加载什么 / 该问什么"                              │
│  严禁: 处理 HTTP, 解析 YAML, 路由决策                                     │
└────────────────────────┬─────────────────────────────────────────────────┘
                         │ 调用
┌────────────────────────┴─────────────────────────────────────────────────┐
│ L4: Provider Layer                                                      │
│ ────────────────────                                                    │
│  - providers/base.py                  AgentProvider ABC                   │
│  - providers/opencode_adapter.py      OpenCode HTTP 适配                 │
│  - providers/claude_code_adapter.py   Claude Code CLI 适配               │
│  - providers/agent_bridge.py          SDK 路由                           │
│  - providers/launcher.py              ⭐ 新增：场景感知的引擎启动器         │
│                                                                          │
│  责任: 协议映射 + 启动控制（cwd / config 注入）                            │
│  严禁: 业务状态机, 场景路由, 卡片渲染                                      │
└────────────────────────┬─────────────────────────────────────────────────┘
                         │ 调用
┌────────────────────────┴─────────────────────────────────────────────────┐
│ L5: Infrastructure Layer                                                │
│ ──────────────────────────                                              │
│  - policy/engine.py                   EffectivePolicy                    │
│  - policy/path_check.py               路径规范化 + 拦截                   │
│  - policy/command_check.py            bash 命令前缀                       │
│  - policy/network_check.py            URL 白名单                          │
│  - policy/audit.py                    AuditLogger                        │
│  - store/base.py                      StorageBackend ABC                 │
│  - store/postgres.py                  Postgres 实现                      │
│  - store/memory.py                    Memory 实现                         │
│  - store/skill_context_store.py       Redis 业务 ctx                      │
│  - audit/                             审计入口                            │
│                                                                          │
│  责任: 物理资源（磁盘/网络/数据库）+ 安全基线                               │
│  严禁: import 任何 L1-L4 的代码                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### 3.2 依赖方向规则（CI 强校验）

```text
L1 → L2 → L3 → L4 → L5
              ↓
              L5

L1 不可 import L4, L5
L2 不可 import L4, L5
L3 不可 import L1, L2
L4 不可 import L1, L2, L3
L5 不可 import 任何上层
```

**校验方式**：`.claude/layer-rules.yaml` + `scripts/check_layer_imports.py`（CI 跑）

```python
# scripts/check_layer_imports.py（节选）
import ast, pathlib, sys

LAYER_PATTERNS = {
    "L1": ["openagent/api/", "openagent/scenarios/middleware.py"],
    "L2": ["openagent/scenarios/"],
    "L3": ["openagent/skill_runtime/", "openagent/auip/",
           "openagent/core/suspendable_scheduler.py",
           "openagent/core/turn_store.py"],
    "L4": ["openagent/providers/"],
    "L5": ["openagent/policy/", "openagent/store/", "openagent/audit/"],
}

ALLOWED_DOWNWARD = {
    "L1": ["L2"],
    "L2": ["L3"],
    "L3": ["L4", "L5"],
    "L4": ["L5"],
    "L5": [],
}

def check_file(path: pathlib.Path) -> list[str]:
    src = path.read_text()
    tree = ast.parse(src)
    layer = detect_layer(path)
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            mod = node.module
            target_layer = detect_layer_by_module(mod)
            if target_layer and target_layer not in ALLOWED_DOWNWARD[layer]:
                violations.append(f"{path}:{node.lineno} imports {mod} ({target_layer}) — not allowed from {layer}")
    return violations
```

### 3.3 每层硬性约束

| 层 | 文件数上限 | 单文件行数 | 函数行数上限 | 圈复杂度 | 测试覆盖率 |
|---|---|---|---|---|---|
| L1 | 不限 | 200 | 40 | 10 | 70% |
| L2 | 不限 | 250 | 40 | 10 | 80% |
| L3 | 不限 | 250 | 40 | 10 | 85% |
| L4 | 不限 | 200 | 40 | 10 | 70% |
| L5 | 不限 | 200 | 40 | 10 | 80% |
| **任意** | – | 300 软上限 | 40 | 10 | – |

**命名约定**：

| 层 | 文件命名 | 类命名 | 函数命名 |
|---|---|---|---|
| L1 | `*.py` | `*Request / *Response / *Middleware` | snake_case |
| L2 | `*.py` | `Scenario*` 前缀 | snake_case |
| L3 | `*.py` | `Skill* / Card* / State* / Turn*` 前缀 | snake_case |
| L4 | `*.py` | `*Adapter / *Launcher` 后缀 | snake_case |
| L5 | `*.py` | 无强约定 | snake_case |

### 3.4 配置文件结构（`.claude/`）

```
.claude/
├── layer-rules.yaml          # 5 层依赖规则
├── quality-gates.yaml        # 质量门禁
├── scenario-lint.yaml        # Scenario YAML 校验规则
└── scripts/
    ├── check_layer_imports.py
    ├── check_file_sizes.py
    ├── lint_scenario.py
    └── check_skill_budget.py
```

---

## 4. 统一资源目录布局

### 4.1 顶层布局

```
/work/                                  # 工作区根（可配置 AGENT_SCHEDULER_WORK_ROOT）
│
├── tenants/                             # 租户工作区（每个 agent 实例的 cwd 候选）
│   └── {tenant_id}/
│       └── projects/
│           └── {project_id}/            # 一个工程 = 一个 workspace_dirs[0]
│               ├── src/                 # 业务代码
│               ├── data/                # 可写数据
│               ├── tests/
│               ├── .openagent/          # ⭐ 工程级 Scenario 覆盖（可选）
│               │   ├── override.scenario.yaml
│               │   └── notes.md
│               └── README.md
│
├── scenarios/                           # ⭐ 全局场景定义（git 版本化）
│   ├── _default.scenario.yaml          # 最低兜底（不能禁用）
│   ├── _generic.scenario.yaml          # 通用场景（user 诉求 2）
│   ├── flight_booking.scenario.yaml    # 业务场景
│   ├── expense_audit.scenario.yaml
│   ├── customer_service.scenario.yaml
│   ├── code_review.scenario.yaml
│   │
│   ├── flight_booking/                  # ⭐ 场景资源子目录（user 诉求 4）
│   │   ├── prompts/                    # 系统提示词片段
│   │   │   ├── base.md
│   │   │   ├── state_s02.md
│   │   │   ├── state_s05.md
│   │   │   ├── state_s11.md
│   │   │   └── state_s13.md
│   │   ├── skills/                     # 该场景加载的 skill
│   │   │   ├── book-flight/
│   │   │   │   ├── SKILL.md            # 完整版（人读）
│   │   │   │   ├── fragments/          # ⭐ 渐进式片段（user 诉求 5）
│   │   │   │   │   ├── summary.md
│   │   │   │   │   ├── state-s02.md
│   │   │   │   │   ├── state-s05.md
│   │   │   │   │   ├── state-s11.md
│   │   │   │   │   └── state-s13.md
│   │   │   │   ├── fragments.yaml      # 片段清单
│   │   │   │   └── manifest.yaml       # 状态机 manifest
│   │   │   └── policy-compliance/
│   │   │       ├── SKILL.md
│   │   │       └── fragments/
│   │   ├── mcp/                        # 该场景用的 MCP server 配置
│   │   │   └── domestic-booking/
│   │   │       ├── config.yaml         # MCP server 启动参数
│   │   │       └── tools.yaml          # 该场景用到的工具清单
│   │   ├── tools/                      # 工具处理器（本地 handler）
│   │   │   └── local-handlers.yaml
│   │   ├── cards/                      # ⭐ A2UI 卡片 schema（hitl 卡片）
│   │   │   ├── OD_INPUT.card.yaml
│   │   │   ├── FLIGHT_LIST.card.yaml
│   │   │   ├── CABIN_LIST.card.yaml
│   │   │   ├── PASSENGER_FORM.card.yaml
│   │   │   ├── OAT_BINDING.card.yaml
│   │   │   ├── PRICE_VERIFY.card.yaml
│   │   │   ├── POLICY_DECISION.card.yaml
│   │   │   ├── ORDER_CONFIRM.card.yaml
│   │   │   ├── ORDER_SUCCESS.card.yaml
│   │   │   └── CANNOT_ORDER.card.yaml
│   │   ├── state-machine.yaml          # 13 状态转移图
│   │   ├── skills.manifest.yaml        # Skill → 片段映射
│   │   └── tests/                      # 该场景的剧本测试
│   │       ├── playbook_a.yaml         # Happy Path
│   │       ├── playbook_c.yaml         # 变价
│   │       └── playbook_e.yaml         # 差标
│   │
│   └── _generic/                       # ⭐ 通用场景资源
│       ├── prompts/
│       │   └── base.md                 # "你是 OpenAgent 通用助手"
│       ├── skills/
│       │   └── README.md               # 通用场景不加载具体 skill
│       ├── mcp/
│       │   └── README.md
│       └── cards/
│           └── CHAT_FALLBACK.card.yaml
│
├── shared/                              # 跨租户共享资源（只读）
│   ├── skills/                          # 全局共享 skill
│   │   ├── faq-search/
│   │   ├── handoff-to-human/
│   │   └── common-prompts/
│   ├── mcp/                             # 全局共享 MCP
│   │   ├── web-search/
│   │   ├── code-search/
│   │   └── policy-checker/
│   ├── prompts/                         # 全局共享 prompt 片段
│   │   ├── base-ai-persona.md
│   │   ├── safety-rails.md
│   │   └── tool-usage-hints.md
│   └── docs/                            # 公共文档（reference only）
│       ├── openagent-architecture.md
│       └── scenario-authoring-guide.md
│
├── cache/                               # 临时缓存（运行时写）
│   ├── opencode-configs/{scenario_name}/
│   └── claude-configs/{scenario_name}/
│
├── logs/                                # 日志
│   ├── audit/
│   ├── routing/
│   └── scenario/
│
└── archive/                             # 归档（只读历史）
```

### 4.2 占位符约定（Scenario YAML 内引用）

| 占位符 | 含义 | 解析时机 |
|---|---|---|
| `${PROJECT_DIR}` | 租户工程的根（= `workspace_dirs[0]`） | ScenarioLoader 加载时 |
| `${SCENARIO_DIR}` | 场景资源子目录（= `work/scenarios/{name}/`） | 加载时 |
| `${WORK_ROOT}` | 工作区根（默认 `/work`） | 启动时从 settings |
| `${WORK_SHARED}` | 共享资源目录 | 启动时 |
| `${TENANT_ID}` | 当前租户（从 auth middleware 注入） | 请求时 |
| `${USER_ID}` | 当前用户 | 请求时 |
| `${AGENT_NAME}` | 选定 agent 实例名 | 路由时 |
| `${MODEL}` | 选定模型 | 路由时 |

**解析器**（`scenarios/loader.py`）：

```python
def resolve_placeholders(value: Any, ctx: dict[str, str]) -> Any:
    """递归替换字符串里的 ${KEY}。"""
    if isinstance(value, str):
        return re.sub(
            r"\$\{([A-Z_]+)\}",
            lambda m: ctx.get(m.group(1), m.group(0)),  # 找不到保留原样
            value,
        )
    if isinstance(value, list):
        return [resolve_placeholders(v, ctx) for v in value]
    if isinstance(value, dict):
        return {k: resolve_placeholders(v, ctx) for k, v in value.items()}
    return value
```

### 4.3 Scenario 资源解析顺序

```
请求进入
  ↓
1. ScenarioMiddleware.route()
  ↓ 拿到 ScenarioConfig（version 化）
2. ScenarioLoader.resolve_placeholders(cfg, ctx)
  ↓ 把所有 ${...} 替换为绝对路径
3. ScenarioLoader.validate_paths(cfg)
  ↓ 检查 workspace_dirs / scenarios_dir / cards_dir 都存在
  ↓ 检查所有引用的 skill 都存在
  ↓ 检查所有引用的 mcp server 配置可加载
  ↓ 失败 → 503 SCENARIO_RESOURCE_UNAVAILABLE + 详细路径
4. ScenarioInjector.inject(cfg, user_message)
  ↓ 过滤 skills / tools
  ↓ 加载 progressive_skill 初始片段
  ↓
5. 注入完成，交给 SchedulerAdapter
```

### 4.4 opencode / claudecode 启动 cwd（user 诉求 3）

**核心原则**：**cwd 永远是 `${PROJECT_DIR}`，绝不是 `/` 或 `$HOME`**

```python
# providers/launcher.py
class EngineLauncher:
    """场景感知的引擎启动器."""

    def launch(self, scenario: ScenarioConfig, agent_config: AgentConfig) -> EngineHandle:
        primary_workspace = scenario.workspace.workspace_dirs[0]  # = ${PROJECT_DIR}
        if primary_workspace in ("/", os.path.expanduser("~"), ""):
            raise LauncherError(
                f"Scenario {scenario.name}.workspace.workspace_dirs[0] = {primary_workspace!r}; "
                f"refusing to launch engine at root. Set PROJECT_DIR in scenario config."
            )
        # 真实路径校验
        resolved = pathlib.Path(primary_workspace).resolve()
        if not resolved.exists():
            raise LauncherError(f"Workspace {primary_workspace} does not exist")

        if agent_config.sdk_type == "opencode":
            return self._launch_opencode(scenario, agent_config, str(resolved))
        if agent_config.sdk_type == "claude_code":
            return self._launch_claude_code(scenario, agent_config, str(resolved))
        raise LauncherError(f"Unknown sdk_type: {agent_config.sdk_type}")

    def _launch_opencode(self, scenario, agent, cwd: str) -> EngineHandle:
        config = self._render_opencode_config(scenario, agent, cwd)
        config_path = self._write_temp_config(scenario.name, config)
        proc = subprocess.Popen(
            ["opencode", "serve",
             "--port", str(self._pick_port()),
             "--hostname", "127.0.0.1",
             "--cwd", cwd,                          # ⭐ user 诉求 3
             "--config", config_path],
            cwd=cwd,                                # ⭐ 双重保险
        )
        return EngineHandle(proc, base_url=f"http://127.0.0.1:{port}", cwd=cwd)

    def _launch_claude_code(self, scenario, agent, cwd: str) -> EngineHandle:
        # ClaudeCode 是 per-session 子进程，不常驻；cwd 通过 ClaudeAgentOptions 传
        # 校验后存到 handle 元数据
        return ClaudeCodeHandle(
            cli_path=agent.base_url or "claude",
            cwd=cwd,                                # ⭐ user 诉求 3
            effective_policy=scenario.security,
        )
```

**`/ready` 校验**（`api/app.py`）：

```python
def _check_engine_cwd(app: Sanic) -> tuple[bool, str]:
    """所有已注册 agent 的 cwd 必须非根."""
    for name, cfg in app.ctx.bridge.list_agents().items():
        # 找到该 agent 关联的 default scenario
        scenario = app.ctx.scenario_registry.get_for_agent(name)
        if scenario is None:
            return False, f"agent {name} has no default scenario"
        cwd = scenario.workspace.workspace_dirs[0]
        if cwd in ("/", "~", os.path.expanduser("~")):
            return False, f"agent {name} default scenario {scenario.name} cwd is {cwd}"
    return True, "all engine cwds are project-relative"
```

---

## 5. 扩展 ScenarioConfig Schema

### 5.1 完整字段定义

> 在 `scenario-routing-proposal.md §3` 原 schema 上**叠加** 5 个块（**新增字段，不删原字段**）。

```yaml
# ============================================================
# 必填（与 routing 原 schema 一致）
# ============================================================
name: flight_booking                # 唯一场景名（kebab-case）
version: "1.2.0"                    # 语义化版本

# ============================================================
# 元信息（新增 owner / contact / tier）
# ============================================================
description: "飞鹤差旅机票预订主流程"
enabled: true
tags: [travel, booking, prod]
owner: team-travel-ai
contact: travel-ai@feihe.com
tier: gold                           # bronze | silver | gold | platinum

# ============================================================
# 路由规则（与原 schema 一致）
# ============================================================
routing:
  trigger_keywords: [订票, 机票, 航班, flight]
  trigger_intent: null
  url_path: null
  priority: 100

# ============================================================
# 执行策略（与原 schema 一致）
# ============================================================
execution:
  system_prompt: |
    你是飞鹤差旅 AI 助手...
  skills: [book-flight, policy-compliance]
  tools: [query_flight_basic, choose_cabin, submit_order]
  orchestration: hitl               # ⭐ 触发 SuspendableScheduler
  hitl:
    card_schemas: [book-flight-v1]
    suspend_timeout: 300
    state_machine: ${SCENARIO_DIR}/state-machine.yaml

# ============================================================
# ⭐ 新增 1: security（来自 agent-sandbox-plan.md §3.2）
# ============================================================
security:
  tool_level: standard              # safe | standard | full
  allowed_tools: [Read, Grep, Glob, Write, Edit, Bash, WebSearch]
  denied_tools: []                  # 黑名单叠加
  allowed_commands: [ls, cat, grep, git, npm, pnpm, python, pytest]
  denied_commands: [rm -rf, sudo, curl, wget, ssh, scp, dd]
  network: local                    # off | local | any
  max_turns: 30
  max_budget_usd: 2.0
  require_approval_for_writes: true

# ============================================================
# ⭐ 新增 2: workspace（来自 sandbox §5.1，user 诉求 3）
# ============================================================
workspace:
  strategy: project_relative        # project_relative | absolute | readonly_only
  workspace_dirs:
    - ${PROJECT_DIR}                # ⭐ user 诉求 3：永远是项目路径
  readonly_dirs:
    - ${SCENARIO_DIR}/prompts
    - ${SCENARIO_DIR}/cards
    - ${WORK_SHARED}/docs
    - ${WORK_SHARED}/skills
  deny_dirs:
    - /etc
    - ~/.ssh
    - ${HOME}
  deny_path_patterns:
    - "**/.env"
    - "**/.env.*"
    - "**/id_rsa"
    - "**/id_ed25519"
    - "**/*.pem"
    - "**/*.key"
    - "**/secrets/**"
  launcher:
    prefer_engine: claude_code      # claude_code | opencode | auto
    fallback_engine: opencode
    engine_config:                  # 引擎特定配置
      claude_code:
        permission_mode: acceptEdits
        setting_sources: [project]
      opencode:
        config_template: standard   # safe | standard | full

# ============================================================
# ⭐ 新增 3: a2ui（来自 book-flight-hitl-design.md，user 诉求 1）
# ============================================================
a2ui:
  enabled: true
  protocol: auip                    # auip | a2ui-google | custom
  cards_dir: ${SCENARIO_DIR}/cards
  state_machine: ${SCENARIO_DIR}/state-machine.yaml
  default_card_timeout: 300
  ask_user:
    tool_name: ask_user
    schema: ${SCENARIO_DIR}/ask_user.schema.json
  renderer_hint: react_aui_v1       # 前端按此加载对应 renderer
  progressive_loading: true         # 是否启用 skill 片段按 state 加载

# ============================================================
# ⭐ 新增 4: progressive_skill（user 诉求 5）
# ============================================================
progressive_skill:
  strategy: on_demand               # on_demand | all | explicit
  budget_tokens: 4000               # ⭐ 强制上限
  budget_policy: error              # error | warn | truncate
  initial_skills:                   # 任何 state 都会加载的
    - name: book-flight
      mode: summary                 # 只加载 fragments/summary.md
  load_on_state:                    # ⭐ 按 state 加载
    S01: []                         # INIT 不需要额外片段
    S02:
      - book-flight:state-s02       # 城市+日期提示
    S03:
      - book-flight:state-s02
    S04:
      - book-flight:state-s02
    S05:
      - book-flight:state-s05       # 航班选择
      - book-flight:cabin-rules     # 舱位规则
    S06:
      - book-flight:state-s05
      - book-flight:state-s06
    S07:
      - book-flight:state-s07
    S08:
      - book-flight:state-s08       # 乘机人
    S09:
      - book-flight:state-s09
    S10:
      - book-flight:state-s10
    S11:
      - book-flight:state-s11       # 差标决策
    S12:
      - book-flight:state-s12
    S13:
      - book-flight:state-s13       # 订单确认
    F1: []
    F2:
      - book-flight:state-f02
    F3:
      - book-flight:state-f03

# ============================================================
# ⭐ 新增 5: resource_dirs（user 诉求 4）
# ============================================================
resource_dirs:
  prompts: ${SCENARIO_DIR}/prompts
  skills: ${SCENARIO_DIR}/skills
  shared_skills: ${WORK_SHARED}/skills
  mcp_servers: ${SCENARIO_DIR}/mcp
  shared_mcp: ${WORK_SHARED}/mcp
  tools: ${SCENARIO_DIR}/tools
  cards: ${SCENARIO_DIR}/cards
  state_machine: ${SCENARIO_DIR}/state-machine.yaml
  tests: ${SCENARIO_DIR}/tests

# ============================================================
# 资源分配（与原 schema 一致）
# ============================================================
resources:
  agent: claude-core                # 关联到 AgentConfig.name
  model: claude-sonnet-4-5
  timeout: 300

# ============================================================
# 业务元数据（与原 schema 一致）
# ============================================================
metadata:
  cost_center: T-1001
  ab_group: control
  sla_tier: gold
  dashboard_url: https://grafana/...
```

### 5.2 字段分组 + 来源标注

| 字段 | 来源 | 状态 |
|---|---|---|
| `name` / `version` / `description` / `enabled` / `tags` / `owner` | routing 原 schema | 不变 |
| `routing: { ... }` | routing 原 schema | 不变 |
| `execution.system_prompt` / `execution.skills` / `execution.tools` / `execution.orchestration` | routing 原 schema | 不变 |
| `execution.hitl: { ... }` | routing 原 schema + 增强 | 扩展 |
| `security: { ... }` | sandbox §3.2 | **新增块** |
| `workspace: { ... }` | sandbox §5.1 + §3.3 | **新增块** |
| `a2ui: { ... }` | hitl §4 | **新增块** |
| `progressive_skill: { ... }` | 本文新增（user 诉求 5） | **新增块** |
| `resource_dirs: { ... }` | 本文新增（user 诉求 4） | **新增块** |
| `resources: { ... }` | routing 原 schema | 不变 |
| `metadata: { ... }` | routing 原 schema | 不变 |

### 5.3 Pydantic 校验（`scenarios/config.py`）

```python
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Literal

class SecurityConfig(BaseModel):
    tool_level: Literal["safe", "standard", "full"] = "standard"
    allowed_tools: list[str] = Field(default_factory=list)
    denied_tools: list[str] = Field(default_factory=list)
    allowed_commands: list[str] = Field(default_factory=list)
    denied_commands: list[str] = Field(default_factory=list)
    network: Literal["off", "local", "any"] = "local"
    max_turns: int = Field(50, ge=1, le=200)
    max_budget_usd: float = Field(5.0, ge=0)
    require_approval_for_writes: bool = True

    @field_validator("denied_commands")
    @classmethod
    def denied_commands_not_empty_dangerous(cls, v):
        # ⭐ 强制：denied_commands 必须包含危险命令
        required = ["rm -rf", "sudo", "dd"]
        for cmd in required:
            if not any(cmd in d for d in v):
                raise ValueError(
                    f"security.denied_commands must include '{cmd}' (or similar). "
                    f"Got: {v}. Add it explicitly."
                )
        return v

class WorkspaceConfig(BaseModel):
    strategy: Literal["project_relative", "absolute", "readonly_only"] = "project_relative"
    workspace_dirs: list[str] = Field(min_length=1)
    readonly_dirs: list[str] = Field(default_factory=list)
    deny_dirs: list[str] = Field(default_factory=list)
    deny_path_patterns: list[str] = Field(default_factory=list)
    launcher: "LauncherConfig"

    @field_validator("workspace_dirs")
    @classmethod
    def workspace_not_root(cls, v):
        for p in v:
            resolved = p.replace("${PROJECT_DIR}", "/tmp/__placeholder__")
            if resolved in ("/", "~", "~/", "/root", "/home", ""):
                raise ValueError(
                    f"workspace.workspace_dirs contains forbidden root path: {p!r}. "
                    f"Must be project-relative. (user 诉求 3)"
                )
        return v

class A2UIConfig(BaseModel):
    enabled: bool = False
    protocol: Literal["auip", "a2ui-google", "custom"] = "auip"
    cards_dir: str | None = None
    state_machine: str | None = None
    default_card_timeout: int = 300
    renderer_hint: str = "react_aui_v1"

class ProgressiveSkillConfig(BaseModel):
    strategy: Literal["on_demand", "all", "explicit", "none"] = "on_demand"
    budget_tokens: int = Field(4000, ge=500, le=32000)
    budget_policy: Literal["error", "warn", "truncate"] = "error"
    initial_skills: list[dict] = Field(default_factory=list)
    load_on_state: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def check_state_coverage(self):
        # ⭐ 如果 orchestration=hitl, 必须为关键等待态声明片段
        # 校验在 ScenarioConfig.model_validator 里做
        return self

class ScenarioConfig(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    description: str = ""
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)
    owner: str | None = None
    contact: str | None = None
    tier: Literal["bronze", "silver", "gold", "platinum"] = "silver"
    routing: RoutingConfig
    execution: ExecutionConfig
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    workspace: WorkspaceConfig
    a2ui: A2UIConfig = Field(default_factory=A2UIConfig)
    progressive_skill: ProgressiveSkillConfig = Field(default_factory=ProgressiveSkillConfig)
    resource_dirs: dict[str, str] = Field(default_factory=dict)
    resources: ResourcesConfig
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def cross_field_check(self):
        # ⭐ HITL 模式必须有 a2ui.enabled
        if self.execution.orchestration == "hitl" and not self.a2ui.enabled:
            raise ValueError(
                f"Scenario {self.name}: orchestration=hitl requires a2ui.enabled=true. "
                f"Either enable A2UI or change orchestration."
            )

        # ⭐ workspace_dirs[0] 不能是危险路径
        first_ws = self.workspace.workspace_dirs[0]
        if "${PROJECT_DIR}" not in first_ws and not first_ws.startswith("/work/"):
            raise ValueError(
                f"Scenario {self.name}: workspace.workspace_dirs[0] = {first_ws!r} "
                f"is not under /work/ and doesn't use ${{PROJECT_DIR}}. Refusing."
            )

        # ⭐ on_demand 模式下必须声明 load_on_state
        if self.progressive_skill.strategy == "on_demand" and not self.progressive_skill.load_on_state:
            raise ValueError(
                f"Scenario {self.name}: progressive_skill.strategy=on_demand "
                f"requires non-empty load_on_state."
            )

        return self
```

### 5.4 加载校验顺序（`scenarios/loader.py`）

```python
def load_scenario(path: Path, ctx: dict) -> ScenarioConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    # 1. 占位符替换
    resolved = resolve_placeholders(raw, ctx)

    # 2. Pydantic 校验（schema 级别）
    try:
        cfg = ScenarioConfig.model_validate(resolved)
    except ValidationError as e:
        raise ScenarioLoadError(
            f"Scenario {path.name} failed validation:\n"
            f"  {e.error_count()} errors\n"
            + "\n".join(f"  - {err['loc']}: {err['msg']}" for err in e.errors()[:10])
        )

    # 3. 物理资源校验
    _validate_resources(cfg)  # 检查路径存在、skill 文件存在、card yaml 合法

    # 4. 二次校验：HITL 必填项
    if cfg.execution.orchestration == "hitl":
        _validate_hitl_setup(cfg)  # 检查 state_machine.yaml / cards_dir 都有

    return cfg


def _validate_resources(cfg: ScenarioConfig) -> None:
    errors = []
    for ws in cfg.workspace.workspace_dirs:
        if not Path(ws).exists():
            errors.append(f"workspace_dir not found: {ws}")
    for ro in cfg.workspace.readonly_dirs:
        if not Path(ro).exists():
            errors.append(f"readonly_dir not found: {ro}")
    cards_dir = Path(cfg.a2ui.cards_dir) if cfg.a2ui.cards_dir else None
    if cards_dir and not cards_dir.exists():
        errors.append(f"a2ui.cards_dir not found: {cards_dir}")
    for skill_name in cfg.execution.skills:
        skill_path = Path(cfg.resource_dirs.get("skills", "")) / skill_name / "SKILL.md"
        if not skill_path.exists():
            errors.append(f"skill SKILL.md not found: {skill_path}")
    if errors:
        raise ScenarioResourceError(
            f"Scenario {cfg.name} has missing resources:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )
```

---

## 6. 通用 `_generic` 场景

> **User 诉求 2**："要有通用的场景"

### 6.1 设计目标

- **最低权限**：所有 agent 的"安全默认值"
- **最小资源**：不加载任何特定 skill
- **最大兼容性**：任何 chat 都能被它处理
- **不抢占**：priority 最高（99999），只在没匹配时兜底

### 6.2 完整 YAML

```yaml
# /work/scenarios/_generic.scenario.yaml
# ============================================================
# 通用兜底场景 — 当没有任何业务场景匹配时使用
# 严禁: 加载任何特定业务 skill / mcp
# 严禁: 修改此文件以"扩展" — 新业务请创建新 scenario
# ============================================================
name: _generic
version: "1.0.0"
description: |
  通用兜底场景。
  触发条件: 没有其他 scenario 通过 6 优先级路由命中。
  行为: 简短回复 + 主动询问用户想做什么 + 不执行业务操作。
enabled: true
tags: [fallback, generic]
owner: openagent-core
tier: bronze

# ============================================================
# 路由: 故意不配置任何 trigger
# 兜底逻辑由 ScenarioRouter 的 "default" 路径实现
# ============================================================
routing:
  trigger_keywords: []       # 空 = 不参与 keyword 匹配
  trigger_intent: null
  url_path: null
  priority: 99999            # 最低优先级

# ============================================================
# 执行策略: 最小系统提示词 + 零 skill + 零 tool
# ============================================================
execution:
  system_prompt: |
    你是 OpenAgent 通用助手。当前没有匹配到具体业务场景。
    请简短回复用户（不超过 50 字），并主动询问用户想做什么。
    如果用户的请求明显属于某个业务（如订票、报销），
    提示用户「请尝试更具体的描述，例如『订明天的机票』」。

    严禁:
    - 假装你能调用任何业务工具
    - 编造订单、价格、政策
    - 替用户做决策

    你的能力: 通用问答 + 引导用户表达意图。
  skills: []                 # 不加载任何业务 skill
  tools: []                  # 不暴露任何业务 MCP tool
  orchestration: single      # 不允许 hitl / chain / parallel

# ============================================================
# 安全: 最严的 safe 档
# ============================================================
security:
  tool_level: safe           # ⭐ 只读、不能 bash
  allowed_tools: [Read, Grep, Glob]   # 仅静态阅读工具
  denied_tools: [Write, Edit, Bash, WebFetch, WebSearch]
  allowed_commands: []       # safe 档不允许任何命令
  denied_commands: [rm -rf, sudo, dd, mkfs, chmod 777, ":(){:|:&};:"]
  network: off               # ⭐ 完全禁止出网
  max_turns: 5               # ⭐ 极短
  max_budget_usd: 0.1        # ⭐ 极低预算
  require_approval_for_writes: true

# ============================================================
# 工作区: 只读 + 严格限制
# ============================================================
workspace:
  strategy: project_relative
  workspace_dirs:
    - ${PROJECT_DIR}         # 只读 cwd
  readonly_dirs:
    - ${WORK_SHARED}/docs    # 仅公共文档可读
  deny_dirs:
    - /etc
    - ~/.ssh
    - ~/.aws
    - ~/.config/gcloud
    - ${HOME}
  deny_path_patterns:
    - "**/.env"
    - "**/.env.*"
    - "**/id_rsa"
    - "**/id_ed25519"
    - "**/*.pem"
    - "**/*.key"
    - "**/secrets/**"
    - "**/credentials/**"
  launcher:
    prefer_engine: claude_code
    fallback_engine: opencode

# ============================================================
# A2UI: 关闭
# ============================================================
a2ui:
  enabled: false             # ⭐ 通用场景不挂卡片
  protocol: auip

# ============================================================
# 渐进式 SKILL: 不加载任何 skill
# ============================================================
progressive_skill:
  strategy: none             # ⭐ 不加载
  budget_tokens: 500
  budget_policy: error
  initial_skills: []
  load_on_state: {}

# ============================================================
# 资源目录: 通用场景专用
# ============================================================
resource_dirs:
  prompts: ${WORK_SHARED}/prompts/_generic
  skills: ${WORK_SHARED}/skills/_generic
  mcp_servers: ${WORK_SHARED}/mcp/_generic
  tools: ${WORK_SHARED}/tools/_generic
  cards: ${WORK_SHARED}/cards/_generic

# ============================================================
# 资源分配: 任何 agent 都能跑
# ============================================================
resources:
  agent: null               # 不指定 agent — 由 router 自动选
  model: null               # 用 agent 默认模型
  timeout: 30               # 30s 超时

# ============================================================
# 元数据
# ============================================================
metadata:
  cost_center: O-0001       # 通用场景不计费到业务
  ab_group: control
  sla_tier: bronze
  is_fallback: true         # 标记为兜底, 不计入业务监控
  dashboard_url: null
```

### 6.3 其他示例场景（最小骨架）

```yaml
# /work/scenarios/expense_audit.scenario.yaml（最小化版）
name: expense_audit
version: "1.0.0"
description: "差旅报销单 AI 审核"
enabled: true
tags: [finance, audit]
owner: team-finance-ai
tier: gold
routing:
  trigger_keywords: [报销, 审核, 差旅费, expense]
  priority: 90
execution:
  system_prompt: "你是差旅报销审核员..."
  skills: [expense-rules, risk-scoring]
  tools: [fetch_receipt_ocr, query_trip_record, check_policy_db]
  orchestration: parallel
  parallel:
    n: 4
    aggregation: merge
security:
  tool_level: standard
  network: local
  max_turns: 20
workspace:
  workspace_dirs: [${PROJECT_DIR}]
  readonly_dirs: [${WORK_SHARED}/docs/finance]
  deny_path_patterns: ["**/.env"]
  launcher:
    prefer_engine: opencode
a2ui: { enabled: false }
progressive_skill:
  strategy: all             # 审核场景小，all 即可
  budget_tokens: 6000
resource_dirs:
  skills: ${SCENARIO_DIR}/skills
  tools: ${SCENARIO_DIR}/tools
resources:
  agent: opencode-core
  timeout: 180
```

---

## 7. 渐进式 SKILL 加载

> **User 诉求 5**："SKILL 调用要遵循渐进式加载策略"

### 7.1 三种策略

| 策略 | 何时用 | 行为 |
|---|---|---|
| `none` | 通用场景 / 极简对话 | 不加载任何 skill 片段 |
| `all` | 业务简单 / skill 短 | 一次性把 SKILL.md 全量加载 |
| `on_demand` | **book-flight 这种复杂状态机** | 按 `current_state` 加载对应 fragment |
| `explicit` | 复杂 skill，开发者想精确控制 | 按 `initial_skills` + 显式调用加载 |

### 7.2 Fragment 目录约定

```
scenarios/flight_booking/skills/book-flight/
├── SKILL.md                  # 完整版（人读，约 600 行）
├── fragments.yaml            # 片段清单 + token 预估
├── fragments/
│   ├── summary.md            # ~500 tokens，概述 + 状态图
│   ├── state-s01.md          # INIT 状态提示
│   ├── state-s02.md          # 城市+日期
│   ├── state-s05.md          # 航班选择
│   ├── state-s06.md          # 舱位列表
│   ├── state-s07.md          # 舱位确认
│   ├── state-s08.md          # 乘机人
│   ├── state-s09.md          # OAT 绑定
│   ├── state-s10.md          # 价格校验
│   ├── state-s11.md          # 差标决策
│   ├── state-s12.md          # 订单预览
│   ├── state-s13.md          # 订单确认
│   ├── state-f01.md          # AUTO_SUBMIT
│   ├── state-f02.md          # CANNOT_ORDER
│   ├── state-f03.md          # POLICY_MULTI_CONDITION
│   ├── cabin-rules.md        # 跨状态共享片段
│   └── policy-hints.md       # 跨状态共享片段
└── manifest.yaml             # 13 状态 × 工具白名单
```

### 7.3 fragments.yaml 格式

```yaml
# scenarios/flight_booking/skills/book-flight/fragments.yaml
version: "1.0"
fragments:
  - id: summary
    path: fragments/summary.md
    estimated_tokens: 480

  - id: state-s01
    path: fragments/state-s01.md
    estimated_tokens: 120

  - id: state-s02
    path: fragments/state-s02.md
    estimated_tokens: 280

  - id: state-s05
    path: fragments/state-s05.md
    estimated_tokens: 350

  - id: state-s06
    path: fragments/state-s06.md
    estimated_tokens: 220

  - id: state-s07
    path: fragments/state-s07.md
    estimated_tokens: 180

  # ... 略

  - id: cabin-rules
    path: fragments/cabin-rules.md
    estimated_tokens: 200
    shared: true              # 跨多个 state 共享

  - id: policy-hints
    path: fragments/policy-hints.md
    estimated_tokens: 250
    shared: true
```

### 7.4 加载器（`skill_runtime/fragments.py`）

```python
class FragmentLoader:
    """按 state 加载 skill 片段，强制 budget."""

    def __init__(self, registry: SkillRegistry, budget: int, policy: str = "error"):
        self._registry = registry
        self._budget = budget
        self._policy = policy

    def load(
        self,
        scenario: ScenarioConfig,
        current_state: str,
    ) -> tuple[str, FragmentLoadReport]:
        """返回 (拼好的 prompt 片段, 加载报告)."""
        if scenario.progressive_skill.strategy == "none":
            return "", FragmentLoadReport(loaded=[], total_tokens=0)

        if scenario.progressive_skill.strategy == "all":
            return self._load_all(scenario)
        # on_demand / explicit
        return self._load_on_demand(scenario, current_state)

    def _load_on_demand(
        self, scenario: ScenarioConfig, current_state: str
    ) -> tuple[str, FragmentLoadReport]:
        report = FragmentLoadReport(loaded=[], total_tokens=0)
        fragments_text = []

        # 1. 加载 initial_skills (summary 模式)
        for init in scenario.progressive_skill.initial_skills:
            text, n = self._load_fragment(init["name"], init.get("mode", "summary"))
            fragments_text.append(text)
            report.loaded.append(f"{init['name']}#{init.get('mode')}")
            report.total_tokens += n

        # 2. 加载当前 state 对应的片段
        state_fragments = scenario.progressive_skill.load_on_state.get(
            current_state, []
        )
        for frag_id in state_fragments:
            skill_name, frag_name = frag_id.split(":", 1)
            text, n = self._load_fragment(skill_name, frag_name)
            fragments_text.append(text)
            report.loaded.append(frag_id)
            report.total_tokens += n

        # 3. Budget 校验
        if report.total_tokens > self._budget:
            msg = (
                f"Skill fragment budget exceeded: {report.total_tokens} > {self._budget}. "
                f"Loaded: {report.loaded}. "
                f"Scenario: {scenario.name}, state: {current_state}."
            )
            if self._policy == "error":
                raise SkillBudgetExceeded(msg)
            elif self._policy == "warn":
                logger.warning("skill_budget_exceeded", **asdict(report), budget=self._budget)
            elif self._policy == "truncate":
                # 截断最后一个片段
                fragments_text = self._truncate(fragments_text, self._budget)

        return "\n\n---\n\n".join(fragments_text), report

    def _load_fragment(self, skill_name: str, fragment_id: str) -> tuple[str, int]:
        skill = self._registry.get(skill_name)
        if skill is None:
            raise SkillNotFoundError(skill_name)
        frag_path = skill.fragments_dir / f"{fragment_id}.md"
        if not frag_path.exists():
            raise FragmentNotFoundError(skill_name, fragment_id)
        text = frag_path.read_text(encoding="utf-8")
        # 粗略 token 估算: 中英文混合, 1 token ≈ 1.5 字符
        tokens = len(text) * 2 // 3
        return text, tokens
```

### 7.5 Prompt 拼装（`skill_runtime/prompt_builder.py`）

```python
class PromptBuilder:
    """拼装 system prompt = 框架 base + scenario + skill 片段."""

    def build(
        self,
        scenario: ScenarioConfig,
        current_state: str,
        messages: list[ChatMessage],
    ) -> str:
        parts = []

        # 1. 框架 base
        parts.append(self._framework_base())

        # 2. Scenario 级 system_prompt
        parts.append(scenario.execution.system_prompt)

        # 3. A2UI 提示 (如果启用)
        if scenario.a2ui.enabled:
            parts.append(self._aui_instructions(scenario))

        # 4. Skill 片段 (按 progressive 策略)
        skill_text, report = self._fragment_loader.load(scenario, current_state)
        if skill_text:
            parts.append(f"[Active skill fragments: {report.loaded}]\n{skill_text}")

        # 5. 当前 state 提示
        parts.append(f"[Current state: {current_state}]")

        # 6. 对话历史 (由 framework 处理)
        return "\n\n".join(parts)
```

---

## 8. A2UI / HITL 在 Scenario 层的接入

> **User 诉求 1**："不同场景可以有不同的 A2UI 交互协议"

### 8.1 触发链路

```
Scenario.execution.orchestration == "hitl"
        ↓
SchedulerAdapter.execute("hitl", scenario, injection)
        ↓
SuspendableScheduler.run_turn(
    session_id, prompt, skill_hint=scenario.name,
    skill_manifest=load_manifest(scenario.a2ui.state_machine),
    cards_dir=scenario.a2ui.cards_dir,
    security=scenario.security,
    workspace=scenario.workspace,
    progressive=scenario.progressive_skill,
)
        ↓
SuspendableScheduler 在 state machine 驱动下:
  - 加载 state-machine.yaml
  - 拦截 ask_user tool
  - 推 card (从 cards_dir/ 渲染)
  - 写 checkpoint
  - suspend
        ↓
前端: <AUIRenderer card={...} onSubmit={...} />
        ↓
POST /agent/turn/<id>/resume
        ↓
SuspendableScheduler.resume()  → 续跑
```

### 8.2 Scenario 加载 State Machine

```python
# scenarios/loader.py
def load_state_machine(scenario: ScenarioConfig) -> SkillManifest:
    """从 scenario.a2ui.state_machine 加载状态机."""
    path = Path(scenario.a2ui.state_machine)
    if not path.exists():
        if scenario.execution.orchestration == "hitl":
            raise ScenarioLoadError(
                f"Scenario {scenario.name}: orchestration=hitl but state_machine not found: {path}"
            )
        return SkillManifest.empty()
    return SkillManifest.from_yaml(path)
```

### 8.3 Card YAML 格式

```yaml
# /work/scenarios/flight_booking/cards/FLIGHT_LIST.card.yaml
card_type: FLIGHT_LIST
schema_version: "1.0"
title: "请选择航班"
body:
  message: "为您找到以下航班，请选择"
fields: []
options:
  - id: flight_1
    label: "CA1501 09:00-11:20 ¥820 经济舱"
    value: {flightId: "CA1501-20260603-0900"}
  - id: flight_2
    label: "MU5102 14:00-16:15 ¥1,250 经济舱"
    value: {flightId: "MU5102-20260603-1400"}
actions:
  - id: select
    label: "确认选择"
    style: primary
metadata:
  state: S05
  skill: book-flight
  schema_id: book-flight-v1
```

```yaml
# /work/scenarios/flight_booking/cards/POLICY_DECISION.card.yaml
card_type: POLICY_DECISION
schema_version: "1.0"
title: "差标超标，请决策"
body:
  message: "您选择的航班超出差标 ¥320"
context:
  current_price: 1520
  policy_limit: 1200
  surcharge: 320
  policy_overrun: true
decision_buttons:
  - id: pay_surcharge
    code: PAY_SURCHARGE
    label: "差额补现"
    style: primary
    surcharge: 320
    policy_hint: "个人承担 ¥320"
  - id: choose_low
    code: CHOOSE_LOW_PRICE_ALTERNATIVE
    label: "换更便宜的"
    style: secondary
  - id: abort
    code: ABORT
    label: "取消"
    style: ghost
metadata:
  state: S11
  skill: book-flight
```

### 8.4 ask_user Tool 注入

```python
# SuspendableScheduler 在每个 turn 开头注入
ASK_USER_TOOL = {
    "name": "ask_user",
    "description": (
        "Pause the current turn and ask the user for structured input. "
        "Returns a UI card to the user. Use this when you need the user "
        "to make a decision or provide missing information."
    ),
    "input_schema": {
        "type": "object",
        "required": ["card_type"],
        "properties": {
            "card_type": {
                "enum": [c.value for c in CardType],
                "description": "Which kind of UI card to show",
            },
            "card_id": {"type": "string"},
            "title": {"type": "string"},
            "body": {"type": "object"},
            "options": {"type": "array"},
            "decision_buttons": {"type": "array"},
            "actions": {"type": "array"},
        },
    },
}
```

### 8.5 5 个场景的 A2UI 配置矩阵

| 场景 | a2ui.enabled | orchestration | 卡片集 |
|---|---|---|---|
| `_generic` | false | single | – |
| `_default` | false | single | – |
| `flight_booking` | true | hitl | 8 个业务卡 + 1 chat fallback |
| `expense_audit` | false | parallel | – |
| `customer_service` | true | hitl | 2 个: HANDOFF_HUMAN / TICKET_RESULT |
| `code_review` | false | delegate | – |

> `flight_booking` 完整 8 卡；`customer_service` 是轻量级 HITL（2 卡）；其余关闭 A2UI。

---

## 9. 5 个场景的 5 维度对比

| 场景 | security.tool_level | workspace.cwd | a2ui | progressive_skill | orchestration |
|---|---|---|---|---|---|
| `_generic` | **safe** | `${PROJECT_DIR}` (只读) | off | none | single |
| `_default` | safe | `${PROJECT_DIR}` (只读) | off | none | single |
| `flight_booking` | standard | `${PROJECT_DIR}` (读写) | **on, 8 cards** | **on_demand, 4000 tok** | **hitl** |
| `expense_audit` | standard | `${PROJECT_DIR}` (读写) | off | all (6k) | parallel |
| `code_review` | standard | `${PROJECT_DIR}` (读写) | off | all (6k) | delegate |
| `customer_service` | safe | `${PROJECT_DIR}` (读写受限) | on, 2 cards | on_demand (2k) | hitl |

> **用户诉求 1 验证**：6 个场景 × 5 个维度 = 30 个独立配置点，**没有**任何代码改动。

---

## 10. 错误码（用户诉求 9：可行动信息）

| HTTP | code | 含义 | 可行动信息 |
|---|---|---|---|
| 400 | `SCENARIO_NOT_FOUND` | 引用的 scenario 不存在 | "Available: [...]" |
| 400 | `SCENARIO_DISABLED` | scenario 关闭 | "Enable via API: PATCH /agent/scenarios/{name} {enabled: true}" |
| 400 | `SCENARIO_VALIDATION_FAILED` | YAML schema 不通过 | "Field: execution.skills[0]=unknown_skill. Available skills: [...]" |
| 503 | `SCENARIO_RESOURCE_UNAVAILABLE` | 物理资源缺失 | "Missing: /work/scenarios/flight_booking/cards/OD_INPUT.card.yaml. Check resource_dirs.cards" |
| 503 | `SCENARIO_WORKSPACE_FORBIDDEN` | cwd 是危险路径 | "workspace.workspace_dirs[0] = '/' is forbidden. Use ${PROJECT_DIR}." |
| 400 | `SKILL_NOT_ALLOWED` | 客户端传了越权 skill | "Scenario {scenario} skills whitelist: [...]. Got: {client_skills}." |
| 400 | `TOOL_NOT_ALLOWED` | 客户端传了越权 tool | 同上 |
| 400 | `POLICY_VIOLATION` | 路径/命令/网络违规 | "Path '/etc/passwd' not in workspace_dirs. Allowed: [...]" |
| 400 | `SKILL_BUDGET_EXCEEDED` | 渐进式 skill 超出预算 | "Loaded: 4500 tokens > budget 4000. Reduce load_on_state or raise budget." |
| 422 | `YAML_PLACEHOLDER_UNRESOLVED` | 占位符未解析 | "Placeholder ${PROJECT_DIR} not in ctx. Inject from auth middleware." |
| 500 | `LAUNCH_FAILED` | 引擎启动失败 | "opencode serve failed at cwd '{cwd}': {stderr}" |

**所有错误都返回结构化 detail**：

```json
{
  "success": false,
  "code": "SCENARIO_RESOURCE_UNAVAILABLE",
  "message": "Scenario 'flight_booking' has missing resources",
  "detail": {
    "missing": [
      "/work/scenarios/flight_booking/cards/OD_INPUT.card.yaml",
      "/work/scenarios/flight_booking/skills/book-flight/fragments.yaml"
    ],
    "action": "Create the missing files or fix resource_dirs in the scenario YAML"
  }
}
```

---

## 11. 分阶段计划：8 个 Phase，**互不影响**

> **User 诉求**：plan 计划，不能互相影响
>
> **保证**：每个 Phase 独立 shippable，独立 review，独立回滚；上一个 Phase 失败不影响下一个 Phase

| Phase | 范围 | 触动现有文件 | 完成后可独立验证 |
|---|---|---|---|
| **P0** 资源目录骨架 | 建 `/work/{tenants,scenarios,shared,cache,logs,archive}` | ❌ 无 | `ls /work/scenarios/_generic.scenario.yaml` 存在 |
| **P1** L5 Policy Engine | `policy/*.py` | ❌ 无（sandbox 实现层） | `pytest tests/test_policy_*` 全过 |
| **P2** L2 Scenario 基础 | `scenarios/registry.py` `router.py` `config.py` `loader.py` `injector.py` | ❌ 无（routing 实现层） | `pytest tests/test_scenario_*` 全过；YAML 加载 5 个 scenario 成功 |
| **P3** L4 Engine Launcher | `providers/launcher.py` | `providers/agent_bridge.py` +30 行（**加方法，不改签名**） | `pytest tests/test_launcher.py` 全过；`opencode serve` 启动在 `${PROJECT_DIR}` 而不是 `/` |
| **P4** L3 Skill Runtime | `skill_runtime/manifest.py` `state_guard.py` `prompt_builder.py` `fragments.py` | `skills/registry.py` +20 行（**加方法，不改签名**） | `pytest tests/test_skill_runtime.py` 全过；按 state 加载片段成功 |
| **P5** L3 AUIP / Suspendable | `auip/*.py` `core/suspendable_scheduler.py` `core/turn_store.py` | `core/scheduler.py` 保留为 `LegacyScheduler`，**新增** `SuspendableScheduler` | `pytest tests/test_auip_*` 全过；HITL 剧本 A 通过 |
| **P6** L1 路由 + Middleware | `api/scenario_routes.py` `scenarios/middleware.py` `api/app.py` | `api/routes.py` `/agent/chat` 开头 +20 行 scenario 检查 | `curl -X POST /agent/chat {scenario: "flight_booking"}` 命中正确 scenario |
| **P7** 6 个示例 scenario | `_generic` `_default` `flight_booking` `expense_audit` `customer_service` `code_review` | 仅 YAML 文件 | 6 个 scenario 全加载；路由命中 100% |
| **P8** 端到端验证 | `tests/e2e/test_*` | ❌ 无 | 5 个剧本（A-E）跑通；性能基准 6 次挂起 P95 < 5s |

### 11.1 Phase 依赖图

```
P0 (目录)
  │
  ├─► P1 (Policy)
  │     │
  ├─► P2 (Scenario) ◄──── (P0 必须先)
  │     │
  │     ├─► P6 (Middleware) ◄── (需要 P2 + P3)
  │     │
  │     └─► P7 (示例 scenario) ◄── (需要 P0 + P1 + P2)
  │
  ├─► P3 (Launcher) ◄── (需要 P2 的 ScenarioConfig)
  │
  ├─► P4 (Skill Runtime) ◄── (需要 P2)
  │     │
  │     └─► P5 (AUIP/HITL) ◄── (需要 P4)
  │
  └─► P8 (E2E) ◄── (需要 P1+P3+P4+P5+P6+P7)
```

> **关键点**：P0 → P1 / P2 / P3 / P4 是 4 个**完全独立**的分支，**可以并行开发**。P5 依赖 P4，P6 依赖 P2+P3，P7 依赖 P0+P1+P2，P8 必须最后。

### 11.2 每个 Phase 的 DoD (Definition of Done)

| Phase | DoD |
|---|---|
| P0 | `mkdir -p` 脚本提交；README 写清每个目录的用途 |
| P1 | `policy/*.py` 4 个模块；`tests/test_policy_*.py` 全过；`/agent/{name}/policy` 端点返回 effective policy |
| P2 | `scenarios/*.py` 5 个模块；`tests/test_scenario_*.py` 全过；5 个示例 scenario YAML 加载 |
| P3 | `providers/launcher.py`；`tests/test_launcher.py`；`/ready` 校验所有 agent 的 cwd 非根 |
| P4 | `skill_runtime/*.py` 4 个模块；fragment 加载 + budget 强制；`/agent/skills/{name}/fragments` 端点 |
| P5 | `auip/*.py` + `core/suspendable_scheduler.py` + `core/turn_store.py`；HITL 剧本 A 通过；`/agent/turn/*` 5 个端点 |
| P6 | `scenarios/middleware.py` + `api/scenario_routes.py`；`curl` 6 优先级路由全部命中 |
| P7 | 6 个 scenario YAML；`POST /agent/scenarios` 注册；热重载工作 |
| P8 | `tests/e2e/test_*` 5 个剧本；CI 跑通；性能基准达标 |

---

## 12. 关键接口契约

### 12.1 Scenario → SuspendableScheduler

```python
# SchedulerAdapter.execute("hitl", ...) 内部
def _to_suspendable_params(
    scenario: ScenarioConfig,
    injection: InjectionResult,
    user_prompt: str,
) -> dict:
    return {
        "prompt": user_prompt,
        "session_id": ...,                       # 来自 request
        "skill_hint": scenario.name,            # 加载 scenario.execution.skills
        "skill_manifest": load_manifest(scenario.a2ui.state_machine),
        "cards_dir": scenario.a2ui.cards_dir,
        "ask_user_tool_schema": scenario.a2ui.ask_user.schema,
        "security": scenario.security,           # 传给 Provider 启动参数
        "workspace": scenario.workspace,         # 传给 Launcher
        "progressive_skill": scenario.progressive_skill,  # 传给 PromptBuilder
        "system_prompt": injection.final_system_prompt,
        "allowed_skills": injection.final_skills,
        "allowed_tools": injection.final_tools,
    }
```

### 12.2 Scenario → Policy Engine

```python
# bridge.create_session / bridge.chat 入口
def _to_effective_policy(
    scenario: ScenarioConfig,
    request_override: dict | None,
) -> EffectivePolicy:
    return EffectivePolicy(
        tool_level=scenario.security.tool_level,
        workspace_dirs=scenario.workspace.workspace_dirs,
        readonly_dirs=scenario.workspace.readonly_dirs,
        deny_dirs=scenario.workspace.deny_dirs,
        deny_path_patterns=scenario.workspace.deny_path_patterns,
        allowed_tools=scenario.security.allowed_tools,
        denied_tools=scenario.security.denied_tools,
        allowed_commands=scenario.security.allowed_commands,
        denied_commands=scenario.security.denied_commands,
        network=scenario.security.network,
        max_turns=scenario.security.max_turns,
        max_budget_usd=scenario.security.max_budget_usd,
    )
```

### 12.3 Skill Manifest → StateGuard

```python
# SuspendableScheduler 加载 scenario.a2ui.state_machine
def _load_state_machine(path: Path) -> SkillManifest:
    return SkillManifest.from_yaml(path)

# StateGuard 校验 AI 调用的工具
class StateGuard:
    def can_call_tool(self, tool_name: str) -> tuple[bool, str]:
        state = self._manifest.states[self._ctx.current_state]
        if tool_name == "ask_user":
            return True, "ok"
        if tool_name not in state.allowed_tools:
            return False, (
                f"State {self._ctx.current_state} 不允许调 {tool_name}。"
                f"允许的工具: {state.allowed_tools}。"
            )
        return True, "ok"
```

### 12.4 Card YAML → AUIRenderer

```python
# 后端: 把 Card 序列化为 AUIP 事件
def card_to_event(card_yaml_path: Path) -> dict:
    raw = yaml.safe_load(card_yaml_path.read_text())
    return {
        "type": "CUSTOM",
        "name": "card",
        "value": {
            "card_id": raw.get("card_id", str(uuid4())),
            "card_type": raw["card_type"],
            "schema_version": raw["schema_version"],
            "title": raw["title"],
            "body": raw.get("body", {}),
            "options": raw.get("options", []),
            "actions": raw.get("actions", []) or raw.get("decision_buttons", []),
            "metadata": raw.get("metadata", {}),
        },
    }

# 前端: 收到 CUSTOM 事件后按 card_type 路由到组件
```

---

## 13. 验证清单（每个 Phase 结束跑一遍）

```python
# tests/integration/test_integration.py
import pytest
from openagent.scenarios import ScenarioRegistry, ScenarioRouter, ScenarioInjector
from openagent.policy import PolicyEngine
from openagent.skills.runtime import FragmentLoader, StateGuard

def test_5_scenarios_load():
    """6 个 scenario 全部加载成功."""
    reg = ScenarioRegistry()
    reg.load_from_paths("/work/scenarios/")
    assert len(reg.list_enabled()) == 6
    assert "flight_booking" in reg.list_names()
    assert "_generic" in reg.list_names()

def test_generic_scenario_is_minimal():
    """_generic 必须最小化: 0 skill, safe, no a2ui, no progressive."""
    reg = ScenarioRegistry()
    cfg = reg.get("_generic")
    assert cfg.execution.skills == []
    assert cfg.security.tool_level == "safe"
    assert cfg.a2ui.enabled is False
    assert cfg.progressive_skill.strategy == "none"

def test_workspace_dirs_not_root():
    """所有 scenario 的 cwd 都不能是 /."""
    reg = ScenarioRegistry()
    for cfg in reg.list_all():
        first = cfg.workspace.workspace_dirs[0]
        assert first not in ("/", "~", "${HOME}"), f"{cfg.name} cwd is {first}"

def test_hitl_scenarios_have_a2ui():
    """orchestration=hitl 必须 a2ui.enabled=true."""
    reg = ScenarioRegistry()
    for cfg in reg.list_all():
        if cfg.execution.orchestration == "hitl":
            assert cfg.a2ui.enabled, f"{cfg.name} is hitl but a2ui disabled"

def test_skill_budget_enforced():
    """progressive_skill 加载超过 budget 应抛出 (policy=error)."""
    cfg = make_scenario_with_huge_skill()
    loader = FragmentLoader(skill_registry, budget=100, policy="error")
    with pytest.raises(SkillBudgetExceeded):
        loader.load(cfg, current_state="S05")

def test_engine_launcher_refuses_root():
    """Launcher 必须拒绝 cwd=/."""
    from openagent.providers.launcher import EngineLauncher
    cfg = make_scenario_with_cwd("/")
    with pytest.raises(LauncherError):
        EngineLauncher().launch(cfg, agent_config)

def test_policy_blocks_etc_passwd():
    """Policy engine 必须拒绝 /etc/passwd."""
    eff = make_effective_policy(tool_level="standard", workspace_dirs=["/work/x"])
    assert not path_check.is_allowed(eff, "/etc/passwd", "read")
```

### 13.1 端到端剧本

```python
# tests/e2e/test_flight_booking_e2e.py
async def test_playbook_a_happy_path():
    """剧本 A: 订明天北京到上海."""
    # 1. POST /agent/scenarios/flight_booking/chat/stream
    # 2. 接收 SSE: session → text → tool_use(query_flight) → tool_result → card FLIGHT_LIST → suspend
    # 3. POST /agent/turn/<id>/resume {flightId: ...}
    # 4. 接收 SSE: resume → tool_use(choose_cabin) → card CABIN_LIST → suspend
    # 5. POST /agent/turn/<id>/resume {cabId: ...}
    # 6. ... 6 个挂起点 ...
    # 7. 接收 SSE: card ORDER_SUCCESS → done
    pass
```

---

## 14. 风险与未决问题

### 14.1 风险 + 缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| **Scenario YAML 膨胀** | 一个文件 500+ 行 | 允许 `extends: ../_base.scenario.yaml` 复用；YAML anchor `&` |
| **占位符解析失败** | Scenario 加载 503 | 启动时 `POST /agent/scenarios/{name}/validate` 预校验；`/ready` 检查 |
| **多 scenario 引用同一 skill 但版本不同** | 行为漂移 | Skill 注册时记录 `skill@version`，Scenario 引用 `book-flight@0.1.0` |
| **engine cwd 解析后不存在** | 启动失败 | Launcher 加 `create_if_missing: true` 字段（默认 false） |
| **A2UI 卡片 schema 与前端组件漂移** | 前端渲染报错 | 卡片 schema 加 `schema_version`，前端按 version 路由到不同组件 |
| **progressive_skill 片段被改后 tokens 超出预算** | 报错 | CI 跑 `python scripts/estimate_fragment_tokens.py` 校验 |
| **多租户共用同一台机器** | 隔离不足 | workspace 路径强校验 + deny_dirs 默认包含其他 tenant |
| **`tool_level=full` 误用** | 安全风险 | `full` 必须 owner 显式 opt-in + audit 单独打标 |
| **book-flight 的 MCP 未接入** | 剧本 A 跑不通 | 先用 mock MCP server 跑通协议层，等真 MCP 接入后切换 |

### 14.2 未决问题

1. **Scenario 是否支持热删除？** 当前只支持 disabled；删除需 reload
2. **多个 scenario 共享同一 skill 时，prompt 片段缓存如何复用？** 暂按 LRU
3. **A2UI 协议选 AUIP 自研还是直接用 AG-UI？** 倾向 AUIP（领域化），后续可平滑迁移
4. **多租户的 tenant_id 注入时机？** 推荐 auth middleware 在 ScenarioMiddleware 之前
5. **book-flight 的 state-machine.yaml 是手写还是从 .md 自动编译？** 推荐 .md 是源，CI 编译成 .yaml
6. **场景 A/B 灰度的 metadata 怎么用？** 暂用 `metadata.ab_group`，未来扩 `metadata.tenant_id`
7. **失败重启后 Turn 如何恢复？** 已有方案 §8.2 crash recovery；本方案沿用

### 14.3 显式不做的事

> 这些是**故意不做**，避免方案膨胀：

- ❌ Docker 容器隔离（user 诉求：暂不用）
- ❌ 全文搜索引擎（policy 文档用纯文件即可）
- ❌ 实时 dashboard（Phase 8 之后考虑）
- ❌ 多语言 Skill（book-flight 是中文，其他场景再决定）
- ❌ Scenario 之间的状态共享（每个 Turn 独立 ctx）
- ❌ LLM 自动生成 Scenario YAML（手工 + LLM 辅助）
- ❌ 多 turn 之间的 ctx 合并（保留简单会话模型）
- ❌ Skill 运行时热更新（v1 重启加载）

---

## 15. 落地动作清单（Do this week）

> **用户原始问题**："要有 plan 计划"

如果只能**这周**做以下 3 件事，**最高 ROI**：

### Day 1-2: Phase 0 + Phase 1
```bash
# 1. 资源目录骨架
mkdir -p /work/{tenants/tenant-A/projects,scenarios/flight_booking/{prompts,skills,mcp,tools,cards,tests},scenarios/_generic/{prompts,skills,mcp,tools,cards},shared/{skills,mcp,prompts,docs},cache,logs,archive}
git add -A && git commit -m "feat: P0 资源目录骨架"

# 2. 写 _generic.scenario.yaml 和 _default.scenario.yaml
cp docs/design/integrated-orchestration-plan.md §6.2 内容到 /work/scenarios/_generic.scenario.yaml
git add -A && git commit -m "feat: P7 _generic + _default 兜底 scenario"
```

### Day 3-4: Phase 2 最小骨架
```python
# src/openagent/scenarios/__init__.py
# src/openagent/scenarios/config.py   (~150 行, Pydantic 校验)
# src/openagent/scenarios/registry.py  (~100 行, YAML 加载)
# src/openagent/scenarios/router.py    (~150 行, 6 优先级)
# src/openagent/scenarios/loader.py    (~100 行, 占位符解析)
# tests/test_scenario_*.py              (~200 行)
```

### Day 5: Phase 8 验收
```bash
# 跑通最简 E2E
curl -X POST localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你好", "scenario": "_generic"}'
# 期望: 命中 _generic, 极简回复, 0 skill, 0 tool, no a2ui
```

---

## 16. 总结

> **本文不是第 5 份方案，是把前 4 份拼起来的胶水 + 配置规范。**

```
┌─────────────────────────────────────────────────────────┐
│  4 份方案 (零修改)                                         │
│  ┌──────────────┐ ┌────────────┐ ┌──────────┐ ┌──────┐ │
│  │ sandbox      │ │ routing    │ │ hitl     │ │skill │ │
│  │ (安全库)     │ │ (路由库)   │ │(协议库)  │ │ (业务)│ │
│  └──────┬───────┘ └─────┬──────┘ └────┬─────┘ └──┬───┘ │
│         └─────────────────┴────────────┴──────────┘     │
│                          │                              │
│                   ┌──────┴──────┐                       │
│                   │  Scenario   │  ← 本文核心            │
│                   │  (配置包)    │                       │
│                   └──────┬──────┘                       │
│                          │                              │
│              ┌───────────┼────────────┐                 │
│              ▼           ▼            ▼                 │
│         资源目录     渐进式 SKILL    A2UI 接入           │
│         (user 4)    (user 5)        (user 1)            │
│         + _generic  + budget 强制   + Suspendable       │
│         (user 2)      (质量约束)      (P0 不互相影响)    │
│         + 启动 cwd                     ↑                │
│         (user 3)                       │                │
│                                        │                │
│         8 个独立 Phase, 任何失败回滚不影响其他            │
└─────────────────────────────────────────────────────────┘
```

**5 项用户诉求的落地点**：

| 诉求 | 落地点 |
|---|---|
| 1. 场景化路由 + 安全 + 工作区 + A2UI | `Scenario` 配置 + `scenarios/` 包 + `a2ui` 块 |
| 2. 通用场景 | `_generic.scenario.yaml`（safe + off + 0 skill）|
| 3. 引擎启动在项目目录 | `workspace.workspace_dirs[0] = ${PROJECT_DIR}` + `Launcher.cwd` 校验 |
| 4. 资源统一管理 | `/work/{tenants,scenarios,shared,cache,logs}` 布局 + `resource_dirs` 块 |
| 5. 渐进式 SKILL | `progressive_skill` 块 + 4 策略 + `fragments/` 目录 + budget 强制 |

**核心质量约束**（让模型不自由发挥）：

- 5 层代码分层，**依赖严格向下**，CI 强校验
- 每层文件 ≤ 200/250 行，函数 ≤ 40 行，圈复杂度 ≤ 10
- Scenario YAML Pydantic 校验，**所有错误带可行动信息**
- 8 个 Phase 独立 shippable，互不卡死
- 4 份既有方案**零修改**，所有功能通过**新文件 + DI** 接入

**下一步**（按 P0 → P1 → P2 → ... 顺序）：

1. 建 `/work/` 目录
2. 写 `_generic` + `_default` 两个 YAML
3. 实现 Pydantic config + registry + router（无 provider 改动）
4. 跑通"任意 chat 都能命中 _generic" 验证
5. 评审通过后按 Phase 推进
