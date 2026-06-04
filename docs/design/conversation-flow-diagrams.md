# OpenAgent 对话时序图 — 服务启动 + 3 种对话形态

> **目的**: 用 4 张 mermaid `sequenceDiagram` 把当前 F2 (scenario) + F4 (HITL) 改造后的实际代码路径画清楚。
> 覆盖:
> 1. **服务启动** — 引擎层 (opencode serve) 先起,Hub 后起,scenario/skill/tool registry 全部就位
> 2. **场景对话** — Client 显式传 `body.scenario` (或 `X-Scenario` / URL),走完整 scenario + injection 链
> 3. **普通对话** — 不传 scenario,命中 `_default`,无 skill 无 tool,纯 LLM
> 4. **单独加载 skill 对话** — 不传 scenario,命中 `_default`,但 caller 显式传 `body.skills`,且 default 白名单允许
>
> 关联源码:
> - `src/openagent/api/app.py` — Sanic 入口 + middleware 注册
> - `src/openagent/api/lifecycle.py` — `startup()` / `shutdown()`
> - `src/openagent/api/scenario_lifecycle.py` — scenario 子系统初始化
> - `src/openagent/scenarios/middleware.py` — `ScenarioMiddleware`
> - `src/openagent/scenarios/router.py` — 6 优先级 `ScenarioRouter`
> - `src/openagent/scenarios/injector.py` — 白名单 `ScenarioInjector`
> - `src/openagent/api/controllers/chat_controller.py` — `POST /agent/chat` + `/agent/chat/stream`
> - `src/openagent/providers/agent_bridge.py` — `AgentBridge`
> - `src/openagent/providers/opencode_adapter.py` — `OpenCodeAdapter` (薄壳)
> - `src/openagent/providers/opencode_chat.py` — `blocking_chat` / `stream_chat`
> - `src/openagent/core/scheduler.py` — `SchedulerService` (chat 任务编排)
> - `src/openagent/core/suspendable_scheduler.py` — `SuspendableScheduler` (HITL)
> - `src/openagent/core/turn_store.py` — `InMemoryTurnStore`
> - `src/openagent/providers/launcher.py` — `opencode serve` 进程生命周期

---

## 0. 组件与层对照

| 简称 | 实际类 / 模块 | 层 | 职责 |
|---|---|---|---|
| **Launcher** | `providers/launcher.py` | L4 | 拉起 `opencode serve` 进程 (Popen) |
| **OCS** | `opencode serve` (外部进程) | L4 | opencode 引擎 HTTP 入口 (:8080) |
| **Sanic** | `api/app.py` | L1 | 路由 + middleware 链 |
| **ScnMW** | `scenarios/middleware.py` | L1 | 拦截 `/agent/chat*` → 路由 + 注入 |
| **ScnRouter** | `scenarios/router.py` | L2 | 6 优先级路由 (URL>Header>Body>Keyword>Intent>Default) |
| **ScnReg** | `scenarios/registry.py` | L2 | 加载 `work/scenarios/*.scenario.yaml` |
| **ScnInj** | `scenarios/injector.py` | L2 | 白名单过滤 + 拼 system_prompt |
| **ChatCtrl** | `api/controllers/chat_controller.py` | L1 | `POST /agent/chat` + `/agent/chat/stream` |
| **Bridge** | `providers/agent_bridge.py` | L3 | 路由到正确 SDK 适配器 + session→agent 反查 |
| **Adapter** | `providers/opencode_adapter.py` | L3 | OpenCode 薄壳 (chat 委托给 `opencode_chat.py`) |
| **SDK** | `opencode_ai.AsyncOpencode` | L3 | opencode HTTP 客户端 |
| **Scheduler** | `core/scheduler.py` | L3 | 任务编排 (超时/重试) — 已被 ChatCtrl 直调 |
| **SuspendSch** | `core/suspendable_scheduler.py` | L3 | HITL 调度 (turn 状态机) |
| **TurnStore** | `core/turn_store.py` | L3 | 挂起 turn 持久化 (in-mem) |
| **Storage** | `store/*` (SessionRepository) | L3 | session + message 持久化 |
| **SkillReg** | `skills/registry.py` | L3 | `.skills/**/*.md` 元数据 |
| **MCPReg** | `mcp/registry.py` | L3 | MCP 工具元数据 |
| **LLM** | 外部 (anthropic / openai / ...) | - | LLM API |
| **MCP** | 外部 (flight / weather / ...) | - | MCP tool 端点 |

