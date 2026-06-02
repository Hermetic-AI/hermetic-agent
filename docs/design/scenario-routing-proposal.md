# 场景化 Agent 路由方案（Scenario-Based Agent Routing）

> **文档版本**：v0.1（设计稿）
> **编制日期**：2026-06-02
> **作者**：Sisyphus（OpenAgent 维护）
> **目标读者**：OpenAgent 架构组 / 业务接入方
> **关联文档**：
> - `docs/agent-scheduler-proposal.md` — 总方案
> - `docs/design/book-flight-hitl-design.md` — HITL 挂起/恢复协议（Phase 5 对接）
> - `CLAUDE.md` — 项目工程规范

---

## 0. 摘要

**问题**：当前 `/agent/chat` 接口的请求体里，`system_prompt` / `skills` / `tools` / `agent_name` 全是"扁平字段"——每次调用都要客户端把整套执行策略塞进来。`Scheduler` 的 `run / run_parallel / run_chain` 三种模式也是调用方临时选。后果：

- **调用方心智负担重**：要懂系统提示词怎么写、Skill 名是什么、Tool 名是什么、什么场景该用哪种调度
- **执行策略散落各处**：同样的"订机票"业务，3 个客户端可能传 3 套不同的 system_prompt，结果行为不一致
- **场景知识无法沉淀**：业务专家懂"订票要这么走流程"，但这套知识没地方写，只能由开发者在客户端硬编码
- **无法做 A/B 灰度**：想给"差旅新用户"换一套更简洁的 system_prompt，没有配置入口
- **路由决策不可观测**：不知道一个 chat 走的是哪个执行栈

**方案**：在现有 `SkillRegistry` / `MCPRegistry` / `AgentBridge` / `Scheduler` 之上，新增一个 **Scenario** 抽象层。一个 **Scenario** 是一次完整执行策略的"打包"：

```yaml
name: flight_booking
system_prompt: "你是飞鹤差旅订票助手..."
skills: [book-flight, policy-check]
tools: [query_flight, choose_cabin, submit_order]
orchestration: chain          # single | parallel | chain | hitl | delegate
agent: claude-core
model: claude-sonnet-4-5
timeout: 300
trigger_keywords: [订票, 机票, 航班, flight]
```

**关键架构**：

| 现状 | 改造后 |
|---|---|
| 客户端在请求体里传 `system_prompt` / `skills` / `tools` | 客户端只传 `message` + `scenario`（或自动推断） |
| 编排模式在客户端临时选 | Scenario 声明一次，所有调用自动按该模式执行 |
| 路由逻辑散落在客户端代码 | 集中在 `ScenarioRouter`，可观测、可灰度、可 A/B |
| Skills / Tools 是全局可见 | Scenario 显式声明 **白名单**，物理隔离 + 防止越权 |

**非目标**：

- 不重写现有 `Scheduler` / `AgentBridge` —— 这层是**叠加**在它们之上的策略层
- 不强制所有 chat 都走 Scenario —— 保留 `/agent/chat` 直通模式（向后兼容）
- 不解决多租户隔离 / 鉴权 —— 那是 `tenant_id` 上层的事，本层只负责"把请求路由到对的一组配置"

---

## 1. 设计原则

| 原则 | 含义 | 反例 |
|---|---|---|
| **P1：渐进式叠加** | Scenario 是新层，**不**改 `Scheduler` / `AgentBridge` / `SkillRegistry` 现有 API | 改 `Scheduler.run()` 签名加 `scenario` 参数 |
| **P2：声明式优先** | 业务执行策略用 YAML 声明，**不要**写代码 | 在 Python 里 `if scenario == "flight": skills = [...]` |
| **P3：白名单强约束** | Scenario 只能使用它**显式声明**的 skills 和 tools；越权调用直接拒绝 | 默认全部可见，scenario 只是装饰 |
| **P4：路由决策可观测** | 每次 chat 必须留下 routing log：哪个 scenario、为什么选中、注入的 skills/tools 是什么 | 路由是黑盒 |
| **P5：失败可降级** | scenario 不存在 / 配置错误 / skill 找不到时，**必须**有兜底策略（拒绝 / 默认 scenario / 报错带原因） | 直接 500 |
| **P6：编排策略正交** | 编排模式（single/parallel/chain/hitl）是 Scenario 的一个字段，与 skills/tools 解耦 | 把编排逻辑写进 skill 的 prompt_template |
| **P7：热加载友好** | YAML 配置变更 → API 重载（不发版），路由立即生效 | 改配置必须重启进程 |

---

## 2. 核心概念

### 2.1 Scenario（场景）

> 一次完整对话的**执行策略包**：用什么系统提示词、加载哪些 Skill、暴露哪些 MCP 工具、用哪种调度模式、跑在哪个 Agent 上。

```python
@dataclass
class ScenarioConfig:
    """场景配置 — 一次执行策略的完整声明。"""

    # ---- 基础标识 ----
    name: str                                # 全局唯一，URL/Header 引用
    version: str = "1.0.0"                   # 语义化版本
    description: str = ""                    # 人类可读说明
    enabled: bool = True                     # False 时路由跳过

    # ---- 路由规则（多源冲突时按优先级）----
    trigger_keywords: list[str] = field(default_factory=list)
    trigger_intent: str | None = None        # 备用：可让 LLM 分类器识别
    url_path: str | None = None              # 形如 "/api/v1/booking/*"
    priority: int = 100                      # 数字越小优先级越高

    # ---- 执行策略（核心）----
    system_prompt: str = ""                  # 业务级 system prompt
    skills: list[str] = field(default_factory=list)     # Skill 白名单
    tools: list[str] = field(default_factory=list)      # MCP Tool 白名单
    orchestration: OrchestrationStrategy = "single"     # 调度模式

    # ---- 资源分配 ----
    agent: str | None = None                 # 指定 agent_name；None = 自动选
    model: str | None = None                 # 指定模型；None = agent default
    timeout: float = 120.0                   # 单轮超时（秒）

    # ---- 编排参数（不同模式使用不同字段）----
    parallel_n: int = 3                      # orchestration=parallel 时使用
    chain_max_steps: int = 10                # orchestration=chain 时使用
    hitl_card_schema: str | None = None      # orchestration=hitl 时使用
    delegate_main_skill: str | None = None   # orchestration=delegate 时使用

    # ---- 治理 ----
    tags: list[str] = field(default_factory=list)
    owner: str | None = None                 # 负责人 / 团队
    metadata: dict[str, Any] = field(default_factory=dict)  # 业务自定义元数据
```

### 2.2 OrchestrationStrategy（编排策略枚举）

```python
OrchestrationStrategy = Literal[
    "single",      # 单 Agent 单会话，1 个 prompt → 1 个回复
    "parallel",    # N 个 prompt 并行分发到 N 个 Agent，收集所有结果
    "chain",       # 顺序执行多步，上一步输出作为下一步上下文
    "hitl",        # Human-in-the-Loop，可挂起等待用户输入（接入 SuspendableScheduler）
    "delegate",    # 主 Agent 拆解子任务 → 并行委派 → 汇总（高级，需 main_skill 支持）
    "pipeline",    # 固定多阶段：A→B→C，每阶段可换 skill（chain 的强约束变体）
]
```

| 策略 | 现有映射 | 适用场景 |
|---|---|---|
| `single` | `Scheduler.run()` | 简单问答、单步工具调用 |
| `parallel` | `Scheduler.run_parallel()` | 调研类（同时查 N 个数据源）、A/B 评估 |
| `chain` | `Scheduler.run_chain()` | 多步规划、上下文累积的任务 |
| `hitl` | `SuspendableScheduler.run_turn()` | 需要用户中途确认、补全信息（订票/审批） |
| `delegate` | **新增** `Scheduler.run_delegate()` | 主 Agent 动态拆解 → 多个子 Agent → 汇总 |
| `pipeline` | **新增** `Scheduler.run_pipeline()` | 业务上固定的 N 阶段流程 |

### 2.3 ScenarioRegistry（场景注册中心）

> 对标现有的 `SkillRegistry` / `MCPRegistry`，负责 Scenario 的加载、查询、注册、版本管理。

