# 基于 OpenCode 的差旅 Agent 技术演示

## 0. 技术定位

当前项目是一个 **基于开源 Agent OpenCode 的差旅 Agent**，核心落地场景为国内机票查询与预订：`fh_domestic_flight_booking`。

项目没有重新实现 Agent Runtime，也没有把差旅流程硬编码进 Agent 核心，而是采用分层协议化架构：

```text
用户
  ↓
前端 Chat / 动态 UI
  ↓  SSE / AGUI(AUIP) card event
OpenAgent Hub
  ↓
OpenCode Agent Runtime
  ↓
Skill: fh-domestic-flight-booking
  ↓
MCP Tools: feihe-travel_*
  ↓
fh-travel Java MCP 服务 / 订票状态机 / 业务系统
```

<div align="center">
<svg width="980" height="430" viewBox="0 0 980 430" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="差旅 Agent 总体轻量架构">
  <defs>
    <linearGradient id="gBlue" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#2563eb"/>
      <stop offset="100%" stop-color="#0f766e"/>
    </linearGradient>
    <linearGradient id="gSlate" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0f172a"/>
      <stop offset="100%" stop-color="#334155"/>
    </linearGradient>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="8" stdDeviation="8" flood-color="#0f172a" flood-opacity="0.16"/>
    </filter>
    <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L0,6 L9,3 z" fill="#64748b"/>
    </marker>
  </defs>

  <rect x="0" y="0" width="980" height="430" rx="24" fill="#f8fafc"/>
  <text x="490" y="42" text-anchor="middle" font-family="Arial, sans-serif" font-size="22" font-weight="700" fill="#0f172a">差旅 Agent 轻量化分层架构</text>
  <text x="490" y="70" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="#64748b">OpenCode 负责 Agent Runtime，差旅能力通过 Skill + MCP + AGUI 协议插入</text>

  <g filter="url(#shadow)">
    <rect x="40" y="120" width="130" height="74" rx="16" fill="#ffffff" stroke="#dbeafe"/>
    <text x="105" y="150" text-anchor="middle" font-family="Arial, sans-serif" font-size="16" font-weight="700" fill="#1e3a8a">用户</text>
    <text x="105" y="174" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#64748b">自然语言需求</text>
  </g>

  <g filter="url(#shadow)">
    <rect x="220" y="105" width="150" height="104" rx="16" fill="#ffffff" stroke="#bfdbfe"/>
    <text x="295" y="138" text-anchor="middle" font-family="Arial, sans-serif" font-size="16" font-weight="700" fill="#1d4ed8">前端</text>
    <text x="295" y="164" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#64748b">Chat</text>
    <text x="295" y="184" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#64748b">FlightResultCard</text>
  </g>

  <g filter="url(#shadow)">
    <rect x="420" y="92" width="165" height="130" rx="18" fill="#ffffff" stroke="#99f6e4"/>
    <text x="502" y="126" text-anchor="middle" font-family="Arial, sans-serif" font-size="16" font-weight="700" fill="#0f766e">OpenAgent Hub</text>
    <text x="502" y="154" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#475569">Scenario Router</text>
    <text x="502" y="174" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#475569">SSE StreamEvent</text>
    <text x="502" y="194" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#475569">AGUI/AUIP Card</text>
  </g>

  <g filter="url(#shadow)">
    <rect x="640" y="80" width="150" height="154" rx="18" fill="url(#gBlue)"/>
    <text x="715" y="116" text-anchor="middle" font-family="Arial, sans-serif" font-size="17" font-weight="700" fill="#ffffff">OpenCode</text>
    <text x="715" y="143" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#dbeafe">Agent Runtime</text>
    <text x="715" y="164" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#dbeafe">Skill Loader</text>
    <text x="715" y="185" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#dbeafe">MCP Tool Use</text>
    <text x="715" y="206" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#dbeafe">Event Stream</text>
  </g>

  <g filter="url(#shadow)">
    <rect x="835" y="105" width="115" height="104" rx="16" fill="#ffffff" stroke="#c4b5fd"/>
    <text x="892" y="138" text-anchor="middle" font-family="Arial, sans-serif" font-size="16" font-weight="700" fill="#5b21b6">LLM</text>
    <text x="892" y="164" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#64748b">OpenAI</text>
    <text x="892" y="184" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#64748b">Compatible</text>
  </g>

  <g filter="url(#shadow)">
    <rect x="420" y="282" width="165" height="95" rx="18" fill="#ecfeff" stroke="#67e8f9"/>
    <text x="502" y="315" text-anchor="middle" font-family="Arial, sans-serif" font-size="16" font-weight="700" fill="#155e75">Skill</text>
    <text x="502" y="342" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#475569">fh-domestic-flight-booking</text>
    <text x="502" y="362" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#475569">状态机 / Tool Contract</text>
  </g>

  <g filter="url(#shadow)">
    <rect x="640" y="282" width="150" height="95" rx="18" fill="#fff7ed" stroke="#fed7aa"/>
    <text x="715" y="315" text-anchor="middle" font-family="Arial, sans-serif" font-size="16" font-weight="700" fill="#9a3412">MCP Tools</text>
    <text x="715" y="342" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#475569">feihe-travel_*</text>
    <text x="715" y="362" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#475569">query / choose / preview</text>
  </g>

  <g filter="url(#shadow)">
    <rect x="835" y="282" width="115" height="95" rx="18" fill="url(#gSlate)"/>
    <text x="892" y="313" text-anchor="middle" font-family="Arial, sans-serif" font-size="15" font-weight="700" fill="#ffffff">Java Runtime</text>
    <text x="892" y="340" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#cbd5e1">状态 / 政策</text>
    <text x="892" y="360" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#cbd5e1">订单预览</text>
  </g>

  <path d="M170 157 H220" stroke="#64748b" stroke-width="2" marker-end="url(#arrow)"/>
  <path d="M370 157 H420" stroke="#64748b" stroke-width="2" marker-end="url(#arrow)"/>
  <path d="M585 157 H640" stroke="#64748b" stroke-width="2" marker-end="url(#arrow)"/>
  <path d="M790 157 H835" stroke="#64748b" stroke-width="2" marker-end="url(#arrow)"/>
  <path d="M715 234 V282" stroke="#64748b" stroke-width="2" marker-end="url(#arrow)"/>
  <path d="M585 330 H640" stroke="#64748b" stroke-width="2" marker-end="url(#arrow)"/>
  <path d="M790 330 H835" stroke="#64748b" stroke-width="2" marker-end="url(#arrow)"/>
  <path d="M502 282 V222" stroke="#64748b" stroke-width="2" marker-end="url(#arrow)"/>

  <text x="195" y="145" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" fill="#64748b">请求</text>
  <text x="395" y="145" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" fill="#64748b">SSE</text>
  <text x="612" y="145" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" fill="#64748b">Bridge</text>
  <text x="812" y="145" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" fill="#64748b">Prompt</text>
  <text x="610" y="318" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" fill="#64748b">Tool Contract</text>
  <text x="812" y="318" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" fill="#64748b">业务事实</text>
</svg>
</div>

核心分工：

- **OpenCode**：Agent Runtime、模型接入、Tool 调用、Skill 加载、事件流。
- **OpenAgent Hub**：场景路由、OpenCode 事件映射、SSE 输出、AGUI/AUIP 卡片转换。
- **Skill**：业务流程约束、状态机、Tool Contract、轻量脚本、交互协议说明。
- **MCP**：真实差旅业务能力调用。
- **Java booking runtime**：Redis 上下文、状态流转、政策校验、订单预览等权威业务逻辑。
- **前端**：按 `card_type` 和协议字段渲染动态 UI。

---

## 1. 底座选型：基于 OpenCode 的开源架构

### 1.1 当前采用 OpenCode Agent 作为底座

当前项目直接使用 **OpenCode Agent** 作为执行底座，复用其原生能力：

- 模型 Provider 配置。
- MCP Tool 调用。
- Skill 加载。
- Tool Use / Tool Result 事件。
- 本地 MCP Server 与远程 MCP Server。
- Agent 会话与流式输出。

项目通过 Python Hub 侧动态渲染 OpenCode 配置，将业务 Skill 和 MCP Server 注入 OpenCode Runtime。

Skill 挂载逻辑位于 `docker/render_config.py`：

```python
def _build_skills_block(skills: list[str], workspace_cwd: str) -> dict:
    paths = [f"{workspace_cwd}/.skills/{name}" for name in skills]
    return {"skills": {"paths": paths}}
```

差旅 MCP Server 注册逻辑同样位于 `docker/render_config.py`：

```python
def _flight_mcp_server_from_env() -> dict | None:
    return {
        "type": "remote",
        "url": endpoint,
        "headers": {
            "Accept": "application/json,text/event-stream",
            header_name: _flight_auth_header_value(header_name),
        },
        "oauth": False,
        "enabled": True,
        "timeout": int(os.environ.get("FLIGHT_MCP_TIMEOUT_MS", "30000")),
    }
```

最终运行时会注册：

```text
feihe-travel
  type: remote
  url: https://traveldev.feiheair.com/api/mcp
  headers:
    token: {env:FLIGHT_API_KEY}
```

### 1.2 Python SDK / Python Hub 支撑