---

## 1. 服务启动 (Service Startup)

```mermaid
sequenceDiagram
    autonumber
    actor Operator
    participant Host
    participant Launcher
    participant OCS as opencode serve
    participant Hub as Sanic Hub
    participant Settings as .env
    participant Storage
    participant SkillReg as SkillRegistry
    participant MCPReg as MCPRegistry
    participant Bridge as AgentBridge
    participant ScnReg as ScenarioRegistry
    participant ScnRouter as ScenarioRouter
    participant ScnInj as ScenarioInjector
    participant TurnStore

    Operator->>Host: docker compose up / python -m openagent.main
    activate Host

    Note over Launcher, OCS: Phase A — 引擎层 (L4)
    Host->>Launcher: 启动 launcher 进程
    activate Launcher
    Launcher->>OCS: Popen(["opencode", "serve", "--port", "8080",<br/>"--cwd", project_dir])
    activate OCS
    OCS-->>Launcher: pid
    Launcher->>OCS: GET /health (轮询)
    OCS-->>Launcher: 200 OK
    deactivate Launcher

    Note over Hub, TurnStore: Phase B — Hub (L1~L3) 启动
    Hub->>Settings: load_settings()
    Settings-->>Hub: Settings(host, port, storage, ...)

    Hub->>Storage: connect() + init_schema()
    activate Storage
    Storage-->>Hub: ok
    deactivate Storage

    Hub->>SkillReg: load_from_paths(*.skills/)
    activate SkillReg
    SkillReg->>SkillReg: 递归扫 SKILL.md
    SkillReg-->>Hub: N skills
    deactivate SkillReg

    Hub->>MCPReg: from_config(mcp_tools_config)
    activate MCPReg
    MCPReg-->>Hub: M tools
    deactivate MCPReg

    Hub->>Bridge: AgentBridge(skill_reg, mcp_reg, storage)
    activate Bridge

    Note over Bridge, OCS: 注册默认 Agent (opencode-core)
    Hub->>Bridge: register(AgentConfig("opencode-core",<br/>base_url=opencode_base_url, sdk_type="opencode"))
    Bridge->>Bridge: 实例化 OpenCodeAdapter
    Bridge->>OCS: AsyncOpencode(base_url) lazy
    OCS-->>Bridge: client (缓存)
    Bridge-->>Hub: registered
    deactivate Bridge

    Hub->>ScnReg: ScenarioRegistry()
    activate ScnReg
    ScnReg->>ScnReg: 扫 work/scenarios/*.scenario.yaml
    ScnReg-->>Hub: K scenarios
    deactivate ScnReg

    Hub->>ScnRouter: ScenarioRouter(registry, default_scenario="_default")
    Hub->>ScnInj: ScenarioInjector(audit=InMemoryAuditLogger)
    Hub->>TurnStore: InMemoryTurnStore()
    activate TurnStore
    TurnStore-->>Hub: ready
    deactivate TurnStore

    Note over Hub: HITL factory (P5 简化: 全状态允许所有 tool)
    Hub->>Hub: app.ctx.hitl_factory = _default_factory

    Hub->>Hub: register_middleware(ScenarioMiddleware)
    Hub->>Hub: register_blueprint(chat_bp, pool_bp,<br/>registry_bp, session_bp)
    Hub->>Hub: app.run(host, port)

    Operator->>Hub: GET /ready
    Hub-->>Operator: {ok: true, scenarios: K, skills: N, tools: M}
    deactivate Host
```

**关键点**:
- 引擎层 (Phase A) **必须先于** Hub (Phase B) 起;否则 `bridge.register("opencode-core")` 会注册失败
- `ScenarioRegistry` 启动时**只读** `work/scenarios/*.yaml`,运行时改 YAML → 调 `POST /agent/scenarios/reload` 热重载
- `TurnStore` 走 `InMemoryTurnStore` (F4 简化版),重启丢;Phase 5 评估持久化

