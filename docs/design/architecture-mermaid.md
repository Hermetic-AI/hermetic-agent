# OpenAgent 架构 Mermaid 图（v0.1 — 2026-06-05）

> 基于 `docs/design/integrated-orchestration-plan.md` + `CLAUDE.md` 当前实现的"最新架构"。
> 5 层代码分层、**统一对话入口**（仅 `POST /agent/chat` 与 `/agent/chat/stream`）、Scenario × Skill Runtime × AUIP 整合。

---

## 1. 总体架构（5 层泳道 + 资源 + 基础设施）

> **设计原则**：每层一个色块泳道，主流程 `==>` 粗箭头沿 L1→L4 一路下穿；
> `work/` 资源在左、`L5` 基础设施在底作 foundation，全用虚线 `-->` 表示非主链路。
> 组件级细节见 §2–§8。

```mermaid
flowchart TB
    %% ============== 外部（顶 / 右） ==============
    CLIENT["🖥  Frontend<br/>(React + TS + AUIRenderer)"]:::ext
    ENG["⚙  External Engines<br/>opencode serve · claude-agent CLI"]:::ext

    %% ============== 5 层泳道 ==============
    subgraph LANE1["L1 · API Layer  (api/)"]
        direction LR
        L1N["chat_controller · middleware<br/>scenario_controller · turn_routes"]
    end
    subgraph LANE2["L2 · Scenarios  (scenarios/)"]
        direction LR
        L2N["router · registry · loader<br/>injector · scheduler_adapter"]
    end
    subgraph LANE3["L3 · Skill Runtime + AUIP + Core"]
        direction LR
        L3N["SuspendableScheduler · skill_runtime<br/>auip · turn_store"]
    end
    subgraph LANE4["L4 · Providers  (providers/)"]
        direction LR
        L4N["launcher · bridge<br/>opencode_adapter · claude_code_adapter"]
    end
    subgraph LANE5["L5 · Infrastructure  (policy/ · store/ · sandbox/)"]
        direction LR
        L5N["policy · store · sandbox"]
    end

    %% ============== 资源（左） ==============
    WORK["📂  work/ 资源目录<br/>scenarios yaml · cards<br/>skills · shared · cache"]:::data

    %% ============== 主流程（粗箭头 ==） ==============
    CLIENT ==>|"POST /agent/chat"| L1N
    L1N ==>|"scenario + inject"| L2N
    L2N ==>|"SuspendableScheduler"| L3N
    L3N ==>|"launch engine"| L4N
    L4N ==>|"SDK call"| ENG

    %% ============== 资源读取（虚线 .） ==============
    WORK -.->|"yaml"| L1N
    WORK -.->|"read"| L2N
    WORK -.->|"fragments"| L3N

    %% ============== 基础设施支撑（虚线 .） ==============
    L1N -.-> L5N
    L2N -.-> L5N
    L3N -.-> L5N
    L4N -.-> L5N

    %% ============== 配色 ==============
    classDef ext fill:#eceff1,stroke:#37474f,color:#263238
    classDef data fill:#fce4ec,stroke:#ad1457,color:#880e4f
    style LANE1 fill:#e3f2fd,stroke:#1565c0,color:#0d47a1
    style LANE2 fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20
    style LANE3 fill:#fff3e0,stroke:#ef6c00,color:#e65100
    style LANE4 fill:#f3e5f5,stroke:#6a1b9a,color:#4a148c
    style LANE5 fill:#fafafa,stroke:#424242,color:#212121
```

### 1.0.1 横向版（LR，适合宽屏）

