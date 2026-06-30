# hermetic-agent 开源演进与重构执行计划

> 项目唯一官方名称：`hermetic-agent`
> 现状基准：基于代码库探索 v2024-06-24

---

## 0. 现状定标

### 0.1 架构现状（5层）

```
L1 api/              ← HTTP入口, chat_controller (统一 /chat + /chat/stream)
L2 scenarios/        ← 6级路由, scenario注入了业务系统提示词
L3 skill_runtime/ + auip/ + core/
   ├─ skill_runtime/ ← 通用 SkillRegistry + 渐进加载 + prompt组装 [健康]
   ├─ auip/          ← [严重耦合] 机票-specific: flight_card/intl_flight_card/passenger_form
   └─ core/          ← suspendable_scheduler (HITL) + turn_store [健康]
L4 providers/        ← opencode_adapter + chat.py [部分耦合: feihe-travel工具名硬编码]
L5 policy/ + store/ + config/
   ├─ policy/        ← 安全策略引擎 [健康]
   ├─ store/         ← 持久化 [健康]
   └─ config/settings.py ← [部分耦合: Feihe auth配置节]
```

### 0.2 关键耦合清单

| 位置 | 类型 | 具体表现 |
|------|------|---------|
| `auip/flight_card.py` | 业务逻辑 | `QUERY_FLIGHT_BASIC_TOOL_NAMES`、舱位优先级、航空器大小逻辑 |
| `auip/intl_flight_card.py` | 业务逻辑 | `AIRCRAFT_MAP`、`CAB_LABELS`、国际机票数据转换 |
| `auip/passenger_form_card.py` | 业务逻辑 | 乘机人表单卡片组装 |
| `api/http/streaming/card_message_rewriter.py` | 业务逻辑 | 机票/舱位选择的格式化rewrite |
| `providers/opencode/chat.py` | 业务耦合 | `_FEIHE_TRAVEL_TOOLS` 集合(21个工具)、`_MCP_TOOL_NAMES` 字典 |
| `config/settings.py` §13 | 租户配置 | `feihe_base_url`、`request_timeout` 等飞鹤特定auth |
| `work/scenarios/*.yaml` | 业务场景 | `fh_domestic_flight_booking.scenario.yaml` 等机票场景 |

### 0.3 干净资产（可直接保留）

- `skills/registry.py`、`frontmatter.py`、`runtime/manifest.py`、`runtime/fragments.py` — 通用SKILL基础设施
- `core/scheduler.py`、`suspendable_scheduler.py`、`turn_store.py` — 通用调度/HITL
- `policy/` 全部 — 安全策略引擎
- `store/` 全部 — 持久化层
- `providers/base.py`、`agent_bridge.py`、`launcher.py` — 通用Provider抽象

---

## 第一阶段：业务剥离与代码重构（Decoupling & Refactoring）

**目标**：将 `hermetic-agent` 从"机票预订系统"还原为"通用Agent调度基座"

### 里程碑 1.1：建立核心基座与业务SKILL的边界协议

**核心任务**：定义"什么是基座"与"什么是业务SKILL"的明确边界，并以此边界为准则进行代码拆分。

**边界定义文档**：`docs/architecture-and-flow.md` 新增 §8 "Core vs Skill Boundary Contract"

```
基座职责（hermetic-agent 无任何业务属性）：
├── L1: HTTP协议处理、SSE流化、错误码返回
├── L2: Scenario路由（URL hint / Header / Body / LLM意图 / 兜底）
├── L3: SKILL注册/发现/渐进加载、AUIP卡片协议（仅通用结构，无业务渲染）
│   ├── SKILL框架：SkillRegistry / FragmentLoader / Manifest状态机 / PromptBuilder
│   └── AUIP框架：TurnEvent / CardType枚举 / 通用Card结构（不含业务渲染逻辑）
├── L4: opencode SDK适配（通用）、Provider抽象、Session生命周期
├── L5: Policy引擎、持久化、配置管理（无业务字段）
└── 通用工具：placeholder解析(${PROJECT_DIR}等)、MCP工具桥接框架

业务SKILL职责（全部外部化）：
├── 垂直场景定义：scenario YAML（含业务系统提示词、业务工具列表）
├── 技能实现：具体业务的SKILL.md（含业务prompt模板、业务工具调用）
├── 卡片渲染：业务特定的数据转换（JSON → 业务UI卡片）
│   └── 约定：每个业务SKILL提供自己的 card_renderer.py，遵循通用CardType协议
├── 消息改写：业务特定的user input格式化
└── 外部集成：第三方API Key管理、业务特有配置节
```