---

## 2. 场景对话 (Scenario Conversation)

> **示例**: Client 发 `POST /agent/chat` `body.scenario = "flight_booking"`,session 已在,scenario 是 HITL 编排 (走 SuspendableScheduler)

```mermaid
sequenceDiagram
    autonumber
    actor Client
    participant Sanic
    participant ScnMW as ScenarioMiddleware
    participant ScnRouter
    participant ScnReg
    participant ScnInj as ScenarioInjector
    participant ChatCtrl as ChatController
    participant Bridge as AgentBridge
    participant Adapter as OpenCodeAdapter
    participant SDK as AsyncOpencode
    participant OCS as opencode serve
    participant LLM
    participant MCP
    participant Storage
    participant SuspendSch as SuspendableScheduler
    participant TurnStore

    Client->>Sanic: POST /agent/chat<br/>{session_id, scenario:"flight_booking",<br/>message:"订明天北京到深圳的机票",<br/>skills:["flight-query"], tools:["mcp_flight"]}
    activate Sanic

    Sanic->>ScnMW: request middleware
    activate ScnMW
    ScnMW->>ScnRouter: route(path, headers, body)
    activate ScnRouter
    ScnRouter->>ScnRouter: 6 优先级检查<br/>(URL→Header→Body→Keyword→Intent→Default)
    Note right of ScnRouter: body.scenario="flight_booking" 命中 #3 (Body)
    ScnRouter->>ScnReg: get("flight_booking")
    ScnReg-->>ScnRouter: ScenarioConfig
    ScnRouter-->>ScnMW: RoutingContext(scenario, matched_by="body")
    deactivate ScnRouter

    ScnMW->>ScnInj: inject(scenario, user_message,<br/>caller_skills, caller_tools, caller_system_prompt)
    activate ScnInj
    Note right of ScnInj: final_skills = scenario.allowed ∩ caller<br/>final_tools = scenario.allowed ∩ caller<br/>final_prompt = scenario.system_prompt + "\n\n" + caller
    ScnInj-->>ScnMW: InjectionResult
    deactivate ScnInj

    ScnMW->>Sanic: request.ctx.scenario = cfg<br/>request.ctx.injection = result
    deactivate ScnMW

    Sanic->>ChatCtrl: dispatch chat(request)
    activate ChatCtrl
    ChatCtrl->>ChatCtrl: 检查 ctx.scenario_error (无)
    ChatCtrl->>ChatCtrl: 解析 body, 取 params =<br/>injection.final_*
    ChatCtrl->>ChatCtrl: 判定 orchestration<br/>(= "hitl" → SuspendableScheduler<br/>= "single" → bridge.chat)
    Note right of ChatCtrl: 本例 orchestration=hitl
    activate SuspendSch

    ChatCtrl->>TurnStore: create_turn(session_id, skill_name="flight_booking")
    activate TurnStore
    TurnStore-->>ChatCtrl: turn_id
    deactivate TurnStore

    ChatCtrl->>SuspendSch: factory(scenario) → 实例
    ChatCtrl->>SuspendSch: run_turn(turn_id, session_id,<br/>augmented_prompt)
    activate SuspendSch

    ChatCtrl->>Bridge: get_agent_for_session(session_id) → agent_name
    Bridge-->>ChatCtrl: "opencode-core"
    ChatCtrl->>Bridge: (在 SSE 流中按事件按需) create_session if needed

    Note over SuspendSch, LLM: 单步 turn (state 推进)
    SuspendSch->>Adapter: (调度器内部) bridge.chat(state_msg)
    activate Adapter
    Adapter->>SDK: client.session.chat(session_id, parts)
    activate SDK
    SDK->>OCS: HTTP POST /session/{id}/message
    activate OCS
    OCS->>OCS: 加载 skill:<br/>work/.../.skills/flight-query/SKILL.md
    OCS->>LLM: HTTP POST /v1/messages<br/>(system_prompt + skill 渲染后)
    activate LLM
    LLM-->>OCS: tool_use{mcp_flight.search}
    deactivate LLM
    OCS->>MCP: HTTP POST flight-api /search
    activate MCP
    MCP-->>OCS: 航班列表
    deactivate MCP
    OCS->>LLM: tool_result 注入
    activate LLM
    LLM-->>OCS: text + 可能再 tool_use
    deactivate LLM
    OCS-->>SDK: SSE events
    deactivate OCS
    SDK-->>Adapter: AsyncIterator[StreamEvent]
    deactivate SDK
    Adapter-->>SuspendSch: events
    deactivate Adapter

    SuspendSch->>TurnStore: 更新 turn state / event_log
    activate TurnStore
    TurnStore-->>SuspendSch: ok
    deactivate TurnStore

    alt 到达终态 / 工具触发 card
        SuspendSch-->>ChatCtrl: TurnEvent(type=SUSPEND,<br/>card, input_schema)
        Note right of ChatCtrl: SSE `suspend` 事件后停流<br/>client 必须 POST /turn/{id}/resume 续接
    else 普通状态推进
        SuspendSch-->>ChatCtrl: TurnEvent(type=TEXT/TOOL_USE/...)
        Note right of ChatCtrl: SSE `text`/`tool_use` 事件
    end

    loop 直到 SUSPEND 或 DONE
        SuspendSch->>SuspendSch: 下一轮 step
    end
    deactivate SuspendSch

    ChatCtrl-->>Sanic: SSE stream
    deactivate ChatCtrl
    Sanic-->>Client: text/event-stream<br/>(scenario→session→text→...→suspend/done)
    deactivate Sanic

    Note over Client, TurnStore: 对话"挂起"或"结束"<br/>- 挂起: turn 状态在 TurnStore,等 /resume<br/>- 结束: turn 关闭,session 仍在 OCS 内存
```

