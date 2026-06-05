# OpenCode 对话流程时序图

> **⚠️ 已废弃（2026-06-05）**
>
> 本文档对应的是 **Scenario 编排层接入前** 的旧版流程（仅含 `Scheduler` + `AgentPool` + `SessionManager`）。
> 不再反映当前架构 — 当前架构在 5 层框架下增加了：
> - L2 `ScenarioMiddleware` + `ScenarioRouter` + `ScenarioInjector` + `SchedulerAdapter`
> - L3 `SuspendableScheduler`（HITL 中断/恢复）+ `skill_runtime` + `auip` + `turn_store`
> - L4 `EngineLauncher`（`cwd = ${PROJECT_DIR}` 强制）
> - 统一 chat 入口（仅 `POST /agent/chat` 与 `/agent/chat/stream`）
>
> **最新文档** → [`docs/architecture-and-flow.md`](./architecture-and-flow.md)
> **历史归档** → 保留本文作 2026-05 版本参考，不要再基于此文档做新设计。
>
> ---

# OpenCode 对话流程时序图（旧版，仅供历史）

## 1. 主对话流程

```mermaid
sequenceDiagram
    actor User
    participant API as "API Route"
    participant Scheduler
    participant Pool as "AgentPoolManager"
    participant SessionMgr as "SessionManager"
    participant SDK as "AsyncOpencode"
    participant Agent as "AgentInstance"

    User->>API: POST /agent/chat
    activate API

    API->>Scheduler: run(message, agent_name, model, timeout)
    activate Scheduler

    alt Acquire Agent
        Scheduler->>Pool: acquire_idle_instance(agent_name)
        activate Pool

        Pool->>Pool: Find IDLE AgentInstance
        alt Found
            Pool->>Agent: status = BUSY
            activate Agent
            Pool-->>Scheduler: AgentInstance
        else No Idle
            Pool-->>Scheduler: NoIdleAgentError
            Scheduler-->>API: error
            API-->>User: error response
        end
        deactivate Pool
    end

    alt Create Session
        Scheduler->>SessionMgr: create(agent_name, model, system_prompt)
        activate SessionMgr

        SessionMgr->>SDK: client.session.create()
        activate SDK

        SDK->>Agent: HTTP POST /session/create
        activate Agent

        Agent-->>SDK: session_id
        deactivate Agent

        SDK-->>SessionMgr: session_id
        deactivate SDK

        SessionMgr-->>Scheduler: session_id
        deactivate SessionMgr
    end

    alt Send Message
        Scheduler->>SessionMgr: chat(session_id, message, timeout)
        activate SessionMgr

        SessionMgr->>SDK: client.session.chat(session_id, parts, timeout)
        activate SDK

        SDK->>Agent: HTTP POST /session/{session_id}/chat
        activate Agent

        loop LLM Processing
            Agent->>Agent: inference
        end

        Agent-->>SDK: response
        deactivate Agent

        SDK-->>SessionMgr: result
        deactivate SDK

        SessionMgr-->>Scheduler: result
        deactivate SessionMgr
    end

    alt Release Agent
        Scheduler->>Pool: release(instance_name)
        activate Pool

        Pool->>Agent: status = IDLE
        deactivate Pool
    end

    Scheduler-->>API: TaskResult
    deactivate Scheduler

    API-->>User: ChatResponse
    deactivate API
```

## 2. 流式对话流程

```mermaid
sequenceDiagram
    actor User
    participant StreamAPI as "API Route (Stream)"
    participant SessionMgr as "SessionManager"
    participant StreamClient as "AsyncOpencode (Streaming)"
    participant Agent as "AgentInstance"

    User->>StreamAPI: POST /agent/chat/stream
    activate StreamAPI

    StreamAPI->>SessionMgr: chat_stream(session_id, message, timeout)
    activate SessionMgr

    SessionMgr->>StreamClient: with_streaming_response.chat(session_id, parts)
    activate StreamClient

    StreamClient->>Agent: HTTP POST /session/{session_id}/chat (streaming)
    activate Agent

    loop SSE Events
        Agent-->>StreamClient: event: session
        StreamClient-->>StreamAPI: session_id event

        loop text chunks
            Agent-->>StreamClient: event: text
            StreamClient-->>StreamAPI: text event
        end

        alt has reasoning
            Agent-->>StreamClient: event: reasoning
            StreamClient-->>StreamAPI: reasoning event
        end
    end

    Agent-->>StreamClient: event: done
    deactivate Agent

    StreamClient-->>SessionMgr: complete
    deactivate StreamClient

    SessionMgr-->>StreamAPI: complete
    deactivate SessionMgr

    StreamAPI-->>User: SSE stream end
    deactivate StreamAPI
```

## 3. 核心组件架构

```mermaid
graph TB
    subgraph "Sanic App"
        Main[main.py]
        App[app.py]
    end

    subgraph "API Layer"
        Routes[routes.py]
    end

    subgraph "Core Components"
        Scheduler[scheduler.py]
        SessionMgr[session.py]
        PoolMgr[agent_pool.py]
    end

    subgraph "External"
        SDK[AsyncOpencode SDK]
        Serve[opencode serve]
    end

    Main-->App
    App-->Routes
    App-->Scheduler
    App-->SessionMgr
    App-->PoolMgr

    Routes-->Scheduler
    Scheduler-->PoolMgr
    Scheduler-->SessionMgr
    SessionMgr-->SDK
    SDK-->Serve
```

## 4. 完整流程图

```mermaid
flowchart TD
    A[User Request] --> B{Choose Mode}

    B -->|Single| C[POST /agent/chat]
    B -->|Streaming| D[POST /agent/chat/stream]

    C --> E[Scheduler.run]
    D --> F[SessionManager.chat_stream]

    E --> G[AgentPoolManager.acquire_idle_instance]
    F --> G

    G --> H{Agent Available?}
    H -->|Yes| I[Get AgentInstance]
    H -->|No| J[Return Error]

    I --> K[SessionManager.create]
    K --> L[AsyncOpencode.session.create]
    L --> M[opencode serve /session/create]
    M --> N[Return session_id]

    N --> O[SessionManager.chat]
    O --> P[AsyncOpencode.session.chat]
    P --> Q[opencode serve /session/chat]
    Q --> R[LLM Processing]
    R --> S[Return Response]

    S --> T[AgentPoolManager.release]
    T --> U[status = IDLE]

    O --> V[Return TaskResult]
    V --> W[API Response]

    U --> W
    J --> W

    W --> X[User Gets Response]
```