当前项目以 Python 服务作为 OpenAgent Hub，对外提供 Chat API、SSE 流、场景路由、AGUI/AUIP 卡片转换等能力，并承接 OpenCode Runtime 的事件流。

关键模块：

| 模块 | 作用 |
| --- | --- |
| `src/openagent/api/controllers/chat_controller.py` | Chat API、SSE、`ask_user` 拦截为 Card |
| `src/openagent/providers/opencode_chat.py` | OpenCode 流式事件处理、Tool Result 兜底卡片组装 |
| `src/openagent/auip/cards.py` | AGUI/AUIP Card 协议模型 |
| `src/openagent/auip/flight_card.py` | 将航班 MCP 原始结果转换为 `FLIGHT_RESULT` 卡片 |
| `docker/render_config.py` | 渲染 OpenCode MCP、Skill、Provider 配置 |

### 1.3 技术落地优势

| 维度 | 当前实现 |
| --- | --- |
| Agent Runtime | 复用 OpenCode，不自研执行框架 |
| Tool 调用 | 复用 OpenCode 原生 MCP Tool |
| Skill 加载 | 通过 OpenCode `skills.paths` 注入 |
| 模型接入 | 通过 OpenCode Provider 配置接入 OpenAI-compatible / Anthropic 等 |
| 鉴权 | 容器环境变量 `FLIGHT_API_KEY` + OpenCode MCP headers |
| 事件流 | OpenCode 事件映射为项目内部 `StreamEvent` |
| 业务开发重心 | 差旅 Skill、MCP 契约、AGUI/AUIP 卡片协议 |

工程结果：

- Agent 底层能力跟随 OpenCode 社区演进。
- 开发侧不重复实现 Agent 调度、Tool 调用、Skill 加载、模型事件流。
- 差旅业务不侵入 OpenCode 核心。
- 上层应用可以聚焦流程编排、协议设计和业务 Tool Contract。

---

## 2. 开发范式：MCP、Skill 与 AGUI 协议约束

> 当前代码中协议目录和配置使用 `auip` 命名，场景配置中为 `a2ui.protocol: auip`。本文将其作为当前项目 AGUI 动态 UI 协议的实际落地形态说明。

### 2.1 三层协议约束

```text
MCP
  约束 Agent 能调用什么业务能力，以及每个工具的输入输出边界

Skill
  约束 Agent 在什么阶段调用什么工具、如何组织流程、何时询问用户

AGUI / AUIP
  约束 Agent 与前端之间如何传递结构化 UI 交互
```

<div align="center">
<svg width="980" height="360" viewBox="0 0 980 360" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="MCP Skill AGUI 三层协议约束">
  <defs>
    <filter id="protoShadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="7" stdDeviation="7" flood-color="#0f172a" flood-opacity="0.14"/>
    </filter>
    <marker id="protoArrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L0,6 L9,3 z" fill="#475569"/>
    </marker>
  </defs>

  <rect x="0" y="0" width="980" height="360" rx="24" fill="#f8fafc"/>
  <text x="490" y="42" text-anchor="middle" font-family="Arial, sans-serif" font-size="22" font-weight="700" fill="#0f172a">协议约束下的开发范式</text>
  <text x="490" y="68" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="#64748b">不同差旅场景通过 Skill 插拔；Agent Core 不进入业务分支</text>

  <g filter="url(#protoShadow)">
    <rect x="70" y="118" width="230" height="142" rx="22" fill="#eff6ff" stroke="#93c5fd"/>
    <text x="185" y="152" text-anchor="middle" font-family="Arial, sans-serif" font-size="21" font-weight="700" fill="#1d4ed8">MCP</text>
    <text x="185" y="180" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="#334155">业务工具协议</text>
    <line x1="105" y1="195" x2="265" y2="195" stroke="#bfdbfe"/>
    <text x="185" y="220" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#475569">queryFlightBasic</text>
    <text x="185" y="240" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#475569">chooseFlight / chooseCabin</text>
  </g>

  <g filter="url(#protoShadow)">
    <rect x="375" y="92" width="230" height="194" rx="22" fill="#ecfeff" stroke="#67e8f9"/>
    <text x="490" y="128" text-anchor="middle" font-family="Arial, sans-serif" font-size="21" font-weight="700" fill="#0f766e">Skill</text>
    <text x="490" y="156" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="#334155">流程与状态协议</text>
    <line x1="410" y1="172" x2="570" y2="172" stroke="#a5f3fc"/>
    <text x="490" y="197" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#475569">state-machine.json</text>
    <text x="490" y="217" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#475569">tool-contracts.json</text>
    <text x="490" y="237" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#475569">normalize / stage_guard</text>
    <text x="490" y="257" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#475569">workflows/*.md</text>
  </g>

  <g filter="url(#protoShadow)">
    <rect x="680" y="118" width="230" height="142" rx="22" fill="#f5f3ff" stroke="#c4b5fd"/>
    <text x="795" y="152" text-anchor="middle" font-family="Arial, sans-serif" font-size="21" font-weight="700" fill="#6d28d9">AGUI / AUIP</text>
    <text x="795" y="180" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="#334155">动态 UI 协议</text>
    <line x1="715" y1="195" x2="875" y2="195" stroke="#ddd6fe"/>
    <text x="795" y="220" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#475569">card_type 白名单</text>
    <text x="795" y="240" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#475569">fields / body / actions</text>
  </g>

  <path d="M300 189 H375" stroke="#475569" stroke-width="2.2" marker-end="url(#protoArrow)"/>
  <path d="M605 189 H680" stroke="#475569" stroke-width="2.2" marker-end="url(#protoArrow)"/>

  <rect x="150" y="306" width="680" height="34" rx="17" fill="#ffffff" stroke="#e2e8f0"/>
  <text x="490" y="328" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" font-weight="700" fill="#0f172a">开发新差旅场景 = 新 Skill + 新 Tool Contract + 新 Card Schema；OpenCode Core 不改</text>
</svg>
</div>

### 2.2 MCP：业务能力接口层

当前国内机票场景在 `work/scenarios/fh_domestic_flight_booking.scenario.yaml` 中显式声明可用工具。

核心 MCP Tool：

| 阶段 | Tool | 作用 |
| --- | --- | --- |
| 权限 | `checkProductAccess` | 检查产品权限 |
| 查询 | `queryFlightBasic` / `feihe-travel_queryFlightBasic` | 查询航班 |
| 过滤 | `filterFlightList` / `feihe-travel_filterFlightList` | 过滤已加载航班列表 |
| 选航班 | `chooseFlight` / `feihe-travel_chooseFlight` | 选择航班 |
| 政策 | `getFlightPolicyInfo` / `feihe-travel_getFlightPolicyInfo` | 获取政策信息 |
| 选舱 | `chooseCabin` / `feihe-travel_chooseCabin` | 选择舱位 |
| 乘机人 | `fillPassenger` / `feihe-travel_fillPassenger` | 填写乘机人 |
| 出差单 | `listTripApplications`, `getTripApplicationDetail` | 出差申请单选择与详情 |
| 成本中心 | `listCostCenters`, `bindCostCenter` | 成本中心查询与绑定 |
| 联系人 | `getDefaultContact` | 默认联系人 |
| 校验 | `validateBookingInfo` | 预订信息校验 |
| 政策决策 | `recordPolicyUserDecision` | 记录用户超规决策 |
| 预览 | `buildOrderPreview` | 构建订单预览 |
| 恢复 | `resetBookingSession` | 重置异常会话 |

MCP 是业务事实来源。Agent 和 Skill 不编造：

- 航班号。
- 价格。
- 舱位。
- 政策结果。
- 乘机人。
- 出差单。
- 成本中心。
- 订单状态。

### 2.3 Skill：流程与策略层

核心 Skill 位于：

```text
work/shared/skills/fh-domestic-flight-booking/
```

关键文件：

| 文件 | 作用 |
| --- | --- |
| `SKILL.md` | Skill 总入口，定义目的、流程、约束、AGUI/AUIP 卡片规则 |
| `schemas/tool-contracts.json` | MCP Tool 调用契约 |
| `schemas/state-machine.json` | 订票状态机 |
| `schemas/booking-plan.schema.json` | 归一化预订计划结构 |
| `schemas/compact-flight.schema.json` | 紧凑航班输出结构 |
| `scripts/normalize_request.py` | 日期、枚举、输入计划归一化 |
| `scripts/stage_guard.py` | 根据阶段检查工具调用是否合法 |
| `scripts/compact_mcp_payload.py` | 压缩 MCP 大结果，减少模型负担 |
| `scripts/render_options.py` | 渲染紧凑选项 |
| `workflows/*.md` | 查询、主预订、往返、政策恢复流程说明 |

Skill 明确保持薄层：

```text
Keep this skill thin: it sequences MCP calls, normalizes inputs,
compacts outputs, and loads detailed guidance only when needed.
Do not reimplement Java services, TMS adapters, Redis context,
policy logic, or order creation inside the skill.
```

即 Skill 只负责：

- 编排调用顺序。
- 约束阶段流转。
- 归一化输入。
- 压缩输出。
- 指导 Agent 何时发起用户交互。

Skill 不负责：