```python
class ScenarioRegistry:
    """场景注册中心 — 与 SkillRegistry / MCPRegistry 同级。"""

    def __init__(self) -> None:
        self._scenarios: dict[str, ScenarioConfig] = {}     # name -> config
        self._by_url: dict[str, str] = {}                   # url_path -> name
        self._by_keyword: list[tuple[str, str]] = []         # [(keyword, name), ...]

    # ---- 加载 ----
    def load_from_paths(self, *paths: str) -> list[ScenarioConfig]:
        """从 YAML 目录加载所有 scenario 配置（递归找 *.scenario.yaml）。"""

    def load_from_dict(self, configs: list[dict]) -> list[ScenarioConfig]:
        """从配置列表加载（DB / API 写入场景用）。"""

    # ---- 注册 ----
    def register(self, config: ScenarioConfig) -> None:
        """注册或覆盖一个 scenario。"""

    def unregister(self, name: str) -> bool: ...

    # ---- 查询 ----
    def get(self, name: str) -> ScenarioConfig | None: ...
    def list_all(self) -> list[ScenarioConfig]: ...
    def list_enabled(self) -> list[ScenarioConfig]: ...

    # ---- 路由 ----
    def match_by_url(self, path: str) -> ScenarioConfig | None: ...
    def match_by_keyword(self, text: str) -> list[ScenarioConfig]:
        """按 trigger_keywords 匹配，按 priority 排序，取 top-1。"""

    def reload(self) -> None:
        """热加载：清空 + 从原路径重新加载。"""
```

### 2.4 ScenarioRouter（场景路由器）

> 这是 **新**的核心组件——每次 `/agent/chat` 或 `/agent/chat/stream` 进入时，第一个被调用的就是它。

```python
@dataclass
class RoutingContext:
    """路由决策的结果 + 推理过程。"""

    scenario: ScenarioConfig                  # 最终选中的场景
    matched_by: Literal["url", "header", "body", "keyword", "intent", "default"]
    candidates: list[str] = field(default_factory=list)  # 候选场景（按优先级）
    rejected: list[tuple[str, str]] = field(default_factory=list)  # 候选 + 拒绝原因


class ScenarioRouter:
    """根据请求多源信息，把请求路由到一个 ScenarioConfig。

    决策顺序（高 → 低优先级）：
        1. URL path 匹配   （/agent/scenarios/{name}/chat）
        2. Header 显式声明 （X-Scenario: flight_booking）
        3. Body 显式声明   （{"scenario": "flight_booking", ...}）
        4. Keyword 匹配    （从 user message 里匹配 trigger_keywords）
        5. Intent 分类器   （可选：调一个轻量 LLM 分类）
        6. Default scenario（settings.default_scenario）
    """

    def __init__(
        self,
        registry: ScenarioRegistry,
        settings: Settings,
        bridge: AgentBridge,                   # 用于 intent 分类
    ) -> None: ...

    async def route(
        self,
        *,
        request_path: str,
        headers: dict[str, str],
        body: dict[str, Any],
    ) -> RoutingContext:
        """执行路由决策，返回 RoutingContext。"""
```

### 2.5 ScenarioInjector（场景注入器）

> 拿到 `ScenarioConfig` 后，把 `system_prompt` / `skills` / `tools` 注入到下游 `bridge.chat()` 调用里。这是**唯一**会改请求体的地方。

```python
class ScenarioInjector:
    """把 ScenarioConfig 转化为 bridge.chat() 的入参。"""

    def __init__(
        self,
        skill_registry: SkillRegistry,
        mcp_registry: MCPRegistry,
    ) -> None: ...

    def inject(
        self,
        scenario: ScenarioConfig,
        user_message: str,
        *,
        caller_skills: list[str] | None = None,   # 客户端可以追加
        caller_tools: list[str] | None = None,    # 客户端可以追加
        caller_system_prompt: str | None = None,  # 客户端可以追加
    ) -> InjectionResult:
        """合并 system_prompt / 过滤 skills / 过滤 tools。"""
        ...


@dataclass
class InjectionResult:
    final_system_prompt: str
    final_skills: list[str]
    final_tools: list[MCPTool]     # 已经过滤 + 转 SDK 格式
    rejected_skills: list[str]     # scenario 白名单之外的
    rejected_tools: list[str]
    injection_log: list[str]       # 注入过程日志（用于 audit）
```

**关键行为**（白名单约束）：

| 调用方传 | Scenario 声明 | 最终注入 |
|---|---|---|
| skills=["a", "b"] | skills=["b", "c"] | `["b"]`（交集，越权部分被丢弃） |
| skills=["a"] | skills=["b"] | `[]`（scenario 不允许 a） |
| skills=None | skills=["b", "c"] | `["b", "c"]`（默认全启用） |

> **P3 白名单强约束**：如果 scenario 声明了 `skills=["b","c"]`，客户端想强行塞 `"a"`，**直接丢弃**而不是合并；越权 tool 同理。这避免恶意/拼错客户端把"机票系统 prompt + 财务 tool"这种离谱组合搞出来。

---

## 3. ScenarioConfig Schema（YAML 完整定义）

### 3.1 字段说明

```yaml
# === 必填 ===
name: flight_booking                  # 全局唯一场景名（kebab-case 建议）

# === 元信息（可选）===
version: "1.2.0"                      # 语义化版本
description: "飞鹤差旅机票预订主流程"
tags: [travel, booking, prod]
owner: team-travel-ai                 # 负责人/团队，用于权限审计
enabled: true                         # false 时路由跳过

# === 路由规则 ===
routing:
  url_path: null                      # 例: "/api/booking/*"（不推荐，RESTful 风格冲突）
  trigger_keywords:                   # 用于 keyword 匹配（中文分词可后续增强）
    - 订票
    - 机票
    - 航班
    - flight
  trigger_intent: null                # 可选：用于 LLM 分类器的 intent 标签
  priority: 100                       # 数字越小优先级越高（默认 100）

# === 核心：执行策略 ===
execution:
  system_prompt: |
    你是飞鹤差旅 AI 助手，专精于机票预订。
    严格遵守差标政策；不主动推荐超标航班。
    遇到政策模糊时主动询问用户。

  skills:                             # Skill 白名单（空数组 = 不加载任何 skill）
    - book-flight
    - policy-compliance

  tools:                              # MCP Tool 白名单
    - query_flight_basic
    - query_flight_realtime
    - choose_cabin
    - validate_policy
    - submit_order

  # ---- 编排策略（5 选 1）----
  orchestration: chain                # single | parallel | chain | hitl | delegate | pipeline

  # orchestration: chain 时
  chain:
    max_steps: 10

  # orchestration: parallel 时（可选）
  parallel:
    n: 3
    aggregation: merge                # merge | vote | first | best_of

  # orchestration: hitl 时（可选）
  hitl:
    card_schema: book-flight-v1       # 卡片 schema 名（见 book-flight-hitl-design.md）
    suspend_timeout: 300              # 单次挂起超时（秒）

  # orchestration: delegate 时（可选）
  delegate:
    main_skill: travel-orchestrator   # 主 Agent 加载的 skill
    sub_scenarios:                    # 允许委派给的子 scenario
      - flight_search
      - hotel_search

  # orchestration: pipeline 时（可选）
  pipeline:
    stages:
      - name: extract_intent
        skill: nlu-extractor
        output_to_ctx: intent
      - name: search
        skill: flight-searcher
        input_from_ctx: [intent, user]
        output_to_ctx: candidates
      - name: rank
        skill: flight-ranker
        input_from_ctx: [candidates, policy]
        output_to_ctx: ranked

# === 资源分配 ===
resources:
  agent: claude-core                  # 指定 agent 实例；null = 路由时自动选
  model: claude-sonnet-4-5            # 指定模型；null = agent default
  timeout: 300                        # 单轮超时（秒）

# === 业务元数据（自定义，不参与执行）===
metadata:
  cost_center: T-1001
  ab_group: control
  sla_tier: gold
  dashboard_url: https://grafana/...
```

### 3.2 完整场景示例集