**关键点**:
- 场景对话的 skill 列表**只来自 scenario 自己的 `execution.skills` 白名单** (与 caller 传入的 `body.skills` 取交集)
- HITL 模式下,**turn 状态独立于 session**:session 在 OCS,turn 在 TurnStore
- `suspend` 后客户端必须调 `POST /turn/{id}/resume` (见 `turn_routes.py:166`)

---

## 3. 普通对话 (Normal Conversation)

> **示例**: Client 发 `POST /agent/chat` **不传** `scenario` / `skills` / `tools`,命中 `_default` (allowed_skills/tools 为空),纯 LLM 调

```mermaid
sequenceDiagram
    autonumber
    actor Client
    participant Sanic
    participant ScnMW as ScenarioMiddleware
    participant ScnRouter
    participant ScnReg
    participant ScnInj as ScenarioInjector
    participant ChatCtrl as ChatController
    participant Bridge as AgentBridge
    participant Adapter as OpenCodeAdapter
    participant SDK as AsyncOpencode
    participant OCS as opencode serve
    participant LLM
    participant Storage

    Client->>Sanic: POST /agent/chat<br/>{message:"写一首关于春天的诗"}
    activate Sanic

    Sanic->>ScnMW: request middleware
    activate ScnMW
    ScnMW->>ScnRouter: route(path, headers, body)
    activate ScnRouter
    ScnRouter->>ScnRouter: 6 优先级全部 miss<br/>(无 URL/Header/Body/Keyword 命中)
    ScnRouter->>ScnRouter: 落回 #6 default → "_default"
    ScnRouter->>ScnReg: get("_default")
    ScnReg-->>ScnRouter: ScenarioConfig(allowed_skills=[],<br/>allowed_tools=[], system_prompt="You are helpful")
    ScnRouter-->>ScnMW: RoutingContext(scenario=_default, matched_by="default")
    deactivate ScnRouter

    ScnMW->>ScnInj: inject(scenario=_default,<br/>caller_skills=None, caller_tools=None)
    activate ScnInj
    Note right of ScnInj: final_skills = [] (空交集)<br/>final_tools  = []<br/>final_prompt = _default.system_prompt
    ScnInj-->>ScnMW: InjectionResult(空)
    deactivate ScnInj

    ScnMW->>Sanic: request.ctx.scenario = _default<br/>request.ctx.injection = (空)
    deactivate ScnMW

    Sanic->>ChatCtrl: dispatch chat(request)
    activate ChatCtrl
    ChatCtrl->>Bridge: create_session(agent_name="opencode-core")
    activate Bridge
    Bridge->>Adapter: create_session()
    activate Adapter
    Adapter->>SDK: client.session.create()
    activate SDK
    SDK->>OCS: HTTP POST /session
    OCS-->>SDK: session_id
    SDK-->>Adapter: SessionInfo
    deactivate SDK
    Adapter-->>Bridge: session_id
    deactivate Adapter
    Bridge-->>ChatCtrl: session_id
    deactivate Bridge

    ChatCtrl->>Storage: save_session(Session)
    activate Storage
    Storage-->>ChatCtrl: ok
    deactivate Storage

    ChatCtrl->>Bridge: chat(session_id, messages,<br/>system_prompt=_default.system_prompt,<br/>skills=[], tools=[], timeout)
    activate Bridge
    Bridge->>Adapter: chat(stream=False)
    activate Adapter
    Adapter->>SDK: client.session.chat(session_id, parts,<br/>model, system_prompt, skills=[], tools=[])
    activate SDK
    SDK->>OCS: HTTP POST /session/{id}/message
    activate OCS
    Note right of OCS: 不加载任何 skill<br/>不渲染 system_prompt 之外的额外 prompt
    OCS->>LLM: POST /v1/messages<br/>(仅 system_prompt + user message)
    activate LLM
    LLM-->>OCS: text content
    deactivate LLM
    OCS-->>SDK: {message, stop_reason}
    deactivate OCS
    SDK-->>Adapter: ChatResult
    deactivate SDK
    Adapter-->>Bridge: ChatResult
    deactivate Adapter
    Bridge-->>ChatCtrl: ChatResult
    deactivate Bridge

    ChatCtrl->>Storage: save_message(user_msg)<br/>+ save_message(assistant_msg)
    activate Storage
    Storage-->>ChatCtrl: ok
    deactivate Storage

    ChatCtrl-->>Sanic: JSONResponse(ChatResponse)
    deactivate ChatCtrl
    Sanic-->>Client: {success, session_id,<br/>result:{message, tool_calls:[],<br/>stop_reason:"end_turn"},<br/>scenario:{name:_default,matched_by:default}}
    deactivate Sanic

    Note over Client, OCS: 对话结束<br/>- session 状态保留在 OCS 内存 (idle 不消)<br/>- 历史消息落 Storage<br/>- 客户端可凭 session_id 续接
```