```mermaid
flowchart LR
    CLIENT["🖥  Frontend"]:::ext
    subgraph LANE1["L1 API"]
        L1N["chat · middleware"]
    end
    subgraph LANE2["L2 Scenarios"]
        L2N["router · injector · registry · loader"]
    end
    subgraph LANE3["L3 Skill + AUIP"]
        L3N["SuspendableScheduler + skill + auip + turn"]
    end
    subgraph LANE4["L4 Providers"]
        L4N["launcher + bridge + adapters"]
    end
    ENG["⚙  Engines"]:::ext
    L5["L5 Infra · policy + store + sandbox"]:::infra
    WORK["📂  work/"]:::data

    CLIENT ==> L1N
    L1N ==> L2N
    L2N ==> L3N
    L3N ==> L4N
    L4N ==> ENG
    L1N -.-> L5
    L2N -.-> L5
    L3N -.-> L5
    L4N -.-> L5
    WORK -.-> L2N
    WORK -.-> L3N

    classDef ext fill:#eceff1,stroke:#37474f,color:#263238
    classDef data fill:#fce4ec,stroke:#ad1457,color:#880e4f
    classDef infra fill:#fafafa,stroke:#424242,color:#212121
    style LANE1 fill:#e3f2fd,stroke:#1565c0,color:#0d47a1
    style LANE2 fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20
    style LANE3 fill:#fff3e0,stroke:#ef6c00,color:#e65100
    style LANE4 fill:#f3e5f5,stroke:#6a1b9a,color:#4a148c
```

### 1.1 反向依赖约束（CI 强校验）

```mermaid
flowchart LR
    L1["L1 API"]:::ok --> L2["L2 Scenarios"]:::ok
    L2 --> L3["L3 Skill/AUIP/Core"]:::ok
    L3 --> L4["L4 Providers"]:::ok
    L4 --> L5["L5 Policy/Store"]:::ok
    L3 --> L5
    L1 -.->|FORBIDDEN| L3:::forbid
    L1 -.->|FORBIDDEN| L4:::forbid
    L1 -.->|FORBIDDEN| L5:::forbid
    L2 -.->|FORBIDDEN| L4:::forbid
    L2 -.->|FORBIDDEN| L5:::forbid
    L3 -.->|FORBIDDEN| L1:::forbid
    L3 -.->|FORBIDDEN| L2:::forbid
    L4 -.->|FORBIDDEN| L1:::forbid
    L4 -.->|FORBIDDEN| L2:::forbid
    L4 -.->|FORBIDDEN| L3:::forbid
    L5 -.->|FORBIDDEN| L1:::forbid
    L5 -.->|FORBIDDEN| L2:::forbid
    L5 -.->|FORBIDDEN| L3:::forbid
    L5 -.->|FORBIDDEN| L4:::forbid
    classDef ok fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20;
    classDef forbid fill:#ffebee,stroke:#c62828,color:#b71c1c;
```

---

## 2. 统一对话入口（绝对约束）

> **仅 2 个端点** 都在 `api/controllers/chat_controller.py`，Scenario 路由发生在入口**前**。

```mermaid
flowchart LR
    REQ(["HTTP Request<br/>body.scenario?<br/>X-Scenario?<br/>keyword?"])

    REQ --> CHAT_SYNC["POST /agent/chat<br/>(同步 JSON)"]
    REQ --> CHAT_SSE["POST /agent/chat/stream<br/>(SSE)"]

    subgraph FORBID["❌ 严禁新增 (CI 拦截)"]
        F1["POST /agent/scenarios/{name}/chat"]
        F2["POST /agent/scenarios/{name}/chat/stream"]
        F3["任何 controller 另起的 chat handler"]
        F4["前端 send to scenario X 服务"]
    end

    CHAT_SYNC --> MW1["ScenarioMiddleware.route()<br/>(6 优先级)"]
    CHAT_SSE --> MW1
    MW1 --> SCN["ScenarioConfig"]
    SCN --> INJ1["ScenarioInjector"]
    INJ1 --> ADP1["SchedulerAdapter"]
    ADP1 --> SCHED["SuspendableScheduler<br/>or LegacyScheduler"]
    SCHED --> OUT1(["SSE: scenario → text → tool_use<br/>→ card → suspend → resume → done"])

    classDef bad fill:#fee,stroke:#d33,color:#900;
    class F1,F2,F3,F4 bad
```

---

## 3. 6 优先级路由（ScenarioRouter）

```mermaid
flowchart TB
    REQ(["Request"]) --> P1{"1. URL Path<br/>body.scenario"}
    P1 -- hit --> R1(["→ 命中 scenario"])
    P1 -- miss --> P2{"2. Header<br/>X-Scenario"}
    P2 -- hit --> R1
    P2 -- miss --> P3{"3. Body<br/>message 关键词"}
    P3 -- hit --> R1
    P3 -- miss --> P4{"4. body.scenario"}
    P4 -- hit --> R1
    P4 -- miss --> P5{"5. 意图分类<br/>(LlmIntentClassifier)"}
    P5 -- hit --> R1
    P5 -- miss --> P6["6. Default<br/>(最低 priority 的 _generic)"]
    P6 --> R1
```