```yaml
# scenarios/flight_booking.scenario.yaml
name: flight_booking
description: 飞鹤差旅 — 机票预订主流程（订票/改签/退票）
routing:
  trigger_keywords: [订票, 买机票, 订机票, flight, 改签, 退票]
  priority: 100
execution:
  system_prompt: |
    你是飞鹤差旅 AI 助手，专精于机票预订、改签、退票。
    严格遵守差标政策；不主动推荐超标航班。
    遇到政策模糊时主动询问用户。
  skills: [book-flight, policy-compliance]
  tools:
    - query_flight_basic
    - query_flight_realtime
    - choose_cabin
    - validate_policy
    - submit_order
    - request_refund
    - request_change
  orchestration: chain
resources:
  agent: claude-core
  model: claude-sonnet-4-5
  timeout: 300
tags: [travel, booking, prod]
owner: team-travel-ai
```

```yaml
# scenarios/expense_audit.scenario.yaml
name: expense_audit
description: 差旅报销单 AI 审核（并行查 4 个数据源 + 汇总）
routing:
  trigger_keywords: [报销, 审核, 差旅费, expense]
  priority: 90
execution:
  system_prompt: |
    你是差旅报销审核员。对报销单做合规检查并给出风险评分。
  skills: [expense-rules, risk-scoring]
  tools: [fetch_receipt_ocr, query_trip_record, check_policy_db, check_budget]
  orchestration: parallel
  parallel:
    n: 4
    aggregation: merge
resources:
  agent: opencode-core
  model: claude-sonnet-4-5
  timeout: 180
tags: [finance, audit]
```

```yaml
# scenarios/code_review.scenario.yaml
name: code_review
description: 代码审计 — 主 Agent 拆解 + 并行委派给多个专项审查
routing:
  trigger_keywords: [code review, 代码审查, 审计代码, 帮我审一下]
  priority: 80
execution:
  system_prompt: |
    你是代码审计协调员，接到一个 PR 后把任务拆给专项审查 Agent，
    最后汇总意见生成报告。
  skills: [review-orchestrator]
  tools: [read_file, search_code, git_diff, post_comment]
  orchestration: delegate
  delegate:
    main_skill: review-orchestrator
    sub_scenarios:
      - security_review
      - perf_review
      - style_review
resources:
  agent: claude-core
  timeout: 600
tags: [devtools, review]
```

```yaml
# scenarios/customer_service.scenario.yaml
name: customer_service
description: 通用客服（兜底场景，无特定意图）
routing:
  priority: 9999                     # 最低优先级，作为 fallback
execution:
  system_prompt: |
    你是飞鹤差旅 AI 客服。请礼貌、简洁地回答用户问题。
    超出能力范围时主动转人工。
  skills: [faq-search, handoff-to-human]
  tools: [crm_lookup, ticket_create]
  orchestration: single
resources:
  agent: opencode-core
  timeout: 60
tags: [fallback, support]
```

```yaml
# scenarios/_default.scenario.yaml
# 兜底场景：所有路由都失败时使用
name: _default
description: 兜底 — 不知道用户想干什么时用
routing:
  priority: 99999
execution:
  system_prompt: |
    你是飞鹤差旅 AI 助手。请简短回复，并主动询问用户想做什么。
  skills: []
  tools: []
  orchestration: single
resources:
  agent: opencode-core
  timeout: 30
```

---

## 4. 路由策略

### 4.1 多源决策树

```
incoming request
  │
  ├─ 1. URL path = /agent/scenarios/{name}/chat     ─► 100% 命中，name 即 scenario
  │
  ├─ 2. Header: X-Scenario: flight_booking         ─► 直接命中
  │
  ├─ 3. Body 字段: { "scenario": "flight_booking"}  ─► 直接命中
  │
  ├─ 4. 全部未命中 → 进入「推断模式」
  │     │
  │     ├─ 4a. Keyword 匹配
  │     │     遍历 registry.match_by_keyword(message)
  │     │     取 priority 最低的命中 scenario
  │     │
  │     ├─ 4b. Intent 分类器（可选，开关 settings.enable_intent_router）
  │     │     用轻量 LLM（Haiku / GPT-4o-mini）从 5 个候选里挑 1 个
  │     │     增加 200~500ms 延迟
  │     │
  │     └─ 4c. 全部失败 → 用 settings.default_scenario
  │                  （默认 settings.default_scenario = "_default"）
  │
  └─ 最终得到 RoutingContext → 注入器 → 进入实际执行
```

### 4.2 决策表

| 来源 | 优先级 | 配置开关 | 是否计入 routing_log |
|---|---|---|---|
| URL path | 0（最高） | — | ✅ |
| Header `X-Scenario` | 1 | — | ✅ |
| Body `scenario` | 2 | — | ✅ |
| Keyword 匹配 | 3 | `routing.fallback_strategy` | ✅ |
| Intent 分类 | 4 | `settings.enable_intent_router=true` | ✅ |
| Default | 5 | `settings.default_scenario` | ✅（标记为 default） |

### 4.3 反例：为什么不允许"完全靠 LLM 分类"

- 增加 200~500ms 延迟，影响首字节
- 分类器会"幻觉"出未声明的 scenario
- 难以 debug（"为什么用户这句话被路由到财务"）
- 成本敏感

→ **推荐**：Keyword 匹配 + URL 显式 + Header 显式，**默认不开** Intent 分类。

### 4.4 路由冲突解决

当多个 scenario 都可能被 Keyword 匹配上时：

```python
def match_by_keyword(self, text: str) -> ScenarioConfig | None:
    """命中规则:
    1. 计算每个 candidate 的命中分数 = sum(命中 keyword 数) / 总 keyword 数
    2. 按 priority 升序排（数字小的优先）
    3. 同 priority 按分数降序
    4. 都一样则取最早注册的
    """
    candidates = []
    for cfg in self._scenarios.values():
        if not cfg.enabled or not cfg.routing.trigger_keywords:
            continue
        hit = sum(1 for kw in cfg.routing.trigger_keywords if kw in text)
        if hit > 0:
            score = hit / len(cfg.routing.trigger_keywords)
            candidates.append((cfg, score))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0].routing.priority, -x[1]))
    return candidates[0][0]
```

---

## 5. 编排策略映射（与现有 Scheduler 的对应关系）

### 5.1 映射表

| Scenario.orchestration | 当前实现 | 新建工作 |
|---|---|---|
| `single` | `Scheduler.run()` ✅ 已有 | 无 |
| `parallel` | `Scheduler.run_parallel()` ✅ 已有 | `aggregation` 策略需扩展（merge/vote/best_of） |
| `chain` | `Scheduler.run_chain()` ✅ 已有 | `max_steps` 终止条件 |
| `hitl` | `SuspendableScheduler.run_turn()` ✅ 已有（见 `book-flight-hitl-design.md`） | 接入 card_schema |
| `delegate` | ❌ 需新增 `Scheduler.run_delegate()` | 主 Agent 拆解 → 子 scenario 并行 → 汇总 |
| `pipeline` | ❌ 需新增 `Scheduler.run_pipeline()` | 固定 stage 编排 |

### 5.2 5 种编排的详细流程图

#### 5.2.1 `single`（最简单）

```
Request
  ↓
Injector(填充 system_prompt + skills + tools)
  ↓
bridge.create_session(agent) → session_id
  ↓
bridge.chat(session, message, system_prompt, skills, tools)
  ↓
Response
```

#### 5.2.2 `parallel`（N 路并发）

```
Request{prompt}
  ↓
Injector
  ↓
Scheduler.run_parallel(
  prompts=[N 个 prompt 变体 / 拆解] | [N 个子查询],   # Scenario 决定怎么拆
  skills=[],
  tools=[],
  ...
)
  ↓
asyncio.gather([run(p1), run(p2), run(p3), ...])
  ↓
Aggregator(根据 execution.parallel.aggregation 策略)
  - merge:   把 N 个结果用 LLM 汇总
  - vote:    多数表决
  - first:   取第一个成功结果
  - best_of: 用评分 prompt 选最好的
  ↓
Response
```

**注**：Scenario 声明 `parallel.n=4` 时，框架会用 Scenario 内的主 system_prompt + skills/tools **自动拆解** 出 N 个子 prompt（不需要调用方提前拼好）。

#### 5.2.3 `chain`（上下文累积）

```
Request{user_prompt}
  ↓
Injector
  ↓
Scheduler.run_chain(
  prompts=[user_prompt, "基于上一步结果，...", "..."],
  ...
)   # 顺序执行，上一步输出拼到下一步 prompt 前
  ↓
for i, p in enumerate(prompts):
    bridge.chat(...)
    append_to_accumulated_context(result)
  ↓
Response{
  steps: 3,
  results: [...],
  final_context: "..."
}
```