- 航班搜索。
- 票价计算。
- 差标政策判断。
- Redis 订票上下文。
- 订单创建。
- 订单预览幂等。

### 2.4 AGUI/AUIP：前后端交互协议层

当前场景启用了 AUIP：

```yaml
a2ui:
  enabled: true
  protocol: auip
  state_machine: ${WORK_SHARED}/skills/fh-domestic-flight-booking/schemas/state-machine.json
  default_card_timeout: 600
  ask_user:
    tool_name: ask_user
    schema: ${SCENARIO_DIR}/ask_user.schema.json
  renderer_hint: react_aui_v1
  progressive_loading: true
```

卡片类型白名单：

```yaml
card_schemas:
  - OD_INPUT
  - FLIGHT_RESULT
  - FLIGHT_LIST
  - CABIN_LIST
  - PASSENGER_FORM
  - OAT_BINDING
  - PRICE_VERIFY
  - POLICY_DECISION
  - ORDER_CONFIRM
  - ORDER_SUCCESS
  - CANNOT_ORDER
  - CHAT_FALLBACK
```

前后端不是靠自然语言猜测 UI，而是靠：

```text
event.type = card
event.data.card_type = <CardType>
event.data.card = <Schema-constrained payload>
```

进行渲染。

### 2.5 解耦效果

当前扩展方式：

```text
新增差旅场景
  ↓
新增或复用 Skill
  ↓
声明 MCP Tool Contract
  ↓
声明 AGUI/AUIP Card Schema
  ↓
场景路由绑定
```

开发者无需进入 OpenCode Agent Core 修改调度逻辑。面对不同差旅流程，只需要开发或调度对应 Skill，实现即插即用。

---

## 3. 前后端交互：AGUI 协议与动态 UI

### 3.1 当前交互链路

标准卡片链路：

```text
LLM / OpenCode Agent
  ↓ tool_use: ask_user(...)
OpenAgent Hub
  ↓ intercept
StreamEvent.card(...)
  ↓ SSE
Frontend
  ↓
按 card_type 渲染对应组件
```

航班查询兜底链路：

```text
LLM / OpenCode Agent
  ↓ tool_use: feihe-travel_queryFlightBasic
MCP Server
  ↓ tool_result: flightList
OpenAgent Hub
  ↓ maybe_assemble_flight_card(...)
StreamEvent.card(card_type=FLIGHT_RESULT)
  ↓ SSE
Frontend
  ↓
FlightResultCard
```

<div align="center">
<svg width="980" height="440" viewBox="0 0 980 440" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="AGUI 动态 UI 通信流程">
  <defs>
    <filter id="uiShadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="6" stdDeviation="7" flood-color="#0f172a" flood-opacity="0.14"/>
    </filter>
    <marker id="uiArrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L0,6 L9,3 z" fill="#475569"/>
    </marker>
    <linearGradient id="uiGreen" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#14b8a6"/>
      <stop offset="100%" stop-color="#2563eb"/>
    </linearGradient>
  </defs>

  <rect x="0" y="0" width="980" height="440" rx="24" fill="#f8fafc"/>
  <text x="490" y="40" text-anchor="middle" font-family="Arial, sans-serif" font-size="22" font-weight="700" fill="#0f172a">AGUI/AUIP 动态 UI 通信链路</text>
  <text x="490" y="66" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="#64748b">LLM 可以主动发 ask_user；Hub 也可以从航班 tool_result 自动组装 FLIGHT_RESULT</text>

  <g filter="url(#uiShadow)">
    <rect x="52" y="112" width="150" height="82" rx="18" fill="#ffffff" stroke="#bfdbfe"/>
    <text x="127" y="144" text-anchor="middle" font-family="Arial, sans-serif" font-size="16" font-weight="700" fill="#1d4ed8">OpenCode Agent</text>
    <text x="127" y="170" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#64748b">tool_use / tool_result</text>
  </g>

  <g filter="url(#uiShadow)">
    <rect x="292" y="90" width="180" height="126" rx="18" fill="#fff7ed" stroke="#fdba74"/>
    <text x="382" y="124" text-anchor="middle" font-family="Arial, sans-serif" font-size="16" font-weight="700" fill="#9a3412">路径 A</text>
    <text x="382" y="150" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="#334155">ask_user</text>
    <text x="382" y="176" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#64748b">card_type + fields/body</text>
    <text x="382" y="196" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#64748b">LLM 主动发卡</text>
  </g>

  <g filter="url(#uiShadow)">
    <rect x="292" y="258" width="180" height="126" rx="18" fill="#ecfeff" stroke="#67e8f9"/>
    <text x="382" y="292" text-anchor="middle" font-family="Arial, sans-serif" font-size="16" font-weight="700" fill="#0f766e">路径 B</text>
    <text x="382" y="318" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="#334155">queryFlightBasic</text>
    <text x="382" y="344" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#64748b">MCP 返回 flightList</text>
    <text x="382" y="364" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#64748b">Hub 兜底组装卡片</text>
  </g>

  <g filter="url(#uiShadow)">
    <rect x="560" y="112" width="170" height="250" rx="22" fill="url(#uiGreen)"/>
    <text x="645" y="150" text-anchor="middle" font-family="Arial, sans-serif" font-size="17" font-weight="700" fill="#ffffff">OpenAgent Hub</text>
    <line x1="592" y1="168" x2="698" y2="168" stroke="#bfdbfe" opacity="0.65"/>
    <text x="645" y="195" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#e0f2fe">_ask_user_to_card</text>
    <text x="645" y="218" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#e0f2fe">allowed_card_types</text>
    <text x="645" y="241" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#e0f2fe">maybe_assemble_flight_card</text>
    <text x="645" y="264" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#e0f2fe">session 去重</text>
    <text x="645" y="287" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#e0f2fe">StreamEvent.card</text>
    <text x="645" y="310" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#e0f2fe">SSE 输出</text>
  </g>

  <g filter="url(#uiShadow)">
    <rect x="805" y="112" width="130" height="250" rx="22" fill="#ffffff" stroke="#c4b5fd"/>
    <text x="870" y="150" text-anchor="middle" font-family="Arial, sans-serif" font-size="17" font-weight="700" fill="#6d28d9">前端</text>
    <line x1="830" y1="168" x2="910" y2="168" stroke="#ddd6fe"/>
    <text x="870" y="195" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#475569">card_type</text>
    <text x="870" y="218" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#475569">FLIGHT_RESULT</text>
    <text x="870" y="241" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#475569">FlightResultCard</text>
    <text x="870" y="264" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#475569">CABIN_LIST</text>
    <text x="870" y="287" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#475569">ORDER_CONFIRM</text>
    <text x="870" y="310" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#475569">动态交互组件</text>
  </g>

  <path d="M202 153 H292" stroke="#475569" stroke-width="2" marker-end="url(#uiArrow)"/>
  <path d="M202 153 C242 153 242 321 292 321" fill="none" stroke="#475569" stroke-width="2" marker-end="url(#uiArrow)"/>
  <path d="M472 153 H560" stroke="#475569" stroke-width="2" marker-end="url(#uiArrow)"/>
  <path d="M472 321 H560" stroke="#475569" stroke-width="2" marker-end="url(#uiArrow)"/>
  <path d="M730 237 H805" stroke="#475569" stroke-width="2" marker-end="url(#uiArrow)"/>

  <rect x="90" y="404" width="800" height="22" rx="11" fill="#ffffff" stroke="#e2e8f0"/>
  <text x="490" y="420" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#334155">前端只依赖协议字段渲染，不解析 MCP 原始 JSON，也不从自然语言中反推 UI</text>
</svg>
</div>

### 3.2 `ask_user` 转 Card

`src/openagent/api/controllers/chat_controller.py` 中的 `_ask_user_to_card` 会拦截 `tool_use`：

```python
def _ask_user_to_card(
    event: StreamEvent,
    *,
    allowed_card_types: set | None,
) -> StreamEvent:
    if event.type != "tool_use":
        return event

    data = event.data or {}
    tool_name = data.get("name") or data.get("tool_name")

    if tool_name != "ask_user":
        return event
```

读取 `card_type`：

```python
card_type = str(inp.get("card_type") or "CHAT_FALLBACK")
```

执行协议校验：

```python
if card_type not in CARD_TYPES_SET:
    return StreamEvent.error(..., code="CARD_TYPE_INVALID")

if allowed_card_types is not None and card_type not in allowed_card_types:
    return StreamEvent.error(..., code="CARD_TYPE_NOT_ALLOWED")
```

转换为 SSE card：

```python
return StreamEvent.card(
    card_id=card_id,
    card_type=card_type,
    card=card_payload,
    correlation_id=correlation_id,
)
```

该逻辑保证：

- Agent 不能发未知 UI 类型。
- 当前场景只能发白名单内卡片。
- 前端收到结构化 `card` 事件，而不是 Markdown 文本。

### 3.3 Card 数据模型

`src/openagent/auip/cards.py` 定义 Card 类型：