**验收标准**：后续所有代码修改不得违反此边界，CI层 `scripts/ci_check.py` 扩展边界检查规则。

---

### 里程碑 1.2：抽取 AUIP 层业务逻辑

**策略**：将 `auip/` 目录下的机票渲染逻辑整体迁移至 `work/shared/skills/fh-domestic-flight-booking/` 作为示例业务SKILL，基座仅保留通用AUIP协议。

#### 步骤 1.2.1：解耦 `auip/flight_card.py`

1. **识别通用部分**：
   - `CardType` 枚举 → 迁移至 `auip/cards.py`（已存在，保留）
   - `TurnEvent` / `AUIPError` → 迁移至 `auip/events.py`（已存在，保留）
   - `maybe_assemble_*` 模式 → 抽象为通用 `CardRenderer` 接口

2. **创建通用渲染接口**：
   ```python
   # auip/renderer.py （新建）
   class CardRenderer(Protocol):
       def can_render(self, event: TurnEvent, context: dict) -> bool: ...
       def render(self, event: TurnEvent, context: dict) -> Card: ...

   # 每个业务SKILL实现自己的 renderer
   # 基座通过 SkillRegistry.get_card_renderer(skill_name) 动态发现
   ```

3. **抽取至业务SKILL**：
   - `work/shared/skills/fh-domestic-flight-booking/card_renderer.py`（新建）：实现 `DomesticFlightCardRenderer`
   - 依赖 `auip/` 中的 `CardType` / `Card` / `TurnEvent` 通用结构
   - `auip/flight_card.py` 删除

#### 步骤 1.2.2：解耦 `auip/intl_flight_card.py`

同上，迁移至 `work/shared/skills/fh-international-flight-booking/card_renderer.py`

#### 步骤 1.2.3：解耦 `auip/passenger_form_card.py`

迁移至 `work/shared/skills/fh-domestic-flight-booking/passenger_form_renderer.py`

#### 步骤 1.2.4：解耦 `card_message_rewriter.py`

- 迁移至 `work/shared/skills/fh-domestic-flight-booking/message_rewriter.py`
- 基座 `auip/` 最终仅保留：
  ```
  auip/
  ├── cards.py      # Card / CardType 通用结构
  ├── events.py    # TurnEvent / AUIPError 通用事件
  ├── renderer.py  # CardRenderer 接口协议
  └── errors.py    # 通用错误（已存在）
  ```

**验收标准**：`auip/` 目录下无任何 `flight`、`booking`、`passenger`、`cabin` 等业务关键词；基座代码可独立编译运行，无机票业务导入。

---

### 里程碑 1.3：清理 Provider 层业务耦合

**目标**：`providers/opencode/chat.py` 去除所有 `feihe-travel` 硬编码

#### 步骤 1.3.1：工具名发现机制从硬编码改为配置驱动

**现状**：
```python
# providers/opencode/chat.py
_FEIHE_TRAVEL_TOOLS = {"feihe-travel_queryFlightBasic", ...}
_MCP_TOOL_NAMES = {"feihe-travel": [...], "mcporter": [...]}
```

**重构为**：
```yaml
# work/shared/skills/fh-domestic-flight-booking/skill.yaml
mcp_tools:
  feihe-travel:
    tools: [queryFlightBasic, ...]
  mcporter:
    tools: [...]
```

**代码改造**：
```python
# providers/opencode/chat.py
# 新增：动态从已激活scenario的SKILL manifest获取工具列表
def _resolve_tool_names(scenario_name: str, skill_manifests: list[SkillManifest]) -> set[str]:
    tool_names = set()
    for manifest in skill_manifests:
        for mcp_server, config in manifest.mcp_tools.items():
            tool_names.update(config.get("tools", []))
    return tool_names
```

#### 步骤 1.3.2：Token推送抽象化

**现状**：
```python
# _push_flight_token_to_opencode() — hardcoded FLIGHT_API_KEY
```