#### 5.2.4 `hitl`（人机协作）

> **完全复用** `book-flight-hitl-design.md` 的 `SuspendableScheduler` 设计

```
Request{user_prompt, card_schema="book-flight-v1"}
  ↓
Scenario 加载 skill: book-flight
  ↓
SuspendableScheduler.run_turn(...)
  ↓
async for TurnEvent:
    if event.type == "suspend":
        return SuspendResponse{turn_id, suspend_event}
    elif event.type == "card":
        return Card{...}
    elif event.type == "done":
        return FinalResponse
  ↓
前端 POST /agent/turn/{turn_id}/resume{user_input}
  ↓
SuspendableScheduler.resume(turn_id, correlation_id, user_input)
  ↓
继续 stream events
  ↓
Response
```

#### 5.2.5 `delegate`（主从委派，**新增**）

> 主 Agent 拆解任务 → 并行调 N 个子 scenario → 主 Agent 汇总

```
Request{user_prompt}
  ↓
Injector
  ↓
Scheduler.run_delegate(
  main_scenario=current,                # 当前 scenario
  user_prompt=user_prompt,
  sub_scenarios=current.delegate.sub_scenarios,
)
  ↓
Phase 1: 主 Agent 思考拆解
    bridge.chat(skill=delegate.main_skill)
    → 吐出结构化 sub_tasks: [{scenario: "flight_search", input: {...}}, ...]
  ↓
Phase 2: 并行执行子 scenario
    tasks = [
        run_sub_scenario("flight_search", sub_task.input),
        run_sub_scenario("hotel_search", sub_task.input),
        ...
    ]
    results = await asyncio.gather(*tasks)
  ↓
Phase 3: 主 Agent 汇总
    bridge.chat(
        prompt=f"原始问题：{user_prompt}\n子任务结果：{results}\n请汇总。",
        skill=delegate.main_skill
    )
  ↓
Response{summary, sub_results}
```

#### 5.2.6 `pipeline`（固定阶段，**新增**）

> 与 `chain` 的区别：**每个阶段用不同的 skill/tool**，不允许模型自由发挥

```
Request{user_input}
  ↓
Injector (载入 pipeline[0].skill)
  ↓
Stage 1: skill=extract_intent
    input_from_ctx: [user]
    output_to_ctx: intent
    bridge.chat(skill=extract_intent, input=user_input)
    → ctx.intent = {...}
  ↓
Stage 2: skill=flight-searcher
    input_from_ctx: [intent, user]
    output_to_ctx: candidates
    bridge.chat(skill=flight-searcher, input={intent, user_input})
    → ctx.candidates = [...]
  ↓
Stage 3: skill=flight-ranker
    input_from_ctx: [candidates, policy]
    output_to_ctx: ranked
    bridge.chat(skill=flight-ranker, input={candidates, policy})
    → ctx.ranked = [...]
  ↓
Response{ranked, ctx}
```

---

## 6. 注入机制（Injector 内部）

### 6.1 System Prompt 拼接顺序

```
final_system_prompt
  ├─ 1. 框架级 base prompt（settings.base_system_prompt，可选）
  ├─ 2. Scenario 声明的 system_prompt
  ├─ 3. 客户端追加的 system_prompt（caller_system_prompt）
  └─ 4. 每个 Skill 的 prompt_template（按 Scenario.skills 顺序拼接）
```

> **示例**（场景 `flight_booking`，客户端无追加）：

```
[Framework Base]
You are an AI assistant. Current date: 2026-06-02. ...
[Scenario: flight_booking]
你是飞鹤差旅 AI 助手，专精于机票预订...
[Skill: book-flight v0.1]
<book-flight-skill.md body>
[Skill: policy-compliance v1.0.0]
<policy-compliance-skill.md body>
```

### 6.2 Skills 白名单过滤算法

```python
def filter_skills(
    scenario_skills: list[str],          # Scenario 声明的白名单
    caller_skills: list[str] | None,     # 客户端想追加的
    registry: SkillRegistry,
) -> tuple[list[str], list[str]]:
    """返回 (最终可用 skills, 被拒绝的 skills)。"""
    if scenario_skills is None:
        # Scenario 没声明 → 默认全开（向后兼容）
        whitelist = None
    else:
        whitelist = set(scenario_skills)

    if caller_skills is None:
        # 客户端没传 → 用 Scenario 的白名单
        return list(whitelist or registry.list_names()), []

    accepted = []
    rejected = []
    for name in caller_skills:
        if whitelist is None or name in whitelist:
            accepted.append(name)
        else:
            rejected.append(name)
    return accepted, rejected
```

### 6.3 Tools 白名单过滤算法

与 Skills 完全相同。区别只在最后一步：把名称列表映射成 `MCPTool` 对象（已经过滤 `enabled`、剔除 schema 不合规的）。

### 6.4 编排模式与注入器的边界

**Injector 只做单次注入**。`parallel` / `chain` / `pipeline` / `delegate` 的多次 chat 由 `Scheduler` 在循环/并发中复用同一个 `InjectionResult`：

```python
async def run_chain(self, scenario, user_prompt):
    injection = self._injector.inject(scenario, user_prompt)
    accumulated = ""
    results = []
    for step in scenario.execution.chain.steps:
        full_prompt = f"{accumulated}\n\n{step}" if accumulated else step
        result = await self._bridge.chat(
            session_id=session_id,
            messages=[ChatMessage(role="user", content=full_prompt)],
            system_prompt=injection.final_system_prompt,  # 复用
            skills=injection.final_skills,
            tools=injection.final_tools,
        )
        results.append(result)
        accumulated += f"\n--- Step {len(results)} ---\n{result.message.content}"
        if len(results) >= scenario.execution.chain.max_steps:
            break
    return results
```

---

## 7. 整体架构

### 7.1 模块图

```
┌────────────────────────────────────────────────────────────────────────┐
│                          Sanic  (api/app.py)                            │
│                                                                        │
│  /agent/chat              /agent/chat/stream                           │
│  /agent/scenarios         /agent/scenarios/{name}/chat                 │
│  /agent/scenarios/{name}/chat/stream                                   │
│                                                                        │
│           │                                                             │
│           ▼                                                             │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │ ScenarioMiddleware  (新增)                                        │ │
│  │  - 拦截请求 → 调 router.route() → 拿到 RoutingContext             │ │
│  │  - 调 injector.inject() → 拿到 InjectionResult                    │ │
│  │  - 写 routing_log                                                  │ │
│  │  - 把结果塞到 request.ctx                                          │ │
│  └──────────────┬───────────────────────────────────────────────────┘ │
│                 │                                                       │
│                 ▼                                                       │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │ 现有 Route handler  (api/routes.py)                               │ │
│  │  - 从 request.ctx 拿 scenario + injection                          │ │
│  │  - 按 scenario.execution.orchestration 选 Scheduler 方法          │ │
│  │  - 调 bridge.chat(stream=False) 或 stream                        │ │
│  └──────────────┬───────────────────────────────────────────────────┘ │
└─────────────────┼─────────────────────────────────────────────────────┘
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
┌──────────────────┐  ┌──────────────────┐
│  ScenarioRegistry │  │  ScenarioRouter  │
│  (新增)           │  │  (新增)           │
│                   │  │                   │
│  load YAML        │  │  6 优先级路由     │
│  register/unreg   │  │  match_by_url/    │
│  match_by_*       │  │  keyword/intent  │
│  reload (hot)     │  │                   │
└──────────────────┘  └──────────────────┘
        │                   │
        └─────────┬─────────┘
                  │
        ┌─────────▼─────────┐
        │  ScenarioInjector │
        │  (新增)            │
        │                   │
        │  - 拼 system_prompt│
        │  - 过滤 skills     │
        │  - 过滤 tools      │
        │  - 返回 Injection  │
        └─────────┬─────────┘
                  │
                  ▼
        ┌──────────────────┐
        │  现有 Bridge/     │
        │  Scheduler/      │  (零修改)
        │  SkillRegistry/  │
        │  MCPRegistry     │
        └──────────────────┘
```

### 7.2 新增文件清单