```python
class CardType(str, Enum):
    CHAT_FALLBACK = "CHAT_FALLBACK"
    OD_INPUT = "OD_INPUT"
    FLIGHT_RESULT = "FLIGHT_RESULT"
    FLIGHT_LIST = "FLIGHT_LIST"
    CABIN_LIST = "CABIN_LIST"
    PASSENGER_FORM = "PASSENGER_FORM"
    OAT_BINDING = "OAT_BINDING"
    PRICE_VERIFY = "PRICE_VERIFY"
    POLICY_DECISION = "POLICY_DECISION"
    ORDER_CONFIRM = "ORDER_CONFIRM"
    ORDER_SUCCESS = "ORDER_SUCCESS"
    CANNOT_ORDER = "CANNOT_ORDER"
    QUESTION = "QUESTION"
    TODO_LIST = "TODO_LIST"
```

核心字段：

| 字段 | 说明 |
| --- | --- |
| `card_id` | 卡片唯一 ID |
| `card_type` | 卡片类型 |
| `schema_version` | 协议版本，当前默认 `1.0` |
| `title` | 标题 |
| `body` | 复杂主体数据 |
| `fields` | 表单字段 |
| `options` | 选项列表 |
| `actions` | 操作按钮 |
| `decision_buttons` | 决策按钮兼容字段 |
| `metadata` | 扩展元数据 |
| `dismissible` | 是否可关闭 |

### 3.4 场景级 Card Schema

国内机票场景卡片 schema：

```text
work/scenarios/fh_domestic_flight_booking/ask_user.schema.json
```

该 schema 明确规定 `card_type` 枚举和不同卡片的必填结构。

| Card Type | 必填结构 | 用途 |
| --- | --- | --- |
| `OD_INPUT` | `fields[]` | 缺少出发地、目的地、日期时补问 |
| `FLIGHT_RESULT` | `body.summary` + `body.plans[]` | 展示航班搜索结果 |
| `FLIGHT_LIST` | `flights[]` | 直接选择航班 |
| `CABIN_LIST` | `cabins[]` | 选择舱位 |
| `PASSENGER_FORM` | `fields[]` | 填乘机人 |
| `OAT_BINDING` | `fields[]` 或 `options[]` | 出差单、成本中心、联系人绑定 |
| `PRICE_VERIFY` | `current_price` | 价格变动确认 |
| `POLICY_DECISION` | `decision_buttons[]` 或 `actions[]` | 差标超规决策 |
| `ORDER_CONFIRM` | `order_summary` | 订单确认 |
| `ORDER_SUCCESS` | `order_no` 或 `order_summary` | 下单成功 |
| `CANNOT_ORDER` | `reason` + `fallback` | 无法继续 |
| `CHAT_FALLBACK` | `message` | 文本兜底 |

### 3.5 航班卡片：`FLIGHT_RESULT`

当前航班结果卡片协议结构：

```json
{
  "card_type": "FLIGHT_RESULT",
  "title": "机票已发送",
  "body": {
    "summary": {
      "totalCount": 196,
      "filteredCount": 196,
      "searchType": "全量查询",
      "depCity": "北京",
      "arrCity": "上海",
      "depDate": "2026-06-12"
    },
    "plans": [
      {
        "id": "fastest",
        "title": "最快抵达",
        "subtitle": "115分钟",
        "criteria": "duration",
        "flights": [
          {
            "flightId": "MF8561",
            "flightNo": "MF8561",
            "airline": {
              "code": "MF",
              "name": "厦门航空"
            },
            "departure": {
              "city": "北京",
              "airport": "大兴机场",
              "airportCode": "PKX",
              "time": "2026-06-12 07:50:00"
            },
            "arrival": {
              "city": "上海",
              "airport": "浦东机场",
              "airportCode": "PVG",
              "time": "2026-06-12 09:45:00"
            },
            "duration": "115分钟",
            "stops": 0,
            "cabin": "经济舱",
            "price": 400
          }
        ]
      }
    ]
  }
}
```

前端只需要判断：

```text
event.type == "card"
event.data.card_type == "FLIGHT_RESULT"
```

即可渲染航班卡片组件。

### 3.6 Hub 侧航班卡片兜底组装

部分模型可能不稳定遵守复杂 Prompt，不主动调用 `ask_user` 发卡片。当前实现增加了 Hub 兜底逻辑。

`src/openagent/providers/opencode_chat.py`：

```python
if (
    mapped.type == "tool_result"
    and mapped.data.get("tool_name") == "feihe-travel_queryFlightBasic"
):
    if session_id in _FLIGHT_CARD_EMITTED:
        continue

    from openagent.auip.flight_card import maybe_assemble_flight_card

    card = maybe_assemble_flight_card(
        tool_name=mapped.data["tool_name"],
        output=mapped.data.get("output"),
    )

    if card is not None:
        _FLIGHT_CARD_EMITTED.add(session_id)
        yield StreamEvent.card(
            card_id=card.card_id,
            card_type=card.card_type.value,
            card={"title": card.title, "body": card.body},
        )
        continue
```

触发条件：

- `tool_result.tool_name == "feihe-travel_queryFlightBasic"`。
- 工具输出可解析。
- 输出包含非空 `flightList`。
- 同一 session 未发过航班卡片。

### 3.7 `maybe_assemble_flight_card` 转换逻辑

实现位置：

```text
src/openagent/auip/flight_card.py
```

核心入口：

```python
def maybe_assemble_flight_card(tool_name: str, output: Any) -> Card | None:
    if tool_name != "feihe-travel_queryFlightBasic":
        return None

    data = _extract_data(output)
    if data is None:
        return None

    flight_list = data.get("flightList") or []
    if not isinstance(flight_list, list) or not flight_list:
        return None

    plans = _build_plans(flight_list, airway_names)

    return Card(
        card_id=f"card-{uuid.uuid4().hex[:12]}",
        card_type=CardType.FLIGHT_RESULT,
        title="机票已发送",
        body={"summary": summary, "plans": plans},
    )
```

当前生成三个推荐方案：

| Plan | 排序逻辑 | 说明 |
| --- | --- | --- |
| `fastest` | 按飞行时长升序 | 最快抵达 |
| `cheapest` | 按价格升序 | 最便宜 |
| `comfortable` | 大机型优先，其次起飞时间 | 舒适首选 |

字段映射示例：

```python
flight_no = _first_text(
    raw.get("flightNo"),
    raw.get("outboundFlightNo"),
    raw.get("flightNumber"),
    raw.get("flightNum"),
    raw.get("flightCode"),
    leg.get("flightNo"),
)
```

```python
"price": _first_number(
    raw.get("lowestPrice"),
    raw.get("price"),
    raw.get("totalPrice"),
)
```

---

## 4. 方案优势

### 4.1 高内聚

国内机票预订相关约束集中在：

```text
work/shared/skills/fh-domestic-flight-booking/
work/scenarios/fh_domestic_flight_booking.scenario.yaml
work/scenarios/fh_domestic_flight_booking/ask_user.schema.json
```

Skill 内部承载：

- 流程顺序。
- Tool 调用时机。
- 参数约束。
- 状态机。
- AGUI/AUIP 卡片结构。
- 轻量脚本。
- 查询、预订、往返、政策恢复工作流。

### 4.2 低耦合

边界清晰：

| 层 | 只负责 |
| --- | --- |
| OpenCode Runtime | Agent 执行、Tool 调用、模型事件 |
| OpenAgent Hub | 事件桥接、场景调度、协议转换 |
| Skill | 流程和约束 |
| MCP / Java | 真实业务能力、状态、校验、政策、订单预览 |
| Frontend | 按卡片协议渲染 |

### 4.3 可维护性强

关键约束都以文件形式存在：

| 约束类型 | 文件 |
| --- | --- |
| 场景路由 | `fh_domestic_flight_booking.scenario.yaml` |
| 业务状态机 | `schemas/state-machine.json` |
| 工具契约 | `schemas/tool-contracts.json` |
| UI 卡片协议 | `ask_user.schema.json` |
| Skill 主约束 | `SKILL.md` |
| 查询主流程 | `workflows/progressive-search.md` |
| 预订主流程 | `workflows/booking-mainline.md` |
| 往返流程 | `workflows/round-trip.md` |
| 政策恢复 | `workflows/policy-oat-recovery.md` |

### 4.4 扩展成本低

新增差旅流程的标准步骤：

1. 新增 `work/shared/skills/<skill-name>/SKILL.md`。
2. 定义 `schemas/tool-contracts.json`。
3. 定义 `schemas/state-machine.json`。
4. 定义必要脚本。
5. 新增 `scenario.yaml`。
6. 注册 MCP Tools。
7. 定义 `ask_user.schema.json`。
8. 前端支持新的 `card_type`。

Agent Core 不需要修改。

---

## 5. 核心 Skill 技术深潜：`fh_domestic_flight_booking`

### 5.1 基本信息

| 项 | 值 |
| --- | --- |
| Skill 名称 | `fh-domestic-flight-booking` |
| Scenario 名称 | `fh_domestic_flight_booking` |
| Skill 目录 | `work/shared/skills/fh-domestic-flight-booking/` |
| Scenario 配置 | `work/scenarios/fh_domestic_flight_booking.scenario.yaml` |
| Card Schema | `work/scenarios/fh_domestic_flight_booking/ask_user.schema.json` |

覆盖能力：