**重构为**：
```python
# providers/opencode/chat.py
async def _push_skill_tokens_to_opencode(skill_manifests: list[SkillManifest], container_admin_url: str):
    for manifest in skill_manifests:
        for env_name, env_value in manifest.required_envs.items():
            await _push_env_to_container(container_admin_url, env_name, env_value)
```

每个业务SKILL在 `SKILL.md` frontmatter 中声明：
```yaml
required_envs:
  FLIGHT_API_KEY: "${FLIGHT_API_KEY}"
```

**验收标准**：`providers/opencode/chat.py` 中无任何 `feihe`、`flight`、`FH_` 前缀变量；`_FEIHE_TRAVEL_TOOLS` 集合删除。

---

### 里程碑 1.4：清理 Config 层租户耦合

**目标**：`config/settings.py` 删除 Feihe-specific 配置节

#### 步骤 1.4.1：识别迁移对象

| 配置字段 | 迁移目标 |
|---------|---------|
| `feihe_base_url` | 移至 `work/scenarios/fh_domestic_flight_booking.scenario.yaml` 的 `env` 字段 |
| `feihe_request_timeout` | 同上 |
| `flight_mcp_token_env` | 移至 `work/shared/skills/fh-domestic-flight-booking/skill.yaml` 的 `required_envs` |

#### 步骤 1.4.2：配置架构改造

```python
# config/settings.py 重构后结构
class Settings(BaseSettings):
    # L1-L4 通用配置（保留）
    server: ServerSettings
    opencode: OpenCodeSettings
    storage: StorageSettings
    skill_runtime: SkillRuntimeSettings
    mcp: MCPSettings  # 通用MCP框架配置，不含业务token
    agent: AgentSettings
    sandbox: SandboxSettings
    policy: PolicySettings
    scenario: ScenarioSettings
    launcher: LauncherSettings
    chat_sse: ChatSSESettings

    # 删除：feihe_auth: FeiheAuthSettings  # 业务特定，整节删除
    # 删除：flight_mcp_token_env  # 业务特定，下沉至SKILL层
```

#### 步骤 1.4.3：Token外部化

业务API Key不再写入 `config/settings.py`，改为：
1. 运行时通过 `work/scenarios/*.scenario.yaml` 的 `env` 字段注入
2. 或通过 `POST /agent/admin/opencode/{node}/env` 动态推送（已有机制）
3. 文档明确要求：**所有业务Secret不得进入代码仓库**

**验收标准**：`config/settings.py` 中无任何 `feihe`、`flight` 关键词；Settings 类所有字段均为通用技术配置。

---

### 里程碑 1.5：Scenario YAML 业务边界隔离

**目标**：确保 `work/scenarios/` 下的 YAML 文件是"业务场景定义"而非"基座代码"

#### 步骤 1.5.1：目录重组

```
work/
├── scenarios/           # 场景定义（业务）
│   ├── fh_domestic_flight_booking.scenario.yaml
│   └── fh_international_flight_booking.scenario.yaml
├── shared/skills/      # 技能定义（业务）
│   └── fh-domestic-flight-booking/
│       ├── SKILL.md
│       ├── card_renderer.py
│       └── skill.yaml
└── tenants/             # 多租户隔离（可选）
    └── feihe/
        └── config.yaml  # 租户级业务配置
```

#### 步骤 1.5.2：场景文件净化

每个 `.scenario.yaml` 文件只包含：
- `name`、`description`、`version`
- `skills[]` — 引用的SKILL列表
- `system_prompt` — 业务系统提示词（机票预订领域）
- `tools` — 业务工具声明（而非基座工具）
- `env` — 业务环境变量（如 `FLIGHT_API_KEY`）

**删除**：任何与"基座调度"相关的配置（这类配置只能出现在 `config/settings.py` 或环境变量中）

**验收标准**：`scripts/ci_check.py` 扩展检查：scenario YAML 中不得出现 `scheduler`、`provider`、`agent_bridge` 等基座层命名。

---

### 里程碑 1.6：第一阶段收尾质量门禁

```bash
# 必须全部通过
python scripts/ci_check.py                          # 5层边界 + 文件大小
python scripts/check_unified_chat_entry.py          # 统一入口约束
ruff check src/hermetic_agent/ --select=[F401]            # 无未使用import（含业务关键词的import应已清除）
grep -r "feihe\|flight\|cabin\|passenger" src/hermetic_agent/  # 应返回空（AUIP目录已迁移）
pytest tests/ -v --tb=short                          # 全量测试通过
```