| 文件 | 行数上限 | 职责 |
|---|---|---|
| `src/openagent/scenarios/__init__.py` | 30 | 包入口 |
| `src/openagent/scenarios/config.py` | 250 | `ScenarioConfig` + `OrchestrationStrategy` 枚举 |
| `src/openagent/scenarios/registry.py` | 250 | `ScenarioRegistry`（加载/查询/热重载） |
| `src/openagent/scenarios/router.py` | 200 | `ScenarioRouter`（6 优先级路由） |
| `src/openagent/scenarios/injector.py` | 200 | `ScenarioInjector`（白名单过滤） |
| `src/openagent/scenarios/middleware.py` | 200 | Sanic middleware：拦截 /agent/* 注入 ctx |
| `src/openagent/scenarios/scheduler_adapter.py` | 300 | 把 `OrchestrationStrategy` 映射到 `Scheduler` 现有方法 + 新增 `run_delegate` / `run_pipeline` |
| `src/openagent/api/scenario_routes.py` | 300 | `/agent/scenarios/*` REST API |
| `src/openagent/store/scenario_store.py` | 250 | DB 持久化（Postgres + Memory） |
| `src/openagent/scenarios/intent_classifier.py` | 200 | 可选：LLM 分类器 |
| `scenarios/*.scenario.yaml` | – | 业务声明文件（git 版本化） |
| `tests/test_scenario_*.py` | – | 单测 + 集成 |

> 总增量约 ~2400 行（不含 YAML），小于一个独立工作流引擎的体量。

### 7.3 修改的现有文件

> 严格遵守 P1：只加**钩子**，不改签名

| 文件 | 改动 | 影响 |
|---|---|---|
| `src/openagent/api/app.py` | `app.ctx.scenario_registry` 初始化；`app.ctx.router` 初始化；注册 middleware | +30 行 |
| `src/openagent/api/routes.py` | `/agent/chat` 开头加 `request.ctx.scenario` 检查；`/agent/chat/stream` 同上；返回结果加 `scenario` 字段 | +40 行 |
| `src/openagent/core/scheduler.py` | 新增 `run_delegate` 和 `run_pipeline` 方法 | +200 行（保留 run/run_parallel/run_chain 签名） |
| `src/openagent/config/settings.py` | 新增 `scenario_paths`、`default_scenario`、`enable_intent_router`、`routing_log_enabled` | +20 行 |
| `src/openagent/store/postgres.py` | 新增 `scenario_config` / `scenario_routing_log` 两张表 | +80 行（DDL） |
| `src/openagent/store/base.py` | 新增 `ScenarioConfigRepository` / `RoutingLogRepository` ABC | +50 行 |

---

## 8. 数据流：3 个典型剧本

### 8.1 剧本 A：客户端显式指定（最简单）

```http
POST /agent/chat HTTP/1.1
X-Scenario: flight_booking
Content-Type: application/json

{
  "message": "帮我订明天北京到上海的机票"
}
```

```
T+0ms     客户端发请求（带 X-Scenario）
T+1ms     Middleware: router.route()
            - source = "header"
            - 命中 scenario=flight_booking
T+2ms     Middleware: injector.inject(scenario)
            - final_system_prompt = base + scenario.system_prompt
                                   + 2 个 skill 的 prompt_template
            - final_skills = ["book-flight", "policy-compliance"]
            - final_tools = [7 个 MCPTool]
T+3ms     Middleware: 写 routing_log
T+5ms     Route handler: scheduler.run()  (orchestration=single)
            → bridge.create_session("claude-core")
            → bridge.chat(stream=False)
T+2500ms  Response
{
  "success": true,
  "session_id": "...",
  "agent_name": "claude-core",
  "scenario": {
    "name": "flight_booking",
    "version": "1.2.0",
    "matched_by": "header"
  },
  "routing": {
    "candidates": ["flight_booking"],
    "rejected": [],
    "injection_log": ["injected skill: book-flight", "injected skill: policy-compliance", ...]
  },
  "result": { "message": { "role": "assistant", "content": "..." } }
}
```

### 8.2 剧本 B：自动 Keyword 路由 + 并行编排

```http
POST /agent/chat HTTP/1.1
Content-Type: application/json

{
  "message": "帮我审一下上个月差旅报销里有没有超标"
}
```

```
T+0ms     Middleware: router.route()
            - source = "keyword"
            - 遍历 scenarios: "expense_audit" 命中关键词 [报销, 审核, 差旅费]
            - 命中 scenario=expense_audit (priority=90)
T+1ms     Middleware: injector.inject()
            - system_prompt: "你是差旅报销审核员..."
            - skills: [expense-rules, risk-scoring]
            - tools: [fetch_receipt_ocr, query_trip_record, check_policy_db, check_budget]
            - orchestration: parallel, n=4
T+2ms     Middleware: 写 routing_log{matched_by: "keyword", scenario: "expense_audit"}
T+3ms     Route handler: scheduler.run_parallel()
            - Scenario 决定拆解: 用主 system_prompt 让 LLM 拆 4 个子查询
              sub_prompts = [
                "检查所有报销单的票据 OCR 完整性",
                "关联出差记录和报销单，验证一致性",
                "对照差标政策检查每张报销单",
                "检查预算剩余和单笔上限"
              ]
            - asyncio.gather([run(p1), run(p2), run(p3), run(p4)])
T+2000ms  4 个并行任务完成
            - aggregation: merge → 用 LLM 汇总成 1 份报告
T+2500ms  Response
{
  "scenario": { "name": "expense_audit", "matched_by": "keyword" },
  "routing": { "matched_by": "keyword", "candidates": ["expense_audit", "_default"] },
  "result": { "summary": "本次审计发现 3 个风险点...", "details": [...] }
}
```

### 8.3 剧本 C：HITL 场景（挂起/恢复）

```http
POST /agent/scenarios/flight_booking/chat/stream HTTP/1.1
Content-Type: application/json

{
  "message": "帮我订一张去上海的机票"
}
```

```
T+0ms     Middleware: router.route()
            - source = "url"
            - 命中 scenario=flight_booking
T+2ms     Middleware: injector.inject()
            - orchestration: hitl
            - card_schema: book-flight-v1
T+3ms     Route handler: SuspendableScheduler.run_turn(stream=True)
T+50ms    SSE: event: session { turn_id: "t-001" }
T+100ms   SSE: event: text "好的，让我帮您查询"
T+200ms   SSE: event: tool_use { name: "query_flight_basic", input: {...} }
T+1500ms  SSE: event: card OD_INPUT
T+1501ms  SSE: event: suspend { checkpoint_id: "ckpt-1", correlation_id: "ask_user_xyz" }
T+1502ms  SSE: event: done  (suspended 状态算 done)

前端: 渲染 OD_INPUT 表单，等用户填
前端 → POST /agent/turn/t-001/resume
       { correlation_id: "ask_user_xyz", user_input: {origin: "PEK", destination: "SHA", date: "2026-06-03"} }
T+30s     SuspendableScheduler.resume()
T+30.1s   SSE: event: resume { checkpoint_id: "ckpt-1" }
T+30.5s   SSE: event: text "已查询到 12 个航班"
T+31s     SSE: event: card FLIGHT_LIST
T+31.1s   SSE: event: suspend
...
```

> HITL 的完整协议见 `book-flight-hitl-design.md`，Scenario 层只是用 `orchestration: hitl` + `card_schema: ...` 字段引用它。

---

## 9. REST API 设计

### 9.1 现有 API 的增强（向后兼容）

#### `POST /agent/chat` —— 增强

**新可选字段**（`ChatRequest`）：

```python
class ChatRequest(BaseModel):
    # 现有字段...
    message: str
    session_id: Optional[str] = None
    agent_name: Optional[str] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    skills: Optional[list[str]] = None
    tools: Optional[list[str]] = None
    timeout: Optional[float] = None

    # ====== 新增 ======
    scenario: Optional[str] = None          # 显式指定 scenario
    # 当 scenario 不传时，由 router 推断
```

**新响应字段**（`ChatResponse`）：

```python
class ChatResponse(BaseModel):
    # 现有字段...
    success: bool
    session_id: str
    agent_name: str
    result: Optional[Any] = None
    error: Optional[str] = None
    duration: Optional[float] = None

    # ====== 新增 ======
    scenario: Optional[ScenarioInfo] = None
    routing: Optional[RoutingInfo] = None
```

#### `POST /agent/chat/stream` —— 增强

SSE 流最前面加 1 个 `scenario` 事件：

```
event: scenario
data: {"name": "flight_booking", "version": "1.2.0", "matched_by": "url"}

event: session
data: {"session_id": "..."}
...
```

### 9.2 新增 `/agent/scenarios/*` API

| 方法 | 路径 | 描述 |
|---|---|---|
| `GET` | `/agent/scenarios` | 列出所有 scenario（支持 `?tag=travel` 过滤） |
| `GET` | `/agent/scenarios/{name}` | 获取单个 scenario 详情 |
| `POST` | `/agent/scenarios` | 注册/覆盖一个 scenario（body 是 YAML 或 dict） |
| `PATCH` | `/agent/scenarios/{name}` | 部分更新（仅某些字段） |
| `DELETE` | `/agent/scenarios/{name}` | 注销 |
| `POST` | `/agent/scenarios/reload` | 热重载（从 YAML 路径重新加载） |
| `POST` | `/agent/scenarios/{name}/chat` | 通过该 scenario 聊（非流式） |
| `POST` | `/agent/scenarios/{name}/chat/stream` | 通过该 scenario 聊（SSE） |
| `GET` | `/agent/scenarios/routing-log` | 查询 routing log（按 session_id / scenario / 时间范围） |

#### 详细规格

```yaml
# POST /agent/scenarios
Request Body:
  name: flight_booking
  version: "1.2.0"
  description: "..."
  routing: { trigger_keywords: [...], priority: 100 }
  execution: { system_prompt: "...", skills: [...], tools: [...], orchestration: "chain" }
  resources: { agent: "claude-core", model: "claude-sonnet-4-5", timeout: 300 }
  tags: [travel, booking]
  enabled: true
  metadata: { ... }

Response 201:
  success: true
  scenario: { ... }   # 完整回显
  source: "db"        # db | yaml | api
```

```yaml
# GET /agent/scenarios?tag=travel
Response 200:
  success: true
  scenarios:
    - name: flight_booking
      version: "1.2.0"
      description: "..."
      enabled: true
      tags: [travel, booking]
      source: "yaml"  # 哪个文件来的
    - name: hotel_booking
      version: "1.0.5"
      ...
  total: 2
```

```yaml
# POST /agent/scenarios/{name}/chat
Path:   {name} = flight_booking
Body:   { "message": "帮我订机票", "session_id": null }
等价于: POST /agent/chat  +  body.scenario = "flight_booking"
```

### 9.3 错误码

| HTTP | code | 含义 |
|---|---|---|
| 400 | `SCENARIO_NOT_FOUND` | 引用的 scenario 不存在 |
| 400 | `SCENARIO_DISABLED` | scenario 被禁用 |
| 400 | `SKILL_NOT_ALLOWED` | 客户端传的 skill 不在白名单 |
| 400 | `TOOL_NOT_ALLOWED` | 客户端传的 tool 不在白名单 |
| 400 | `ORCHESTRATION_NOT_SUPPORTED` | orchestration 字段值非法 |
| 422 | `YAML_PARSE_ERROR` | 注册 scenario 时 YAML 格式错 |
| 500 | `ROUTING_FAILED` | 路由全失败且无 default_scenario |
| 503 | `SCENARIO_STORE_UNAVAILABLE` | DB 后端不可用 |

---

## 10. 持久化

### 10.1 表结构（Postgres DDL）

```sql
-- Scenario 配置（YAML 之外的运行时配置，DB 优先）
CREATE TABLE scenario_config (
    name           TEXT PRIMARY KEY,
    version        TEXT NOT NULL DEFAULT '1.0.0',
    description    TEXT,
    enabled        BOOLEAN NOT NULL DEFAULT TRUE,
    config         JSONB NOT NULL,              -- 完整 ScenarioConfig
    source         TEXT NOT NULL,               -- 'yaml' | 'api' | 'db'
    source_path    TEXT,                        -- YAML 文件路径
    created_at     TIMESTAMPTZ DEFAULT now(),
    updated_at     TIMESTAMPTZ DEFAULT now(),
    updated_by     TEXT
);
CREATE INDEX idx_scenario_enabled ON scenario_config(enabled);
CREATE INDEX idx_scenario_tags ON scenario_config USING GIN((config->'tags'));

-- 路由决策日志（每条 chat 一条）
CREATE TABLE scenario_routing_log (
    log_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id     UUID,                        -- 客户端请求 ID
    session_id     TEXT,                        -- bridge session_id
    matched_scenario TEXT NOT NULL,             -- 最终选中的 scenario
    matched_by     TEXT NOT NULL,               -- url | header | body | keyword | intent | default
    candidates     TEXT[],                      -- 候选 scenario 列表
    rejected       JSONB,                       -- [{scenario, reason}]
    injection_log  JSONB,                       -- 注入详情
    user_message   TEXT,                        -- 脱敏后
    latency_ms     INTEGER,
    status         TEXT,                        -- ok | error
    error          TEXT,
    created_at     TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_routing_session ON scenario_routing_log(session_id, created_at DESC);
CREATE INDEX idx_routing_scenario ON scenario_routing_log(matched_scenario, created_at DESC);
CREATE INDEX idx_routing_matched_by ON scenario_routing_log(matched_by, created_at DESC);
```

### 10.2 配置加载优先级

```
YAML 文件（versioned in git）
       │
       ▼  启动时 / reload 时
ScenarioRegistry._load_yaml()
       │
       ▼
DB scenario_config 表（admin UI 编辑）
       │
       ▼  覆盖策略：DB > YAML（同名时）
Final Registry (内存)
```

> **DB 覆盖 YAML 的好处**：紧急 disable 一个有 bug 的 scenario，不需要走 git PR + 部署。

### 10.3 Repository 抽象

```python
# store/base.py
class ScenarioConfigRepository(ABC):
    @abstractmethod
    async def get(self, name: str) -> dict | None: ...

    @abstractmethod
    async def list_all(self, tag: str | None = None) -> list[dict]: ...

    @abstractmethod
    async def upsert(self, name: str, config: dict, source: str, updated_by: str) -> None: ...

    @abstractmethod
    async def delete(self, name: str) -> bool: ...


class RoutingLogRepository(ABC):
    @abstractmethod
    async def append(self, log: RoutingLogEntry) -> None: ...

    @abstractmethod
    async def query(
        self,
        *,
        session_id: str | None = None,
        scenario: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[RoutingLogEntry]: ...
```

Postgres 实现放在 `store/postgres.py`，内存实现放在 `store/memory.py`（开发模式）。

---

## 11. 与现有架构的对接矩阵

| 现有组件 | 接入方式 | 改动量 |
|---|---|---|
| `SkillRegistry` | `ScenarioInjector` 调用 `build_system_prompt_with_skills` 拼 prompt | 0（复用） |
| `MCPRegistry` | `ScenarioInjector` 调用 `list_all_by_names(tools)` | 0（复用） |
| `AgentBridge` | `ScenarioInjector` 输出的 `InjectionResult` 直接喂给 `bridge.chat()` | 0（复用） |
| `Scheduler.run/parallel/chain` | `SchedulerAdapter.execute(orchestration, ...)` 内部 switch | +50 行 |
| `Scheduler.run_delegate / run_pipeline` | **新增** | +400 行 |
| `AgentPoolManager` | 0 改动（Scenario 里的 `agent` 字段直接传 name 进去） | 0 |
| `SuspendableScheduler` (HITL) | `SchedulerAdapter.execute("hitl", ...)` 转发 | 0（复用） |
| `Settings` (pydantic) | 新增 4 个字段 | +20 行 |
| `app.ctx` | 新增 `scenario_registry` / `scenario_router` | +5 行 |
| `Store Backend` | 新增 2 张表 + 2 个 repo | +200 行 |

> **P1 验证**：现有 `/agent/chat` 调通的所有测试用例，在本方案落地后**继续通过**（scenario 字段默认 None 时走"直通模式"）。

---

## 12. 实施路线图

### Phase 1：配置层 + 基础路由（1 周）

**目标**：Scenario 可声明、可加载、Keyword 可路由

- [ ] `scenarios/config.py` — `ScenarioConfig` dataclass + Pydantic validator
- [ ] `scenarios/registry.py` — `ScenarioRegistry` + YAML 加载
- [ ] `scenarios/injector.py` — `ScenarioInjector`（白名单过滤）
- [ ] `scenarios/__init__.py` — 包入口
- [ ] 5 个示例 scenario YAML 文件
- [ ] `tests/test_scenario_registry.py`、`tests/test_scenario_injector.py` 单测
- [ ] CI：scenario YAML 字段校验

**验收**：能从 YAML 加载 5 个 scenario，Keyword 路由命中正确率 100%。

### Phase 2：路由 + Middleware（1 周）

**目标**：客户端发请求自动落到正确 scenario

- [ ] `scenarios/router.py` — `ScenarioRouter`（6 优先级）
- [ ] `scenarios/middleware.py` — Sanic middleware
- [ ] `api/app.py` — 初始化 registry + router，挂 middleware
- [ ] `api/routes.py` — `/agent/chat` 增强（scenario 字段）
- [ ] `tests/test_scenario_router.py` 矩阵测试（6 源 × 5 场景）
- [ ] `tests/integration/test_scenario_routing.py` 端到端

**验收**：
- `POST /agent/chat {scenario: "flight_booking", ...}` → 命中 flight_booking
- `POST /agent/chat {message: "..."}`（无 scenario） → Keyword 路由
- `POST /agent/chat`（无任何线索） → `_default` 场景

### Phase 3：5 种编排策略（2 周）

**目标**：Scenario 声明的 orchestration 全部跑通

- [ ] `core/scheduler.py` 新增 `run_delegate()` + `run_pipeline()`
- [ ] `scenarios/scheduler_adapter.py` — 把 `OrchestrationStrategy` 映射到 Scheduler 方法
- [ ] `tests/test_scheduler_delegate.py`、`test_scheduler_pipeline.py`
- [ ] Phase 5 HITL 集成（参考 `book-flight-hitl-design.md` §6.2）

**验收**：6 种 orchestration 全部跑通，3 个业务剧本（单/并行/链/HITL/委派/管线）端到端测试通过。

### Phase 4：管理 API + 持久化（1 周）

**目标**：可以运行时增删改 scenario

- [ ] `store/scenario_store.py` — Postgres + Memory 实现
- [ ] `store/base.py` 新增 2 个 Repository ABC
- [ ] `store/postgres.py` 新增 2 张表 DDL
- [ ] `api/scenario_routes.py` — `/agent/scenarios/*` 9 个端点
- [ ] `tests/test_scenario_store.py` + 集成测试
- [ ] DB schema 迁移脚本

**验收**：通过 API 注册一个 scenario，立即生效；通过 `POST /agent/scenarios/reload` 热重载 YAML。

### Phase 5：监控 + 前端（1 周）

**目标**：可观测、可运营

- [ ] `scenarios/routing_log.py` — 自动写 routing_log
- [ ] `GET /agent/scenarios/routing-log` 查询 API
- [ ] Prometheus metrics：`scenario_route_total{scenario, matched_by}`、`scenario_route_latency_seconds`
- [ ] 前端 Scenario 管理界面（Vite + React）：
  - 列出所有 scenario
  - 编辑 system_prompt / skills / tools（YAML 编辑器）
  - 在线测试 chat
  - 查看 routing log
- [ ] Grafana dashboard 模板

**验收**：能查到"过去 1 小时 flight_booking 路由了 230 次，命中源分布：header 50% / keyword 40% / default 10%"。

### Phase 6：灰度 / A/B / 多租户扩展（1 周，后续）

- [ ] `metadata.ab_group` 路由：同 scenario 多个版本，按 user_id 灰度
- [ ] `metadata.tenant_id` 路由：不同租户走不同 scenario
- [ ] Intent 分类器（可选 `enable_intent_router=true`）
- [ ] scenario 限流 / 熔断

---

## 13. 关键代码示例

### 13.1 `ScenarioRouter.route()` 伪代码

```python
class ScenarioRouter:
    async def route(
        self,
        *,
        request_path: str,
        headers: dict[str, str],
        body: dict[str, Any],
    ) -> RoutingContext:
        candidates: list[str] = []
        rejected: list[tuple[str, str]] = []

        # 1. URL path
        m = re.match(r"^/agent/scenarios/([^/]+)/chat", request_path)
        if m:
            name = m.group(1)
            cfg = self._registry.get(name)
            if cfg and cfg.enabled:
                return RoutingContext(cfg, "url", candidates, rejected)
            rejected.append((name, f"not found or disabled (path={request_path})"))

        # 2. Header
        name = headers.get("X-Scenario") or headers.get("x-scenario")
        if name:
            cfg = self._registry.get(name)
            if cfg and cfg.enabled:
                return RoutingContext(cfg, "header", candidates, rejected)
            rejected.append((name, "not found or disabled (header)"))

        # 3. Body
        name = body.get("scenario")
        if name:
            cfg = self._registry.get(name)
            if cfg and cfg.enabled:
                return RoutingContext(cfg, "body", candidates, rejected)
            rejected.append((name, "not found or disabled (body)"))

        # 4. Keyword
        message = body.get("message", "")
        if message:
            matched = self._registry.match_by_keyword(message)
            for cfg in matched:
                candidates.append(cfg.name)
            if matched:
                return RoutingContext(matched[0], "keyword", candidates, rejected)

        # 5. Intent (optional, gated by settings)
        if self._settings.enable_intent_router and message:
            try:
                name = await self._intent_classifier.classify(message, candidates)
                cfg = self._registry.get(name)
                if cfg and cfg.enabled:
                    return RoutingContext(cfg, "intent", candidates, rejected)
            except Exception as e:
                logger.warning("intent_classifier_failed", error=str(e))

        # 6. Default
        default_name = self._settings.default_scenario or "_default"
        cfg = self._registry.get(default_name)
        if cfg is None:
            raise RoutingFailedError(
                f"No scenario matched and no default available. "
                f"Candidates: {candidates}, Rejected: {rejected}"
            )
        return RoutingContext(cfg, "default", candidates, rejected)
```

### 13.2 `SchedulerAdapter.execute()` 伪代码

```python
class SchedulerAdapter:
    """把 ScenarioConfig.orchestration 翻译成 Scheduler 调用。"""

    def __init__(self, scheduler: Scheduler, suspendable: SuspendableScheduler | None = None) -> None:
        self._scheduler = scheduler
        self._suspendable = suspendable

    async def execute(
        self,
        scenario: ScenarioConfig,
        injection: InjectionResult,
        user_prompt: str,
        *,
        session_id: str | None = None,
        stream: bool = False,
    ) -> TaskResult | AsyncIterator[StreamEvent]:
        orch = scenario.execution.orchestration

        if orch == "single":
            return await self._scheduler.run(
                prompt=user_prompt,
                agent_name=scenario.resources.agent,
                model=scenario.resources.model,
                system_prompt=injection.final_system_prompt,
                timeout=scenario.resources.timeout,
                skills=injection.final_skills,
                tools=[t.name for t in injection.final_tools],
            )

        if orch == "parallel":
            sub_prompts = await self._decompose_for_parallel(scenario, user_prompt, injection)
            results = await self._scheduler.run_parallel(
                prompts=sub_prompts,
                timeout=scenario.resources.timeout,
                skills=injection.final_skills,
                tools=[t.name for t in injection.final_tools],
            )
            return await self._aggregate(scenario, results)

        if orch == "chain":
            sub_prompts = scenario.execution.chain.steps or [user_prompt]
            return await self._scheduler.run_chain(
                prompts=[user_prompt] + sub_prompts[1:],  # 第一个用用户原始输入
                agent_name=scenario.resources.agent,
                model=scenario.resources.model,
                system_prompt=injection.final_system_prompt,
                timeout=scenario.resources.timeout,
                skills=injection.final_skills,
                tools=[t.name for t in injection.final_tools],
            )

        if orch == "hitl":
            if self._suspendable is None:
                raise NotConfiguredError("HITL requires SuspendableScheduler")
            return self._suspendable.run_turn(
                prompt=user_prompt,
                session_id=session_id,
                skill_hint=scenario.name,
                # ... 注入 prompt/skills/tools ...
            )

        if orch == "delegate":
            return await self._scheduler.run_delegate(
                user_prompt=user_prompt,
                main_scenario=scenario,
                sub_scenarios=scenario.execution.delegate.sub_scenarios,
                injection=injection,
            )

        if orch == "pipeline":
            return await self._scheduler.run_pipeline(
                user_prompt=user_prompt,
                scenario=scenario,
                injection=injection,
            )

        raise ValueError(f"Unknown orchestration: {orch}")
```

### 13.3 `app.py` 集成

```python
# api/app.py (新增片段)
from openagent.scenarios import ScenarioRegistry, ScenarioRouter, ScenarioInjector, ScenarioMiddleware

@Sanic("agent-scheduler-hub").after_server_start
async def startup(app: Sanic) -> None:
    # ... 现有初始化 ...

    # ---- 新增：Scenario 初始化 ----
    scenario_registry = ScenarioRegistry()
    if settings.scenario_paths:
        scenario_registry.load_from_paths(*settings.scenario_paths)
    # DB 覆盖 YAML
    if settings.scenario_db_override and hasattr(app.ctx, "storage"):
        scenario_registry.load_from_db(app.ctx.storage)

    scenario_injector = ScenarioInjector(
        skill_registry=skill_registry,
        mcp_registry=mcp_registry,
    )
    scenario_router = ScenarioRouter(
        registry=scenario_registry,
        settings=settings,
        bridge=bridge,
    )

    app.ctx.scenario_registry = scenario_registry
    app.ctx.scenario_injector = scenario_injector
    app.ctx.scenario_router = scenario_router

    # 挂中间件
    app.register_middleware(ScenarioMiddleware, "request")

    logger.info(
        "scenarios_loaded",
        count=len(scenario_registry.list_all()),
        enabled=len(scenario_registry.list_enabled()),
    )
```

### 13.4 Middleware 片段

```python
# scenarios/middleware.py
class ScenarioMiddleware:
    """拦截 /agent/chat* 路由：先做场景路由 + 注入。"""

    def __init__(self, app: Sanic) -> None:
        self.app = app

    async def __call__(self, request: Request) -> None:
        if not request.path.startswith("/agent/"):
            return
        if not (request.path.endswith("/chat") or "/chat/stream" in request.path):
            return

        body = request.json or {}
        headers = {k: v for k, v in request.headers.items()}

        # 1. 路由
        router: ScenarioRouter = self.app.ctx.scenario_router
        try:
            ctx = await router.route(
                request_path=request.path,
                headers=headers,
                body=body,
            )
        except RoutingFailedError as e:
            return self._reject(request, 500, "ROUTING_FAILED", str(e))

        # 2. 注入
        injector: ScenarioInjector = self.app.ctx.scenario_injector
        try:
            injection = injector.inject(
                scenario=ctx.scenario,
                user_message=body.get("message", ""),
                caller_skills=body.get("skills"),
                caller_tools=body.get("tools"),
                caller_system_prompt=body.get("system_prompt"),
            )
        except ScenarioInjectionError as e:
            return self._reject(request, 400, "INJECTION_FAILED", str(e))

        # 3. 写 routing_log
        if self.app.ctx.settings.routing_log_enabled:
            await self._log_routing(request, ctx, injection)

        # 4. 挂到 request.ctx
        request.ctx.scenario = ctx.scenario
        request.ctx.routing_context = ctx
        request.ctx.injection = injection

    def _reject(self, request, status, code, message):
        return JSONResponse(
            {"success": False, "error": message, "code": code},
            status=status,
        )
```

---

## 14. 与现有 `book-flight-hitl-design.md` 的关系

`book-flight-hitl-design.md` 设计了 **SuspendableScheduler + AUIP 协议**，解决"AI 等用户输入"的问题。**本方案是它的前置层**：

```
Scenario 层（本文）
    │
    │ scenario.execution.orchestration = "hitl"
    │ scenario.execution.hitl.card_schema = "book-flight-v1"
    │
    ▼
SuspendableScheduler 层（已有方案）
    │
    │ run_turn / resume / checkpoint
    │
    ▼
现有 AgentBridge / OpenCode / ClaudeCode
```

| 关注点 | book-flight-hitl-design.md | 本方案 |
|---|---|---|
| 抽象 | SuspendableScheduler、AUIP、Card | ScenarioConfig、ScenarioRouter、Injector |
| 关心什么 | 一次"问-答"跨多轮挂起 | 一次 chat 走哪一套执行策略 |
| Skill 关系 | Skill 是 manifest + state machine | Skill 是 Scenario 的白名单元素 |
| Provider 关系 | 双 SDK 透明（opencode / claude_code） | 双 SDK 透明（不变） |
| 状态 | Turn（跨挂起）| Scenario（一次 chat 的执行策略） |

**集成方式**：
- Scenario 的 `orchestration: hitl` 字段直接转发给 SuspendableScheduler
- Scenario 的 `card_schema` 字段对应 book-flight 的 `book-flight-v1` 等 schema 名
- Skill 加载复用：Scenario.skills 里的 `book-flight` 会被加载到 SuspendableScheduler 的 skill runtime

---

## 15. 风险与决策点

| 风险 | 影响 | 缓解 |
|---|---|---|
| **Skill 名拼错** | Scenario 启不来 | YAML schema 严格校验 + 启动时 dry-run 加载 |
| **Tool 被恶意客户端越权** | 安全风险 | P3 白名单强约束（默认拒绝）|
| **编排失败时部分 session 已创建** | 资源泄漏 | 每个编排函数用 `try/finally` 包 `bridge.delete_session` |
| **YAML 热重载覆盖 DB 编辑** | 误覆盖 | 优先级：DB > YAML；reload 时跳过 DB 已存在的 name |
| **Keyword 匹配误命中** | 错误路由 | 匹配分数 + priority 排序；高风险场景要求显式 scenario |
| **5 种编排 + 6 种路由路径 → 矩阵爆炸** | 测试复杂 | 矩阵测试 + 黄金剧本（剧本 A/B/C 必须通过） |
| **routing_log 写入失败阻塞主流程** | 性能/可用性 | 异步写入 + 本地缓存，DB 挂了不影响 chat |
| **Scenario 配置漂移** | A 环境与 B 环境行为不一致 | scenario YAML 进 git，CI 校验 schema |

### 待决策点

1. **Intent 分类器是否 Phase 1 必做？**
   - 推荐：**不做**，默认 Keyword 路由足够
2. **Scenario 优先级用 priority 数值还是显式 priority_class？**
   - 推荐：保留 `priority: int`，加注释 "数字越小优先级越高"
3. **Pipeline 与 Chain 的边界**？
   - 推荐：Chain 是 LLM 自由发挥的多步；Pipeline 是固定 N 阶段，**不允许** LLM 改 stage
4. **Delegate 的"主 Agent 拆解"是否用专用 LLM？**
   - 推荐：复用主 scenario 的 system_prompt + skill，**不**专门搞个 meta-LLM
5. **多租户隔离是否 Phase 1 做？**
   - 推荐：**不做**，Scenario 层只做"路由到对的一组配置"，tenant_id 在更上层（auth middleware）

---

## 16. 总结

本方案在 OpenAgent 现有架构上叠加一个 **Scenario** 抽象层，把"每次 chat 的执行策略"从客户端硬编码提升为 **配置驱动**：

1. **ScenarioConfig**（YAML）= 一次执行的完整策略包（system_prompt + skills + tools + orchestration + agent + model + timeout）
2. **ScenarioRegistry** 加载/查询/热重载
3. **ScenarioRouter** 6 优先级路由（URL > Header > Body > Keyword > Intent > Default）
4. **ScenarioInjector** 强白名单注入（防止越权）
5. **SchedulerAdapter** 把 6 种编排模式映射到现有 Scheduler
6. **DB 持久化** + **routing_log** 让路由可观测、可灰度
7. **向后兼容**：所有现有 `/agent/chat` 调用在 scenario 为空时保持原行为

**总工作量**：~2400 行 Python + 5 个示例 YAML + 9 个新 API 端点，分 6 个 Phase，4-5 周完成。

**与已有方案的关系**：
- 现有 `book-flight-hitl-design.md`（HITL）= `orchestration: hitl` 时的下游
- 现有 `agent-scheduler-proposal.md`（总方案）= 本方案是其 "阶段二：增强引擎" 的具体落地

**下一步**：
1. 在 `scenarios/` 目录放 3 个业务 scenario（flight_booking / expense_audit / customer_service）
2. 实现 Phase 1 + Phase 2 跑通端到端 demo
3. 评审通过后推进 Phase 3（5 种编排）