- 日期归一化。
- 城市归一化。
- 航班查询。
- 查询结果过滤。
- 渐进式信息披露。
- 航班选择。
- 舱位选择。
- 乘机人填写。
- 出差单绑定。
- 成本中心绑定。
- 差标超规决策。
- 信息校验。
- 订单预览。
- 异常恢复。

### 5.2 设计原则：薄 Skill，不做影子订票引擎

Skill 只做四件事：

| 职责 | 说明 |
| --- | --- |
| Sequence | 编排 MCP 调用顺序 |
| Normalize | 归一化日期、枚举、输入计划 |
| Compact | 压缩 MCP 大结果，降低模型上下文负担 |
| Guide | 通过文档和 schema 约束 Agent 行为 |

明确不做：

| 不做的事情 | 权威层 |
| --- | --- |
| TMS 航班搜索 | MCP / Java 服务 |
| 票价逻辑 | MCP / Java 服务 |
| Redis `AirDomesticBookingContext` | Java booking runtime |
| `advanceTo` / `rollbackTo` 状态副作用 | Java booking runtime |
| 差标超规计算 | Java booking runtime |
| 乘机人权限 | Java booking runtime |
| 订单保存与预览幂等 | Java booking runtime |

### 5.3 角色分工

来自 `references/architecture.md` 的实际分工：

| 角色 | 职责 |
| --- | --- |
| OpenCode Agent | 理解用户意图、选择资源、调用脚本、调用 MCP、请求用户确认 |
| Skill | 保存稳定流程知识、schema contract、确定性工具脚本 |
| fh-travel MCP | 拥有工具行为和副作用 |
| Java booking runtime | 拥有 Redis 上下文、状态转换、政策映射、校验、订单预览 |

调用关系：

```text
OpenCode Agent
  ↓ 读取 Skill 约束
fh-domestic-flight-booking Skill
  ↓ 决定调用哪个 MCP Tool
fh-travel MCP
  ↓ 执行业务动作
Java booking runtime
  ↓ 管理状态、校验、政策、订单预览
```

### 5.4 Skill 加载策略

`SKILL.md` 要求先加载主文件，再按任务加载细分资源。

| 资源 | 使用时机 |
| --- | --- |
| `references/architecture.md` | 理解架构和边界 |
| `references/mcp-tool-map.md` | 查 MCP 调用映射 |
| `references/opencode-mcp.md` | 查 OpenCode MCP 调用方式 |
| `references/source-alignment.md` | 对齐 Java 源码 |
| `workflows/progressive-search.md` | 航班查询 |
| `workflows/booking-mainline.md` | 主预订流程 |
| `workflows/round-trip.md` | 往返流程 |
| `workflows/policy-oat-recovery.md` | 政策、OAT、异常恢复 |
| `schemas/*.json` | 稳定结构约束 |
| `ask_user.schema.json` | AGUI/AUIP 卡片协议 |

该策略避免每次把所有文档加载进上下文，减少 token 压力。

### 5.5 Scenario 执行配置

触发关键词：

```yaml
trigger_keywords:
  - flight booking
  - query flight
  - 订机票
  - 预订机票
  - 国内机票
  - 差旅机票
```

优先级：

```yaml
priority: 120
```

绑定 Skill：

```yaml
execution:
  skills:
    - fh-domestic-flight-booking
```

绑定工具：

```yaml
execution:
  tools:
    - ask_user
    - queryFlightBasic
    - filterFlightList
    - chooseFlight
    - chooseCabin
    - fillPassenger
    - validateBookingInfo
    - buildOrderPreview
    - feihe-travel_queryFlightBasic
    - feihe-travel_chooseFlight
    - feihe-travel_chooseCabin
    - feihe-travel_buildOrderPreview
```

运行资源：

```yaml
resources:
  agent: opencode-default
  model: MiniMax-M2.7-highspeed
  timeout: 300
```

### 5.6 状态机设计

状态机文件：

```text
work/shared/skills/fh-domestic-flight-booking/schemas/state-machine.json
```

状态集合：

```json
[
  "INIT",
  "TRIP_CONFIRMED",
  "FLIGHT_LISTED",
  "FLIGHT_SELECTED",
  "CABIN_SELECTED",
  "PASSENGER_FILLED",
  "INFO_VALIDATED",
  "PRICE_CONFIRMED",
  "ORDER_PREVIEWED",
  "READY_TO_SUBMIT",
  "FINISHED",
  "CANCELLED"
]
```

主流程：

```text
INIT
  -> FLIGHT_LISTED
  -> FLIGHT_SELECTED
  -> CABIN_SELECTED
  -> PASSENGER_FILLED
  -> INFO_VALIDATED
  -> ORDER_PREVIEWED
  -> FINISHED
```

<div align="center">
<svg width="1040" height="420" viewBox="0 0 1040 420" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="fh_domestic_flight_booking 状态机">
  <defs>
    <filter id="smShadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="6" stdDeviation="7" flood-color="#0f172a" flood-opacity="0.13"/>
    </filter>
    <marker id="smArrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L0,6 L9,3 z" fill="#475569"/>
    </marker>
    <linearGradient id="smMain" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#2563eb"/>
      <stop offset="100%" stop-color="#0891b2"/>
    </linearGradient>
  </defs>

  <rect x="0" y="0" width="1040" height="420" rx="24" fill="#f8fafc"/>
  <text x="520" y="38" text-anchor="middle" font-family="Arial, sans-serif" font-size="22" font-weight="700" fill="#0f172a">fh_domestic_flight_booking 状态机与工具边界</text>
  <text x="520" y="64" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="#64748b">Skill 只约束高层阶段；真实状态副作用仍由 Java booking runtime 执行</text>

  <g filter="url(#smShadow)">
    <rect x="44" y="126" width="104" height="58" rx="15" fill="#ffffff" stroke="#bfdbfe"/>
    <text x="96" y="160" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" font-weight="700" fill="#1d4ed8">INIT</text>
  </g>
  <g filter="url(#smShadow)">
    <rect x="190" y="126" width="128" height="58" rx="15" fill="#ffffff" stroke="#bfdbfe"/>
    <text x="254" y="160" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" font-weight="700" fill="#1d4ed8">FLIGHT_LISTED</text>
  </g>
  <g filter="url(#smShadow)">
    <rect x="360" y="126" width="138" height="58" rx="15" fill="#ffffff" stroke="#bfdbfe"/>
    <text x="429" y="160" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" font-weight="700" fill="#1d4ed8">FLIGHT_SELECTED</text>
  </g>
  <g filter="url(#smShadow)">
    <rect x="540" y="126" width="128" height="58" rx="15" fill="#ffffff" stroke="#bfdbfe"/>
    <text x="604" y="160" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" font-weight="700" fill="#1d4ed8">CABIN_SELECTED</text>
  </g>
  <g filter="url(#smShadow)">
    <rect x="710" y="126" width="142" height="58" rx="15" fill="#ffffff" stroke="#bfdbfe"/>
    <text x="781" y="160" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" font-weight="700" fill="#1d4ed8">PASSENGER_FILLED</text>
  </g>
  <g filter="url(#smShadow)">
    <rect x="894" y="126" width="118" height="58" rx="15" fill="#ffffff" stroke="#bfdbfe"/>
    <text x="953" y="160" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" font-weight="700" fill="#1d4ed8">INFO_VALIDATED</text>
  </g>

  <g filter="url(#smShadow)">
    <rect x="710" y="274" width="142" height="58" rx="15" fill="#fff7ed" stroke="#fdba74"/>
    <text x="781" y="308" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" font-weight="700" fill="#9a3412">PRICE_CONFIRMED</text>
  </g>
  <g filter="url(#smShadow)">
    <rect x="894" y="274" width="124" height="58" rx="15" fill="url(#smMain)"/>
    <text x="956" y="308" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" font-weight="700" fill="#ffffff">ORDER_PREVIEWED</text>
  </g>
  <g filter="url(#smShadow)">
    <rect x="444" y="274" width="112" height="58" rx="15" fill="#f0fdf4" stroke="#86efac"/>
    <text x="500" y="308" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" font-weight="700" fill="#166534">FINISHED</text>
  </g>

  <path d="M148 155 H190" stroke="#475569" stroke-width="2" marker-end="url(#smArrow)"/>
  <path d="M318 155 H360" stroke="#475569" stroke-width="2" marker-end="url(#smArrow)"/>
  <path d="M498 155 H540" stroke="#475569" stroke-width="2" marker-end="url(#smArrow)"/>
  <path d="M668 155 H710" stroke="#475569" stroke-width="2" marker-end="url(#smArrow)"/>
  <path d="M852 155 H894" stroke="#475569" stroke-width="2" marker-end="url(#smArrow)"/>
  <path d="M953 184 V274" stroke="#475569" stroke-width="2" marker-end="url(#smArrow)"/>
  <path d="M852 303 H894" stroke="#475569" stroke-width="2" marker-end="url(#smArrow)"/>
  <path d="M781 184 V274" stroke="#ea580c" stroke-width="2" marker-end="url(#smArrow)"/>
  <path d="M894 303 H556" stroke="#475569" stroke-width="2" marker-end="url(#smArrow)"/>
  <path d="M710 303 H556" stroke="#475569" stroke-width="2" marker-end="url(#smArrow)"/>

  <text x="169" y="142" text-anchor="middle" font-family="Arial, sans-serif" font-size="10" fill="#64748b">query</text>
  <text x="339" y="142" text-anchor="middle" font-family="Arial, sans-serif" font-size="10" fill="#64748b">chooseFlight</text>
  <text x="519" y="142" text-anchor="middle" font-family="Arial, sans-serif" font-size="10" fill="#64748b">chooseCabin</text>
  <text x="689" y="142" text-anchor="middle" font-family="Arial, sans-serif" font-size="10" fill="#64748b">fillPassenger</text>
  <text x="873" y="142" text-anchor="middle" font-family="Arial, sans-serif" font-size="10" fill="#64748b">validate</text>
  <text x="991" y="232" text-anchor="middle" font-family="Arial, sans-serif" font-size="10" fill="#64748b">buildPreview</text>
  <text x="820" y="236" text-anchor="middle" font-family="Arial, sans-serif" font-size="10" fill="#ea580c">价格变动</text>

  <rect x="54" y="366" width="932" height="34" rx="17" fill="#ffffff" stroke="#e2e8f0"/>
  <text x="520" y="388" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#334155">stage_guard.py 基于 tool-contracts.json 做预检查；Java runtime 仍是最终状态与副作用事实来源</text>