**阶段一产物**：
- `docs/core-skill-boundary.md` — 边界定义文档
- `work/shared/skills/fh-domestic-flight-booking/` — 示例业务SKILL（含card_renderer）
- 重构后的 `auip/` 目录（仅通用结构）
- 净化后的 `config/settings.py`
- `work/scenarios/` 目录重组

---

## 第二阶段：核心架构整合（Core Integration）

**目标**：以开源 `opencode` 为唯一底层引擎，完成 hermetic-agent 作为通用Agent调度层的深度整合。

### 里程碑 2.1：opencode SDK 深度集成

#### 步骤 2.1.1：SDK 升级路径分析

```
当前：providers/opencode/ 使用 opencode-sdk-python（本地适配层）
目标：直接基于 opencode 官方 Python SDK 调用，移除自定义适配层
```

**分析 `relate_project/opencode-sdk-python/`**：
- 确认 SDK 版本、API surface
- 确认 `AsyncOpencode` 客户端的 `session.chat()` / `event.list()` 接口与当前 `chat.py` 用法是否匹配
- 确认认证机制（API Key / Token）和当前 token push 机制的关系

#### 步骤 2.1.2：Adapter 层精简

当前 `providers/opencode/adapter.py` 是"薄壳"，但 `chat.py` 有1300+行含业务逻辑。重构后：

```python
# providers/opencode/chat.py 重构目标（≤400行）
# 职责：纯协议转换（hermetic StreamEvent ↔ opencode SDK event）
# 无任何业务逻辑

async def stream_chat(...):
    client = get_client(base_url)
    async with client.event.list(session_id=session_id) as events:
        async for sdk_event in events:
            hermetic_event = map_opencode_event(sdk_event)  # 纯映射
            yield hermetic_event

def blocking_chat(...):
    # 同步调用 client.session.chat()
    # 映射返回值
    return ChatResult(...)
```

#### 步骤 2.1.3：多SDK路由扩展

当前 `agent_bridge.py` 已支持 `opencode` / `claude_code` 双SDK。验证：
- `claude_code` adapter 是否完整
- 未来可扩展 `anthropic` / `openai` 等provider

**验收标准**：所有 provider 目录下无非业务逻辑代码；所有 provider 均可独立测试（mock SDK）。

---

### 里程碑 2.2：调度器与状态机改造

#### 步骤 2.2.1：Scheduler 通用化

当前 `core/scheduler.py` 的 `single_run` / `parallel_run` / `chain_run` / `in_session_run` 是通用抽象，确认：
- 无任何业务状态假设
- 所有 run 类型均可跨 scenario 复用

#### 步骤 2.2.2：HITL 状态机标准化

`core/suspendable_scheduler.py` 的 checkpoint/resume 机制：
- 当前与 `turn_store.py` 紧耦合
- 验证 checkpoint 数据结构是否通用（不含业务字段）
- 确认 suspend/resume 协议是否可序列化（用于分布式场景）

```python
# 期望的 HITL 协议
@dataclass
class HITLCheckpoint:
    session_id: str
    turn_index: int
    skill_state: dict  # SKILL自定义状态，基座不解释
    auip_context: dict # AUIP通用上下文，基座不解释业务含义
    # ...基座透明传序，不关心内容
```

#### 步骤 2.2.3：编排引擎扩展性

`scenarios/` 层的编排能力：
- 当前 6 级路由优先级 → 保留
- 验证 scenario 注入（`injector.py`）是否支持纯业务定制，不触及基座

**验收标准**：`core/scheduler.py` / `suspendable_scheduler.py` 行数 ≤ 250（5层约束）；无业务关键词。

---

### 里程碑 2.3：状态管理与持久化抽象

#### 步骤 2.3.1：TurnStore 泛化

`core/turn_store.py` 当前存储 HITL checkpoint：
- 验证 schema 是否通用（不含业务字段）
- 如果通用：保留为 `TurnStore` 接口
- 如果含业务字段：抽象为 `TurnStore`（接口）+ `HITLTurnStoreImpl`（实现），业务字段下沉至 SKILL 层序列化

#### 步骤 2.3.2：Session 持久化