**关键点**:
- 普通对话**不是"绕过 scenario"**——它**也走 middleware**,只是命中 default scenario
- 想要真正的"裸 LLM"必须有一个 `_default` scenario 且 `allowed_skills=[]`、`allowed_tools=[]`
- `_default` 缺失时 `route()` 抛 `RoutingFailedError` → controller 返回 400 (设计如此,防止裸奔)

---

## 4. 单独加载 skill 对话 (Standalone Skill Conversation)

> **示例**: Client 发 `POST /agent/chat` **不传** `scenario`,但显式传 `body.skills=["weather-query"]`,命中 `_default` (其白名单允许 weather-query),tool 不传

```mermaid
sequenceDiagram
    autonumber
    actor Client
    participant Sanic
    participant ScnMW as ScenarioMiddleware
    participant ScnRouter
    participant ScnReg
    participant ScnInj as ScenarioInjector
    participant ChatCtrl as ChatController
    participant Bridge as AgentBridge
    participant Adapter as OpenCodeAdapter
    participant SDK as AsyncOpencode
    participant OCS as opencode serve
    participant LLM
    participant MCP as MCP weather
    participant Storage

    Client->>Sanic: POST /agent/chat<br/>{message:"北京明天天气怎么样",<br/>skills:["weather-query"]}
    activate Sanic

    Sanic->>ScnMW: request middleware
    activate ScnMW
    ScnMW->>ScnRouter: route(path, headers, body)
    activate ScnRouter
    ScnRouter->>ScnRouter: body.scenario 缺失<br/>keyword 不命中<br/>→ 落回 #6 default "_default"
    ScnRouter->>ScnReg: get("_default")
    Note right of ScnReg: _default.execution.skills<br/>= ["weather-query", ...]
    ScnReg-->>ScnRouter: ScenarioConfig
    ScnRouter-->>ScnMW: RoutingContext(matched_by="default")
    deactivate ScnRouter

    ScnMW->>ScnInj: inject(scenario=_default,<br/>caller_skills=["weather-query"])
    activate ScnInj
    Note right of ScnInj: final_skills = ["weather-query"]<br/>(白名单 ∩ caller = 命中)<br/>final_tools  = []<br/>rejected_skills = []<br/>final_prompt = _default.system_prompt
    ScnInj-->>ScnMW: InjectionResult(skills=["weather-query"])
    deactivate ScnInj

    ScnMW->>Sanic: request.ctx.scenario = _default<br/>request.ctx.injection = result
    deactivate ScnMW

    Sanic->>ChatCtrl: dispatch chat(request)
    activate ChatCtrl
    ChatCtrl->>ChatCtrl: params = injection.final_*<br/>(skills=["weather-query"], tools=[])
    ChatCtrl->>Bridge: create_session() / get_agent_for_session()
    activate Bridge
    Bridge-->>ChatCtrl: session_id
    deactivate Bridge

    ChatCtrl->>Bridge: chat(session_id, messages,<br/>system_prompt, skills=["weather-query"],<br/>tools=[], timeout)
    activate Bridge
    Bridge->>Adapter: chat()
    activate Adapter
    Adapter->>SDK: client.session.chat(session_id, parts,<br/>model, system_prompt,<br/>skills=["weather-query"], tools=[])
    activate SDK
    SDK->>OCS: HTTP POST /session/{id}/message
    activate OCS
    OCS->>OCS: 加载 skill:<br/>work/.../.skills/weather-query/SKILL.md
    OCS->>OCS: 拼 system_prompt =<br/>base + <skill name=weather-query>...</skill>
    OCS->>LLM: POST /v1/messages<br/>(skill 渲染后的完整 prompt)
    activate LLM
    LLM-->>OCS: tool_use{get_weather}
    deactivate LLM
    OCS->>MCP: HTTP POST mcp-weather /get_weather
    activate MCP
    MCP-->>OCS: 天气数据
    deactivate MCP
    OCS->>LLM: tool_result 注入
    activate LLM
    LLM-->>OCS: text "北京明天晴,18~25℃"
    deactivate LLM
    OCS-->>SDK: {message, tool_calls}
    deactivate OCS
    SDK-->>Adapter: ChatResult
    deactivate SDK
    Adapter-->>Bridge: ChatResult
    deactivate Adapter
    Bridge-->>ChatCtrl: ChatResult
    deactivate Bridge

    ChatCtrl->>Storage: save_message × 2
    activate Storage
    Storage-->>ChatCtrl: ok
    deactivate Storage

    ChatCtrl-->>Sanic: JSONResponse
    deactivate ChatCtrl
    Sanic-->>Client: {success, session_id, agent_name,<br/>result:{message, tool_calls:[{name:"get_weather"}],<br/>stop_reason:"end_turn"},<br/>routing:{matched_by:default, rejected_skills:[]}}
    deactivate Sanic

    Note over Client, OCS: 对话结束<br/>- session 保留在 OCS 内存<br/>- 后续同一 session_id 不传 skills 也能用 (history 续接)<br/>- 下次若再传 skills 不同的,以本次注入为准
```