---

## 4. HITL / A2UI 流转（SuspendableScheduler）

```mermaid
sequenceDiagram
    autonumber
    actor U as 用户
    participant FE as Frontend<br/>(AUIRenderer)
    participant API as chat_controller
    participant MW as ScenarioMiddleware
    participant INJ as ScenarioInjector
    participant SS as SuspendableScheduler
    participant ENG as Engine<br/>(opencode/claude_code)
    participant TURN as TurnStore
    participant CARD as Card YAML<br/>(work/.../cards/)

    U->>FE: 输入「订明天北京到上海机票」
    FE->>API: POST /agent/chat/stream
    API->>MW: route(headers, body)
    MW-->>API: ScenarioConfig(flight_booking)
    API->>INJ: inject(scenario, msg)
    INJ-->>API: InjectionResult(skills, tools, system_prompt)

    API->>SS: run_turn(scenario, injection)
    SS->>ENG: 启动 + 推 system_prompt
    ENG-->>SS: tool_use(ask_user, FLIGHT_LIST)
    SS->>CARD: 加载 FLIGHT_LIST.card.yaml
    SS-->>API: SSE event {type: card, card_type: FLIGHT_LIST}
    SS->>TURN: checkpoint(state=S05, turn_id)
    SS-->>API: SSE event {type: suspend, turn_id}
    API-->>FE: 结束本轮 SSE
    FE->>U: 渲染航班选择卡
    U->>FE: 选 CA1501
    FE->>API: POST /agent/turn/{id}/resume {flightId}
    API->>SS: resume(turn_id, payload)
    SS->>TURN: load checkpoint
    SS->>ENG: 续推选择结果
    ENG-->>SS: tool_use(ask_user, CABIN_LIST)
    SS-->>API: SSE card + suspend
    Note over SS,FE: ... 6 个挂起点 ...
    ENG-->>SS: 终态 ORDER_SUCCESS
    SS-->>API: SSE {type: card, ORDER_SUCCESS}
    SS-->>API: SSE {type: done}
    API-->>FE: 关闭 SSE
```

---

## 5. Scenario YAML → 5 维度配置

```mermaid
flowchart LR
    YAML["flight_booking.scenario.yaml"] --> RP["routing:<br/>keywords / priority"]
    YAML --> EX["execution:<br/>system_prompt · skills · tools<br/>orchestration: hitl"]
    YAML --> SEC["security:<br/>tool_level · allowed/denied<br/>network · max_turns/budget"]
    YAML --> WS["workspace:<br/>workspace_dirs · readonly<br/>deny_dirs · launcher"]
    YAML --> A2["a2ui:<br/>cards_dir · state_machine<br/>ask_user · renderer_hint"]
    YAML --> PS["progressive_skill:<br/>strategy · budget · load_on_state"]
    YAML --> RD["resource_dirs:<br/>prompts · skills · mcp · cards"]

    SEC --> POL_E["PolicyEngine"]
    WS --> LAUNCH["EngineLauncher.cwd"]
    A2 --> SUSP_E["SuspendableScheduler"]
    PS --> PROMPT["PromptBuilder"]
    EX --> INJ_E["ScenarioInjector"]
```

---

## 6. 渐进式 SKILL 加载（按 state）

```mermaid
flowchart TB
    INIT["Turn 启动"] --> INITSK["加载 initial_skills<br/>(book-flight#summary)"]
    INITSK --> STATE{"Current state?"}
    STATE -->|S01| NO["(无额外片段)"]
    STATE -->|S02| S02["加载 state-s02.md<br/>城市+日期提示"]
    STATE -->|S05| S05["加载 state-s05.md<br/>+ cabin-rules.md"]
    STATE -->|S11| S11["加载 state-s11.md<br/>差标决策"]
    NO --> BUDGET
    S02 --> BUDGET
    S05 --> BUDGET
    S11 --> BUDGET
    BUDGET{"Σ tokens > budget?"}
    BUDGET -- "policy=error" --> ERR["抛 SkillBudgetExceeded<br/>(code: SKILL_BUDGET_EXCEEDED)"]
    BUDGET -- "policy=truncate" --> TR["截断最后片段"]
    BUDGET -- "policy=warn" --> LOG["warn 日志 + 继续"]
    TR --> BUILD["PromptBuilder 拼装"]
    LOG --> BUILD
    BUILD --> NEXT["送入 Engine 推理"]
```