`store/` 层（MySQL/PostgreSQL/Memory）：
- 验证 SQLAlchemy 模型是否含业务字段（如 `flight_booking_id`）
- 业务字段全部迁移至 SKILL 层，Session store 只保留通用对话状态

**验收标准**：`store/models/` 中无任何业务相关表或字段。

---

### 里程碑 2.4：第二阶段收尾质量门禁

```bash
pytest tests/test_suspendable_scheduler*.py -v     # HITL核心功能回归
pytest tests/test_providers*.py -v                  # Provider层测试
ruff check src/hermetic_agent/providers/ --select=F401  # 无未用import
mypy src/hermetic_agent/core/scheduler.py src/hermetic_agent/core/suspendable_scheduler.py --strict
```

**阶段二产物**：
- 精简后的 `providers/opencode/chat.py`（≤400行）
- 泛化的 `TurnStore` 接口与实现
- `core/` 目录完全通用化

---

## 第三阶段：开发者体验与 SKILL 体系构建（Developer Experience）

**目标**：建立完整的 SKILL 开发规范，使第三方开发者能通过编写 SKILL 实现任意业务Agent。

### 里程碑 3.1：SKILL 开发规范与脚手架

#### 步骤 3.1.1：发布 `hermetic-skill-cli` 脚手架工具

```bash
# 期望的用户流程
npm create hermetic-skill@latest my-agent-skill
cd my-agent-skill
# 编辑 SKILL.md 和 skill.yaml
hermetic-skill test --local    # 本地单元测试
hermetic-skill build           # 打包
hermetic-skill publish         # 发布到 SKILL market（可选）
```

**脚手架模板结构**：
```
my-agent-skill/
├── SKILL.md              # Skill定义（frontmatter + prompt模板）
├── skill.yaml            # Skill配置（tools, env, card_types）
├── card_renderer.py      # 业务卡片渲染（可选）
├── message_rewriter.py   # 业务消息改写（可选）
├── tests/
│   └── test_skill.py     # Skill单元测试
└── README.md
```

#### 步骤 3.1.2：发布标准 SKILL 模板文档

`docs/skills/skills-authoring-guide.md`（替换现有 `docs/skills-development-guide.md`）：

**必须章节**：
1. SKILL.md Frontmatter Schema（所有字段类型与约束）
2. skill.yaml Schema（MCP工具声明、环境变量、卡类型注册）
3. CardRenderer 协议（如何为业务实现自定义卡片）
4. MessageRewriter 协议（如何改写用户输入）
5. 渐进加载策略（none/all/on_demand/explicit + token budget）
6. 状态机设计（SkillManifest states + transitions）
7. 测试规范（mock opencode SDK、集成测试）

#### 步骤 3.1.3：建立 SKILL 兼容性契约

```yaml
# hermetic-agent SKILL 兼容性版本
compatibility:
  hermetic_agent: ">=1.0.0 <2.0.0"
  opencode_sdk: ">=0.8.0"
```

**验收标准**：有一个完整的示例 SKILL（`fh-domestic-flight-booking` 重构后）展示所有协议；脚手架 CLI 可运行。

---

### 里程碑 3.2：SKILL 注册与发现机制

#### 步骤 3.2.1：SKILL Market 架构（可选，后期开源）

```
hermetic-agent SKILL Registry（开源 + 自托管）
├── 官方收录 SKILL（hermetic-agent 维护）
├── 社区贡献 SKILL（第三方开发者发布）
└── 企业私有 SKILL（内网部署）
```

#### 步骤 3.2.2：动态 SKILL 加载 API

当前 `SkillRegistry.load_from_paths()` 仅支持文件系统加载。扩展：

```python
class SkillRegistry:
    async def load_from_url(self, url: str, auth: str | None = None) -> Skill: ...
    async def load_from_marketplace(self, skill_id: str, version: str | None = None) -> Skill: ...
```

**验收标准**：支持 `work/shared/skills/` 目录加载；扩展接口存在但可选（不阻塞基座）。

---

### 里程碑 3.3：文档与快速开始

#### 步骤 3.3.1：`docs/quickstart.md`

**目标**：5分钟让开发者跑通第一个 hermetic-agent + 自定义 SKILL

```
1. 安装 hermetic-agent（pip install / docker run）
2. 配置 opencode 连接
3. 编写第一个 SKILL.md
4. 编写第一个 scenario.yaml
5. 启动 + POST /agent/chat
```