</svg>
</div>

状态流转：

| 当前状态 | 允许流转 |
| --- | --- |
| `INIT` | `FLIGHT_LISTED` |
| `TRIP_CONFIRMED` | `FLIGHT_LISTED` |
| `FLIGHT_LISTED` | `FLIGHT_SELECTED` |
| `FLIGHT_SELECTED` | `CABIN_SELECTED`, `FLIGHT_SELECTED`, `FLIGHT_LISTED` |
| `CABIN_SELECTED` | `PASSENGER_FILLED`, `FLIGHT_LISTED` |
| `PASSENGER_FILLED` | `INFO_VALIDATED`, `PRICE_CONFIRMED` |
| `INFO_VALIDATED` | `ORDER_PREVIEWED` |
| `PRICE_CONFIRMED` | `ORDER_PREVIEWED`, `FINISHED` |
| `ORDER_PREVIEWED` | `READY_TO_SUBMIT`, `FINISHED` |
| `READY_TO_SUBMIT` | `FINISHED` |

OAT 子阶段：

```json
[
  "AWAIT_PASSENGERS",
  "NEED_TRIP_BIND",
  "NEED_COST_CENTER",
  "NEED_CONTACT",
  "OAT_READY"
]
```

### 5.7 Tool Contract 设计

工具契约文件：

```text
work/shared/skills/fh-domestic-flight-booking/schemas/tool-contracts.json
```

该文件定义每个工具的：

- 必填字段。
- 任选字段。
- 允许调用阶段。
- 枚举值。

#### 5.7.1 查询工具

```json
"queryFlightBasic": {
  "required": ["departureCity", "arrivalCity", "departureDate"],
  "stages": ["INIT", "TRIP_CONFIRMED", "FLIGHT_LISTED", "FLIGHT_SELECTED"]
}
```

含义：

- 必须有出发城市。
- 必须有到达城市。
- 必须有出发日期。
- 可在初始阶段和重新查询阶段调用。

#### 5.7.2 过滤工具

```json
"filterFlightList": {
  "required": ["sessionId"],
  "stages": ["FLIGHT_LISTED"]
}
```

含义：

- 只能在已有航班列表后过滤。
- 不能替代首次查询。

#### 5.7.3 选择航班

```json
"chooseFlight": {
  "required": ["sessionId"],
  "requiredOneOf": ["index", "flightNo"],
  "stages": ["FLIGHT_LISTED", "FLIGHT_SELECTED"]
}
```

含义：

- 必须绑定当前订票会话 `sessionId`。
- 可以通过列表序号或航班号选择。
- 禁止从其他 session 的结果中选择。

#### 5.7.4 选择舱位

```json
"chooseCabin": {
  "required": ["sessionId"],
  "requiredOneOf": ["index", "cabinName", "cabId", "price"],
  "stages": ["FLIGHT_SELECTED", "CABIN_SELECTED"]
}
```

含义：

- 必须先选航班，再选舱。
- 舱位可通过 index、名称、舱位 ID 或价格定位。

#### 5.7.5 填乘机人

```json
"fillPassenger": {
  "required": ["sessionId", "names"],
  "stages": ["CABIN_SELECTED", "PASSENGER_FILLED"]
}
```

含义：

- 必须先选舱。
- 乘机人名称是必填参数。

#### 5.7.6 校验与预览

```json
"validateBookingInfo": {
  "required": ["sessionId"],
  "stages": ["PASSENGER_FILLED", "INFO_VALIDATED", "PRICE_CONFIRMED"]
}
```

```json
"buildOrderPreview": {
  "required": ["sessionId"],
  "stages": ["INFO_VALIDATED", "PRICE_CONFIRMED", "ORDER_PREVIEWED"]
}
```

含义：

- 先填完必要信息，再校验。
- 校验通过后构建订单预览。
- 如有价格变化，进入 `PRICE_CONFIRMED` 分支。

### 5.8 输入参数设计

#### 5.8.1 首次查询最小输入

`queryFlightBasic` 最小输入：

```json
{
  "departureCity": "北京",
  "arrivalCity": "上海",
  "departureDate": "2026-06-10"
}
```

Skill 明确要求：当用户已经给出出发城市、到达城市和日期时，立即调用 `queryFlightBasic`，不得先问舱位、预算、时间偏好、乘机人或出差单。

示例：

```text
用户：帮我查一下北京到上海明天的单程机票
当前日期：2026-06-09
```

应直接调用：

```json
{
  "departureCity": "北京",
  "arrivalCity": "上海",
  "departureDate": "2026-06-10"
}
```

#### 5.8.2 查询扩展输入

枚举定义：

```json
"roundTripListMode": ["RECOMMENDED", "FREE"],
"cabinClass": ["ECONOMY", "FULL_ECONOMY", "BUSINESS", "FIRST"],
"departureDayPart": ["MORNING", "AFTERNOON", "EVENING"],
"sortBy": ["PRICE", "ARRIVAL_TIME", "DURATION", "REFUND_FLEXIBILITY"]
```

可扩展字段：

| 字段 | 说明 |
| --- | --- |
| `returnDate` | 返程日期 |
| `roundTripListMode` | 往返推荐模式 |
| `cabinClass` | 舱等 |
| `departureDayPart` | 出发时段 |
| `depTimeStart` | 出发时间起 |
| `depTimeEnd` | 出发时间止 |
| `maxPrice` | 最高价格 |
| `sortBy` | 排序方式 |

#### 5.8.3 缺失输入卡片

当缺少查询必填项时，使用 `OD_INPUT`：

```json
{
  "card_type": "OD_INPUT",
  "title": "补充航班查询信息",
  "fields": [
    {
      "id": "departureCity",
      "label": "出发城市",
      "type": "text",
      "required": true
    },
    {
      "id": "arrivalCity",
      "label": "到达城市",
      "type": "text",
      "required": true
    },
    {
      "id": "departureDate",
      "label": "出发日期",
      "type": "date",
      "required": true
    }
  ]
}
```

Skill 要求只问缺失字段，不让用户重复填写已知信息。

### 5.9 输出参数设计

#### 5.9.1 MCP 原始输出

`queryFlightBasic` 典型返回：

```json
{
  "serialNumber": "260605140647A00000001",
  "searchType": "经济舱最低价",
  "flightCount": 3,
  "filteredCount": 3,
  "totalCount": 3,
  "depCityName": "北京",
  "arrCityName": "上海",
  "depDate": "2026-06-06",
  "flightList": [
    {
      "flightId": "F001",
      "flightNo": "CA1501",
      "airId": "CA",
      "airlineName": "国航",
      "aircraftName": "波音787(大)",
      "depAirportName": "首都机场",
      "arrAirportName": "虹桥机场",
      "depAirportCode": "PEK",
      "arrAirportCode": "SHA",
      "depTime": "08:00",
      "arrTime": "10:20",
      "totalDuration": "2h20m",
      "lowestPrice": 850,
      "lowestCabinName": "经济舱",
      "stopCount": 0
    }
  ]
}
```

#### 5.9.2 AGUI/AUIP 输出

Hub 转换后的 `FLIGHT_RESULT`：

```json
{
  "card_type": "FLIGHT_RESULT",
  "title": "机票已发送",
  "body": {
    "summary": {
      "totalCount": 3,
      "filteredCount": 3,
      "searchType": "经济舱最低价",
      "depCity": "北京",
      "arrCity": "上海",
      "depDate": "2026-06-06"
    },
    "plans": [
      {
        "id": "fastest",
        "title": "最快抵达",
        "subtitle": "1h55m",
        "criteria": "duration",
        "flights": []
      },
      {
        "id": "cheapest",
        "title": "最便宜",
        "subtitle": "¥680.0 起",
        "criteria": "price",
        "flights": []
      },
      {
        "id": "comfortable",
        "title": "舒适首选",
        "subtitle": "波音787(大)",
        "criteria": "comfort",
        "flights": []
      }
    ]
  }
}
```

### 5.10 数据流转推演

#### 5.10.1 快速查询路径