**关键点**:
- "单独加载 skill" 跟"普通对话"差别**只在 caller 传了 `body.skills`**:让 `_default` 的白名单生效
- `rejected_skills` 字段会回传给 client,方便排查"我传了但没生效"的问题
- **没有 scenario ≠ 绕过注入**:即便走 default,middleware 仍跑、Injector 仍过滤

---

## 5. 3 种对话的差异对照

| 维度 | 场景对话 | 普通对话 | 单独加载 skill |
|---|---|---|---|
| `body.scenario` | 显式传 | 不传 | 不传 |
| `body.skills` | 可选(白名单内) | 不传 | 显式传 |
| ScnRouter 命中 | URL/Header/Body/Keyword (前 5 优先级) | default (第 6) | default (第 6) |
| `matched_by` 字段 | `body` / `header` / `url` / `keyword` | `default` | `default` |
| `injection.final_skills` | scenario 白名单 ∩ caller | `[]` (default 为空) | caller (若 default 允许) |
| `injection.final_system_prompt` | scenario.system_prompt + caller | default.system_prompt | default.system_prompt |
| 是否可走 HITL | ✅ (orchestration=hitl) | ❌ (default 通常 single) | ❌ |
| Turn 是否进 TurnStore | ✅ (HITL) 或 ❌ (single) | ❌ | ❌ |
| OCS 是否加载 skill | ✅ (scenario / caller 列表) | ❌ | ✅ (caller 列表) |
| MCP tool 是否可达 | ✅ (scenario 允许) | ❌ | ❌ (除非 default 允许) |
| `rejected_skills` 字段 | 可能有 (caller 超白名单) | `[]` | 可能有 (caller 超 default 白名单) |