#### 步骤 3.3.2：`docs/architecture.md`

5层架构图（更新版，无业务内容）+ 每层职责描述 + 扩展点说明

#### 步骤 3.3.3：`docs/opencode-integration.md`

opencode SDK 集成指南：
- SDK 安装
- Provider 选择
- 事件映射表（opencode event → hermetic StreamEvent）
- 自定义 Provider 写法

**验收标准**：新开发者参照文档可在 30 分钟内完成第一个自定义 SKILL 运行。

---

### 里程碑 3.4：第三阶段收尾质量门禁

```bash
# SKILL 协议验证
hermetic-skill validate work/shared/skills/fh-domestic-flight-booking/
# 应输出：SKILL.md ✓ | skill.yaml ✓ | card_renderer.py ✓

# 文档完整性检查
ls docs/skills/  # 应包含所有 7 个章节
python scripts/ci_check.py --skill-docs
```

**阶段三产物**：
- `hermetic-skill-cli` 脚手架工具（或等效 npm 包）
- `docs/skills/skills-authoring-guide.md`
- `docs/quickstart.md` + `docs/architecture.md` + `docs/opencode-integration.md`
- 重构后的示例 SKILL（`fh-domestic-flight-booking` 完整实现）

---

## 第四阶段：开源准备与发布（Open Source Readiness）

**目标**：以开源协议发布 hermetic-agent，建立社区运营基础设施。

### 里程碑 4.1：开源协议与法律准备

#### 步骤 4.1.1：选择开源协议

**推荐：Apache 2.0 + 许可证头**

| 考量 | 选择 |
|------|------|
| 商业友好度 | Apache 2.0（允许闭源使用） |
| 专利保护 | 含专利授权条款 |
| Hermetic 品牌保护 | 可叠加 `hermetic-agent` 商标条款 |
| 争议避免 | 无 copyleft 强制要求 |

#### 步骤 4.1.2：许可证头批量添加

```bash
# 在所有 .py 文件头部添加
# Copyright 2024 hermetic-agent Authors
# Licensed under the Apache License, Version 2.0
```

#### 步骤 4.1.3：依赖许可证审计

- 扫描 `requirements.txt` / `pyproject.toml` 中所有依赖的许可证
- 确认无 GPL 强制传染依赖（尤其是 AGPL 的 opencode 本身是否允许 Apache 2.0 下游）
- 生成 `NOTICE` 文件（第三方依赖声明）

**验收标准**：`LICENSE` 文件存在于根目录；`NOTICE` 文件列出所有第三方依赖；无法律风险依赖。

---

### 里程碑 4.2：CI/CD 管道构建

#### 步骤 4.2.1：GitHub Actions 工作流

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/uv-action@v1
      - run: ruff check src/
      - run: mypy src/ --strict
      - run: python scripts/ci_check.py

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/uv-action@v1
      - run: pytest tests/ -v --tb=short

  skill-validation:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python scripts/validate_skills.py work/shared/skills/
```

```yaml
# .github/workflows/release.yml
name: Release
on:
  push:
    tags: ['v*']
jobs:
  docker:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: azure/login@v1
        with: creds: ${{ secrets.AZURE_CREDENTIALS }}
      - run: |
          docker build -t ghcr.io/hermetic-agent/hermetic-agent:${{ github.ref_name }} .
          docker push ghcr.io/hermetic-agent/hermetic-agent:${{ github.ref_name }}
```

#### 步骤 4.2.2：Docker 构建优化

参考 `docs/BUILD.md`，确保：
- `requirements.txt` 与 `pyproject.toml` 同步
- BuildKit cache 优化（避免 cache miss 导致 rebuild）
- 多架构构建（amd64/arm64）

**验收标准**：PR 自动跑 CI；release tag 自动构建 + 推送镜像至 ghcr.io。

---

### 里程碑 4.3：核心文档库建设

#### 步骤 4.3.1：`README.md`（根目录）

```
# hermetic-agent

A general-purpose Agent scheduling framework built on opencode SDK.

[Architecture diagram]
[Quick badges: CI, License, Python version]

## Features
- 5-layer architecture (API / Scenario / SKILL Runtime / Provider / Policy)
- Unified chat entry point (sync + SSE streaming)
- Generic SKILL system with progressive loading
- opencode SDK as the core execution engine
- HITL (Human-in-the-Loop) support