```text
用户输入：
  "帮我查北京到上海明天的机票"

Agent：
  提取 departureCity=北京
  提取 arrivalCity=上海
  归一化 明天 -> 2026-06-10

Skill：
  判断三要素齐全
  禁止先问舱位
  要求直接调用 queryFlightBasic

OpenCode：
  调用 feihe-travel_queryFlightBasic

MCP：
  返回 flightList

Hub：
  监听 tool_result
  调用 maybe_assemble_flight_card
  生成 FLIGHT_RESULT

Frontend：
  收到 SSE card event
  渲染航班卡片
```

#### 5.10.2 完整预订路径

```text
INIT
  用户给出出发地、目的地、日期
  ↓
queryFlightBasic
  ↓
FLIGHT_LISTED
  展示 FLIGHT_RESULT / FLIGHT_LIST
  ↓
chooseFlight
  ↓
FLIGHT_SELECTED
  展示 CABIN_LIST
  ↓
chooseCabin
  ↓
CABIN_SELECTED
  补乘机人 / 出差单 / 成本中心 / 联系人
  ↓
fillPassenger
listTripApplications
bindCostCenter
getDefaultContact
  ↓
PASSENGER_FILLED
  ↓
validateBookingInfo
  ↓
INFO_VALIDATED
  如价格变化进入 PRICE_CONFIRMED
  如政策超规进入 POLICY_DECISION
  ↓
buildOrderPreview
  ↓
ORDER_PREVIEWED
  展示 ORDER_CONFIRM
  ↓
FINISHED
```

### 5.11 内部代码逻辑边界

#### 5.11.1 日期归一化：`normalize_request.py`

职责：

- 将相对日期转为 `yyyy-MM-dd`。
- 归一化枚举。
- 校验必填字段。
- 校验日期和时间格式。
- 校验互斥字段。

日期别名：

```python
DATE_ALIASES = {
    "today": 0,
    "tomorrow": 1,
    "day after tomorrow": 2,
    "今天": 0,
    "明天": 1,
    "后天": 2,
    "大后天": 3,
}
```

归一化逻辑：

```python
def normalize_date(value: Any, today: date) -> Any:
    if DATE_RE.match(raw):
        return raw
    if lower in DATE_ALIASES:
        return (today + timedelta(days=DATE_ALIASES[lower])).isoformat()
    return raw
```

必填校验：

```python
for key in ("departureCity", "arrivalCity", "departureDate"):
    if blank(plan.get(key)):
        errors.append(f"missing required field: {key}")
```

边界：

- 不查真实航班。
- 不判断城市是否存在。
- 不计算政策。
- 不写订票状态。

#### 5.11.2 阶段守卫：`stage_guard.py`

职责：

- 根据当前状态和目标工具检查是否允许调用。
- 返回工具必填参数提示。
- 防止 Agent 越阶段调用 MCP。

核心逻辑：

```python
def check(tool: str, stage: str, contracts: dict | None = None) -> dict:
    entry = contracts["tools"].get(tool)
    if not entry:
        return {"allowed": None, "tool": tool, "stage": stage, "reason": "unknown tool"}

    stages = entry.get("stages", [])
    allowed = "*" in stages or stage in stages

    return {
        "allowed": allowed,
        "tool": tool,
        "stage": stage,
        "expectedStages": stages,
        "required": entry.get("required", []),
        "requiredOneOf": entry.get("requiredOneOf", []),
        "fixHint": None if allowed else f"current stage {stage} is not in allowed stages for {tool}"
    }
```

边界：

- 只做高层阶段判断。
- 不执行工具。
- 不修改业务状态。
- 不替代 Java 状态机。
- 不作为最终业务权限判断。

#### 5.11.3 MCP Payload 压缩：`compact_mcp_payload.py`

职责：

- 从 MCP 大结果中提取摘要。
- 兼容多种列表字段。
- 保留关键决策字段。
- 限制返回数量。
- 避免把大 payload 直接塞进模型上下文。

可识别列表字段：

```python
LIST_KEYS = ["flightList", "flights", "items", "records", "list"]
```

字段别名：

```python
ALIASES = {
    "flightNo": ["flightNo", "outboundFlightNo", "flightNumber"],
    "airline": ["airlineName", "airline", "airlineCode", "airId"],
    "origin": ["depCityName", "origin", "departureCity", "fromCity"],
    "destination": ["arrCityName", "destination", "arrivalCity", "toCity"],
    "price": ["totalPrice", "lowestPrice", "price", "ticketPrice"],
    "cabin": ["lowestCabinName", "cabinName", "cabin", "cabinClass"],
    "policy": ["policyCompliant", "policy", "policyText"],
    "cabId": ["cabId", "cabinId"]
}
```

输出结构：

```json
{
  "summary": {
    "flightCount": 196,
    "lowestPrice": 400
  },
  "flights": [
    {
      "index": 1,
      "flightNo": "MF8561",
      "airline": "厦门航空",
      "origin": "北京",
      "destination": "上海",
      "price": 400,
      "cabin": "经济舱"
    }
  ],
  "omitted": 188
}
```

边界：

- 不改变 MCP 事实。
- 不替代业务排序。
- 不创建订单状态。
- 只为模型阅读和渐进展示降噪。

#### 5.11.4 航班卡片组装：`flight_card.py`

职责：

- 监听 `feihe-travel_queryFlightBasic` 工具结果。
- 将 MCP `flightList` 映射为 AGUI/AUIP `FLIGHT_RESULT`。
- 生成三类推荐 plan。
- 向前端输出结构化卡片。

排序逻辑：

```python
cheapest = sorted(
    flight_list,
    key=lambda f: _first_number(f.get("lowestPrice"), f.get("price"), f.get("totalPrice")) or 9e9
)
```

```python
fastest = sorted(
    flight_list,
    key=lambda f: f.get("durationMin") or _parse_minutes(_duration_text(...))
)
```

```python
comfortable = sorted(
    flight_list,
    key=lambda f: (
        _aircraft_priority(f.get("planeSize") or f.get("aircraftName") or f.get("aircraft") or ""),
        f.get("outboundDepDate") or f.get("departTime") or ""
    )
)
```

边界：

- 只负责 UI 卡片组装。
- 不执行选航班。
- 不保存用户选择。
- 不保证最终可订，最终状态以后续 MCP 结果为准。
- 不替代 `chooseFlight` / `chooseCabin`。

### 5.12 Skill 的交互策略

#### 5.12.1 首轮查询速度优先

Skill 规定：只要用户已给出出发地、目的地和出发日期，就直接调用 `queryFlightBasic`。

首轮查询前禁止调用：

- `ask_user`
- `question`
- `glob`
- `read`
- `grep`
- `skill`
- `flight-query`
- `getDateInfo`
- `checkProductAccess`
- helper scripts

目标是减少首轮航班结果延迟。

#### 5.12.2 只问必要缺失信息

交互策略：

| 用户输入 | 行为 |
| --- | --- |
| “查北京到上海明天机票” | 直接查 |
| “查明天去上海的机票” | 只问出发城市 |
| “查北京出发的机票” | 问目的地和日期 |
| “帮我订刚才最便宜的” | 如已有列表，调用 `chooseFlight` |
| “换一个早一点的” | 如已有列表，调用 `filterFlightList` 或重新 `queryFlightBasic` |

#### 5.12.3 渐进式披露

信息展示层级：

1. 查询摘要：数量、最低价、Top 选项。
2. 对比字段：航司、时间、时长、价格、经停、行李/餐食。
3. 细节字段：退改签、政策、舱位 ID、成本中心、出差单。
4. 提交前：校验结果、订单预览。

大 MCP payload 不直接输出给用户。

### 5.13 Skill 的 AGUI/AUIP 卡片策略

| Stage | Card Type | Required Shape |
| --- | --- | --- |
| Missing search input | `OD_INPUT` | 顶层 `fields[]` |
| Flight search result | `FLIGHT_RESULT` | `body.summary` + `body.plans[]` |
| Direct flight selection | `FLIGHT_LIST` | 顶层 `flights[]` |
| Cabin selection | `CABIN_LIST` | 顶层 `cabins[]` |
| Passenger details | `PASSENGER_FORM` | 顶层 `fields[]` |
| Trip/cost/contact binding | `OAT_BINDING` | 顶层 `fields[]` 或 `options[]` |
| Price changed | `PRICE_VERIFY` | 顶层 `current_price`, `original_price`, `price_diff` |
| Policy overrun | `POLICY_DECISION` | 顶层 `decision_buttons[]` |
| Final preview | `ORDER_CONFIRM` | 顶层 `order_summary`, `total_price` |
| Order completed | `ORDER_SUCCESS` | 顶层 `order_no` 或 `order_summary` |
| Cannot continue | `CANNOT_ORDER` | 顶层 `reason`, `fallback` |
| Free-text fallback | `CHAT_FALLBACK` | 顶层 `message` |

明确禁止输出未支持别名：

```text
CABIN_OPTIONS
ORDER_PREVIEW
```

### 5.14 异常恢复设计