---

## 6. 对话"结束"的状态留痕

| 结束方式 | 状态落在哪 | 续接方式 |
|---|---|---|
| **普通场景对话 (single)** | session 在 OCS 内存 + Storage | 凭 `session_id` 续发即可,SDK 自动 resume |
| **HITL 场景对话 (suspend)** | turn 在 TurnStore (F4 简化:in-mem), session 在 OCS | 客户端调 `POST /turn/{id}/resume` (body: form 填写结果) |
| **普通对话 / 单独 skill** | session 在 OCS 内存 + Storage | 凭 `session_id` 续发 |
| **任何 chat 中途出错** | error event 推 SSE / JSON `error` 字段 | 客户端重试,需要的话带新 session_id |
| **Server shutdown** | session 状态**丢失** (OCS 内存) | 客户端需建新 session;Storage 里的 message 历史仍在,UI 可拼回 |

---

## 7. 错误流的统一出口

| 错误源 | 表现 | 客户端看到 |
|---|---|---|
| `ScenarioMiddleware.route()` 抛 `RoutingFailedError` | `request.ctx.scenario_error = e` | `chat`: 400 JSON `{success:false, code:"ROUTING_FAILED", error:..., action:...}`<br/>`chat_stream`: SSE `error` 事件后 eof |
| `ScenarioInjector.inject()` 失败 | 同上,挂 `INJECTION_FAILED` | 同上 |
| `bridge.create_session()` 失败 | controller catch | 500 JSON,`error: "TypeError: ... [traceback]"` |
| `OCS` HTTP 5xx / 超时 | adapter raise | controller catch → 500 JSON / SSE `error` |
| LLM API 4xx/5xx | opencode serve 返回 error | result.error 字段填充,success=false |
| HITL 状态机走错 | SuspendableScheduler emit `TurnEvent(ERROR)` | SSE `error` 事件 |

---

## 8. 验证清单 (用这些图查实现)

- [ ] 启动顺序:launcher 拉 OCS 在前,Hub 在后,否则 `opencode-core` 注册失败
- [ ] middleware **只拦截** `/agent/chat` + `/agent/chat/stream` + `/agent/scenarios/{name}/chat`,其他 URL 不动
- [ ] 场景对话的 `matched_by` 跟路由优先级一致 (URL > Header > Body > Keyword > Intent > Default)
- [ ] 普通对话 / 单独 skill **仍走** middleware (只是命中 default)
- [ ] `_default` 缺失时 `chat` 必返回 400,不会"裸奔"调 LLM
- [ ] `final_skills` = 交集,`rejected_skills` 必有值或空数组
- [ ] HITL 模式下,SSE 流里**必有** `scenario` → `session` → `card` → `suspend` 序列,然后停
- [ ] 单步场景 SSE 流:**有** `scenario` → `session` → `text/tool_use/tool_result` → `done`
- [ ] session 状态在 OCS 内存,关 OCS 进程就丢;Storage 里的 message 历史独立保留