## Quick Start
[5-step quick start]

## Documentation
[Links to docs/]

## License
Apache 2.0
```

#### 步骤 4.3.2：`CONTRIBUTING.md`

- 开发环境搭建（uv venv + pre-commit）
- 代码风格（ruff + mypy）
- PR 流程（fork + PR + CI 必须通过）
- SKILL 贡献规范

#### 步骤 4.3.3：`CHANGELOG.md` 规范

基于 [Keep a Changelog](https://keepachangelog.com/)：
```yaml
## [1.0.0] - YYYY-MM-DD
### Added
- Initial open source release
- 5-layer architecture
- opencode SDK integration
- SKILL system with progressive loading
### Removed
- Feihe-specific business logic (migrated to SKILL layer)
```

#### 步骤 4.3.4：API 文档（OpenAPI）

更新 `docs/api/openapi.json`：
- 所有 endpoint 的 request/response schema
- 错误码 12 个完整描述
- 认证机制说明

**验收标准**：`README.md` 在本地 clone 后 5 分钟内可跑通 quick start；`CONTRIBUTING.md` 覆盖完整开发流。

---

### 里程碑 4.4：社区运营基础设施

#### 步骤 4.4.1：GitHub 仓库设置

- 启用 GitHub Discussions（Q&A / Ideas / General）
- 配置 CODEOWNERS（核心维护团队审查）
- 设置分支保护规则（`main` require PR + 2 reviewer）
- 添加 `good first issue` / `help wanted` 标签

#### 步骤 4.4.2：发布计划

| 时间 | 里程碑 |
|------|--------|
| Week 1-2 | Phase 1 完成，branch `refactor/decoupling` → PR |
| Week 3-4 | Phase 2 完成，branch `refactor/core-integration` → PR |
| Month 2 | Phase 3 完成，branch `feature/skill-system` → PR |
| Month 3 | Phase 4 + 开源发布（v1.0.0） |

**v1.0.0 发布检查清单**：
- [ ] 所有 CI 绿灯
- [ ] `hermetic-agent` PyPI 发布
- [ ] Docker 镜像发布至 ghcr.io + Docker Hub
- [ ] npm 包 `@hermetic-agent/skill-cli` 发布
- [ ] GitHub Releases 页面创建
- [ ] README 链接有效
- [ ] 外部媒体报道/announcement

**验收标准**：第一个开源 release 可通过 `pip install hermetic-agent` 安装并运行。

---

## 总体里程碑时间线

```
Month 1: 第一阶段（业务剥离）
├── Week 1: 边界定义 + AUIP解耦
├── Week 2: Provider层净化 + Config清理
├── Week 3: Scenario YAML重组 + CI门禁
└── Week 4: 第一阶段收尾 + code review

Month 2: 第二阶段（核心架构整合）
├── Week 1: opencode SDK深度集成
├── Week 2: 调度器通用化 + HITL标准化
├── Week 3: 持久化抽象 + 状态管理
└── Week 4: 第二阶段收尾 + code review

Month 3: 第三阶段（开发者体验）
├── Week 1: SKILL脚手架CLI
├── Week 2: SKILL开发规范文档
├── Week 3: 快速开始 + 架构文档
└── Week 4: 示例SKILL完善 + 第三阶段收尾

Month 4: 第四阶段（开源发布）
├── Week 1: 许可证 + 法律审查 + 依赖审计
├── Week 2: CI/CD管道 + Docker构建
├── Week 3: README/CONTRIBUTING/CHANGELOG + API文档
└── Week 4: GitHub仓库设置 + v1.0.0 发布
```

---

## 附录：关键风险与缓解

| 风险 | 级别 | 缓解策略 |
|------|------|---------|
| AUIP 业务逻辑抽取后发现需要基座级别的泛化重构 | 高 | Phase 1 先做 POC，只迁移一个 SKILL，验证接口稳定性后再批量迁移 |
| opencode SDK 新版本 breaking change | 中 | 锁定主版本；SDK 升级需额外测试门禁 |
| 社区 SKILL 质量不可控 | 低 | 提供 SKILL 认证徽章机制；文档明确 SKILL "as-is" 原则 |
| Feihe 特定配置遗漏清理 | 高 | Phase 1 结尾专项 grep 扫描；无业务关键词残留才可合并 |