---

## 7. work/ 资源目录布局

```mermaid
graph TB
    ROOT["work/ (AGENT_SCHEDULER_WORK_ROOT)"]
    ROOT --> TEN["tenants/{tenant_id}/projects/{project_id}/<br/>PROJECT_DIR = workspace_dirs[0]"]
    ROOT --> SCN["scenarios/"]
    ROOT --> SHARED["shared/<br/>skills · mcp · prompts · docs"]
    ROOT --> CACHE["cache/<br/>opencode-configs/ · claude-configs/"]
    ROOT --> LOGS["logs/<br/>audit/ · routing/ · scenario/"]
    ROOT --> ARCH["archive/"]

    SCN --> S_DEF["_default.scenario.yaml"]
    SCN --> S_GEN["_generic.scenario.yaml (兜底)"]
    SCN --> S_FB["flight_booking.scenario.yaml"]
    SCN --> S_EA["expense_audit.scenario.yaml"]
    SCN --> S_CS["customer_service.scenario.yaml"]
    SCN --> S_CR["code_review.scenario.yaml"]

    S_FB --> FB_DIR["flight_booking/"]
    FB_DIR --> FB_P["prompts/"]
    FB_DIR --> FB_S["skills/book-flight/<br/>SKILL.md + fragments/"]
    FB_DIR --> FB_M["mcp/domestic-booking/"]
    FB_DIR --> FB_C["cards/*.card.yaml<br/>(8 个业务卡 + 1 chat fallback)"]
    FB_DIR --> FB_T["tests/playbook_*.yaml"]
```

---

## 8. 5 场景 × 5 维度速览

```mermaid
graph LR
    subgraph ROW1["安全档 tool_level"]
        G1["_generic: safe"]
        G2["_default: safe"]
        G3["flight_booking: standard"]
        G4["expense_audit: standard"]
        G5["customer_service: safe"]
        G6["code_review: standard"]
    end
    subgraph ROW2["编排 orchestration"]
        O1["single"] --- O2["single"] --- O3["hitl"] --- O4["parallel"] --- O5["hitl"] --- O6["delegate"]
    end
    subgraph ROW3["A2UI 卡片"]
        A1["off"] --- A2["off"] --- A3["8 cards"] --- A4["off"] --- A5["2 cards"] --- A6["off"]
    end
    subgraph ROW4["渐进式 SKILL"]
        P1["none"] --- P2["none"] --- P3["on_demand 4k"] --- P4["all 6k"] --- P5["on_demand 2k"] --- P6["all 6k"]
    end
    subgraph ROW5["cwd 策略"]
        W1["ro"] --- W2["ro"] --- W3["rw"] --- W4["rw"] --- W5["受限 rw"] --- W6["rw"]
    end
```

---

## 阅读指南

| 图 | 看什么 | 出问题找谁 |
|---|---|---|
| §1 总体 | 5 层边界 + 反向 import 约束 | 跨层调用先查这里 |
| §2 统一入口 | 唯一 2 个 chat 端点 | 想加 scenario URL → 删 |
| §3 6 优先级 | 路由命中顺序 | 关键词没命中 → 看这里 |
| §4 HITL 时序 | Card + suspend + resume 全链路 | 状态机卡住 → 走读时序 |
| §5 YAML 字段 | 5 个新增块来源 | 配置缺字段 → 对照 §5.1 |
| §6 渐进式 | budget 强制点 | 加载报错 → 看 policy |
| §7 资源布局 | work/ 子目录 | 文件该放哪 → 看这里 |
| §8 5×5 对比 | 5 场景速查 | "X 场景能不能做 Y" → 看这里 |