| 异常 | 处理 |
| --- | --- |
| 上下文损坏 | `resetBookingSession` |
| 用户要求重来 | `resetBookingSession` |
| 价格变化 | `PRICE_VERIFY` + `PRICE_CONFIRMED` |
| 政策超规 | `POLICY_DECISION` + `recordPolicyUserDecision` |
| 无法继续预订 | `CANNOT_ORDER` |
| 查询字段缺失 | `OD_INPUT` |
| `ask_user` 不可用 | Hub 生成 fallback missing query card |
| 模型不发航班卡 | Hub 从 `tool_result` 自动组装 `FLIGHT_RESULT` |

### 5.15 测试覆盖

| 测试文件 | 覆盖点 |
| --- | --- |
| `tests/test_auip_flight_card.py` | 航班卡片组装、字段映射、三类 plan、空结果、容错 |
| `tests/test_opencode_chat_flight_card.py` | OpenCode `tool_result` 转 SSE `card`、session 去重、非航班工具透传 |
| `tests/test_mcp_token_config.py` | `ask_user` 本地 MCP 注册、差旅 MCP token 配置 |

---

## 6. 一次完整技术调用示例

<div align="center">
<svg width="1040" height="520" viewBox="0 0 1040 520" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="从用户查询到航班卡片的端到端时序">
  <defs>
    <filter id="seqShadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="5" stdDeviation="6" flood-color="#0f172a" flood-opacity="0.12"/>
    </filter>
    <marker id="seqArrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L0,6 L9,3 z" fill="#475569"/>
    </marker>
  </defs>

  <rect x="0" y="0" width="1040" height="520" rx="24" fill="#f8fafc"/>
  <text x="520" y="40" text-anchor="middle" font-family="Arial, sans-serif" font-size="22" font-weight="700" fill="#0f172a">端到端时序：自然语言查询 → MCP → AGUI 航班卡片</text>
  <text x="520" y="66" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="#64748b">首轮查询速度优先：三要素齐全时直接 queryFlightBasic，不先发 OD_INPUT</text>

  <g filter="url(#seqShadow)">
    <rect x="40" y="100" width="120" height="46" rx="14" fill="#ffffff" stroke="#bfdbfe"/>
    <text x="100" y="129" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" font-weight="700" fill="#1d4ed8">用户</text>
  </g>
  <g filter="url(#seqShadow)">
    <rect x="220" y="100" width="132" height="46" rx="14" fill="#ffffff" stroke="#a5f3fc"/>
    <text x="286" y="129" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" font-weight="700" fill="#0f766e">OpenAgent Hub</text>
  </g>
  <g filter="url(#seqShadow)">
    <rect x="420" y="100" width="132" height="46" rx="14" fill="#ffffff" stroke="#93c5fd"/>
    <text x="486" y="129" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" font-weight="700" fill="#1d4ed8">OpenCode</text>
  </g>
  <g filter="url(#seqShadow)">
    <rect x="620" y="100" width="132" height="46" rx="14" fill="#ecfeff" stroke="#67e8f9"/>
    <text x="686" y="129" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" font-weight="700" fill="#0f766e">Skill</text>
  </g>
  <g filter="url(#seqShadow)">
    <rect x="820" y="100" width="132" height="46" rx="14" fill="#fff7ed" stroke="#fdba74"/>
    <text x="886" y="129" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" font-weight="700" fill="#9a3412">MCP / Java</text>
  </g>

  <line x1="100" y1="146" x2="100" y2="470" stroke="#cbd5e1" stroke-dasharray="5 6"/>
  <line x1="286" y1="146" x2="286" y2="470" stroke="#cbd5e1" stroke-dasharray="5 6"/>
  <line x1="486" y1="146" x2="486" y2="470" stroke="#cbd5e1" stroke-dasharray="5 6"/>
  <line x1="686" y1="146" x2="686" y2="470" stroke="#cbd5e1" stroke-dasharray="5 6"/>
  <line x1="886" y1="146" x2="886" y2="470" stroke="#cbd5e1" stroke-dasharray="5 6"/>

  <path d="M100 186 H286" stroke="#475569" stroke-width="2" marker-end="url(#seqArrow)"/>
  <text x="193" y="176" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#334155">北京到上海明天机票</text>

  <path d="M286 228 H486" stroke="#475569" stroke-width="2" marker-end="url(#seqArrow)"/>
  <text x="386" y="218" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#334155">stream_chat / scenario route</text>

  <path d="M486 270 H686" stroke="#475569" stroke-width="2" marker-end="url(#seqArrow)"/>
  <text x="586" y="260" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#334155">读取 Skill 约束</text>

  <path d="M686 312 H486" stroke="#0f766e" stroke-width="2" marker-end="url(#seqArrow)"/>
  <text x="586" y="302" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#0f766e">归一化日期 + 三要素齐全</text>

  <path d="M486 354 H886" stroke="#475569" stroke-width="2" marker-end="url(#seqArrow)"/>
  <text x="686" y="344" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#334155">feihe-travel_queryFlightBasic({北京, 上海, 2026-06-10})</text>

  <path d="M886 396 H486" stroke="#9a3412" stroke-width="2" marker-end="url(#seqArrow)"/>
  <text x="686" y="386" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#9a3412">tool_result: flightList</text>

  <path d="M486 438 H286" stroke="#0f766e" stroke-width="2" marker-end="url(#seqArrow)"/>
  <text x="386" y="428" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#0f766e">maybe_assemble_flight_card</text>

  <path d="M286 470 H100" stroke="#6d28d9" stroke-width="2" marker-end="url(#seqArrow)"/>
  <text x="193" y="492" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#6d28d9">SSE card: FLIGHT_RESULT → 前端 FlightResultCard</text>

  <rect x="628" y="208" width="300" height="52" rx="14" fill="#ffffff" stroke="#e2e8f0"/>
  <text x="778" y="230" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" font-weight="700" fill="#0f172a">关键约束</text>
  <text x="778" y="248" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" fill="#64748b">不先问舱位；不先发 OD_INPUT；不手写 HTTP</text>
</svg>
</div>

### 6.1 用户输入

```text
帮我查一下北京到上海明天的单程机票
```

### 6.2 Agent 提取

```json
{
  "departureCity": "北京",
  "arrivalCity": "上海",
  "departureDate": "明天"
}
```

### 6.3 Skill 归一化

假设当前日期为 `2026-06-09`：

```json
{
  "departureCity": "北京",
  "arrivalCity": "上海",
  "departureDate": "2026-06-10"
}
```

### 6.4 MCP 调用

```json
{
  "tool": "feihe-travel_queryFlightBasic",
  "arguments": {
    "departureCity": "北京",
    "arrivalCity": "上海",
    "departureDate": "2026-06-10"
  }
}
```

### 6.5 MCP 返回

```json
{
  "searchType": "经济舱最低价",
  "flightCount": 3,
  "filteredCount": 3,
  "depCityName": "北京",
  "arrCityName": "上海",
  "depDate": "2026-06-10",
  "flightList": [
    {
      "flightNo": "CA1501",
      "airlineName": "国航",
      "aircraftName": "波音787(大)",
      "depTime": "08:00",
      "arrTime": "10:20",
      "totalDuration": "2h20m",
      "lowestPrice": 850,
      "lowestCabinName": "经济舱"
    }
  ]
}
```

### 6.6 Hub 转换为 Card

```json
{
  "type": "card",
  "data": {
    "card_type": "FLIGHT_RESULT",
    "card": {
      "title": "机票已发送",
      "body": {
        "summary": {
          "totalCount": 3,
          "filteredCount": 3,
          "searchType": "经济舱最低价",
          "depCity": "北京",
          "arrCity": "上海",
          "depDate": "2026-06-10"
        },
        "plans": [
          {
            "id": "fastest",
            "title": "最快抵达",
            "criteria": "duration",
            "flights": []
          },
          {
            "id": "cheapest",
            "title": "最便宜",
            "criteria": "price",
            "flights": []
          },
          {
            "id": "comfortable",
            "title": "舒适首选",
            "criteria": "comfort",
            "flights": []
          }
        ]
      }
    }
  }
}
```

### 6.7 前端渲染

```text
card_type = FLIGHT_RESULT
  -> FlightResultCard
  -> 展示航班摘要、最快、最便宜、舒适首选
```

---

## 7. 技术结论

当前差旅 Agent 的核心落点不是复杂 Prompt，而是通过 **OpenCode + MCP + Skill + AGUI/AUIP** 建立协议约束下的开发范式。

技术结论：

- OpenCode 提供开源 Agent Runtime。
- Python Hub 提供场景调度、SSE、事件映射、卡片转换。
- MCP 提供真实差旅业务工具。
- Skill 提供轻量、可审计、可版本化的业务流程约束。
- AGUI/AUIP 提供前后端结构化动态 UI 协议。
- Java booking runtime 保留业务状态、政策、校验、订单预览等权威逻辑。

`fh_domestic_flight_booking` Skill 的技术价值：

- 用状态机约束 Agent 行为。
- 用 Tool Contract 限定 MCP 调用边界。
- 用 Card Schema 限定前端交互结构。
- 用小脚本完成确定性归一化和防错。
- 不侵入 OpenCode Core。
- 不重写 Java 业务能力。
- 不让 UI 依赖自然语言输出。
- 将复杂差旅流程拆成可维护、可测试、可扩展的协议化模块。
