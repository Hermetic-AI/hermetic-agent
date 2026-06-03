# 场景对话 Walkthrough — 以 flight-query 为例

> **目的**: 用现有的 `flight-query` skill 端到端串一遍"场景对话"是怎么跑的
> 适用对象: 新成员 onboarding / 新建一个业务场景
> 关联: `docs/design/opencode-skill-and-workspace-constraint.md`(本批次代码修复)· `docs/design/integrated-orchestration-plan.md` §4-6 · `docs/design/scenario-routing-proposal.md` §3

---

## 0. 三件套 — 场景、Skill、工作区

一个能跑起来的"场景对话"需要三件套,缺一不可:

| 件 | 是什么 | 谁负责加载 | 文件位置 |
|---|---|---|---|
| **Skill** | LLM 在该场景下要遵循的"知识/工作流"(纯 prompt 模板) | `SkillRegistry` 在 `bootstrap` 时从 `.skills/` 目录递归加载 `SKILL.md` | `src/openagent/.skills/<name>/SKILL.md` |
| **Scenario** | 业务定义:路由规则、system_prompt、工具白名单、安全策略、workspace_dirs | `ScenarioRegistry` 启动时从 `work/scenarios/*.scenario.yaml` 加载 | `work/scenarios/<name>.scenario.yaml` |
| **Workspace** | opencode 引擎"工作在哪"——读哪些文件、写哪些文件、skill 从哪里找 | `ScenarioMiddleware` 把 scenario 挂到 `request.ctx`,`routes.py` 把 `workspace.workspace_dirs[0]` 透传给 opencode SDK | 由 `launcher.py` 启动 opencode serve 时定,每个 session 可覆盖 |

---

## 1. 前置(假设你已经有了)

1. **opencode serve 跑着**: `launcher.py` 已经把它启动,绑 `--cwd <某个项目根>`(一般是 `work/tenants/<tenant>/projects/<project>/`)
2. **OpenAgent 跑着**: `python -m openagent.main`,端口 18000
3. **skill 在位**: `src/openagent/.skills/flight-query/SKILL.md` 已经存在(本次示例用现成的)
4. **ScenarioLoader 已配置**: `work/scenarios/` 在 loader 的扫描路径里(默认就在 `work/scenarios/`,无需额外配置)

---

## 2. Step-by-Step:新建一个 flight-query 场景

### 2.1 Step 1 — 准备项目工作区(给 opencode 一个"工作目录")

`work/tenants/tenant-A/projects/project-1/` 就是 scenario 的"主工作区"。`${PROJECT_DIR}` 在 scenario 加载时被替换成这个路径。

```bash
PROJECT_DIR="work/tenants/tenant-A/projects/project-1"

# 1. 建项目根
mkdir -p "$PROJECT_DIR"

# 2. 把业务代码/数据放进来(演示用,实际项目里可能已经是 git clone)
ln -sfn "$(pwd)/src"  "$PROJECT_DIR/src"      # 可选:让 opencode 看得见业务代码
ln -sfn "$(pwd)/tests" "$PROJECT_DIR/tests"

# 3. 把 flight-query skill 暴露给 opencode(关键!)
#    opencode 的 skill 发现从 --cwd 向上扫 .claude/skills/ 和 .agents/skills/
mkdir -p "$PROJECT_DIR/.claude/skills"
ln -sfn "$(realpath "src/openagent/.skills/flight-query")" \
         "$PROJECT_DIR/.claude/skills/flight-query"

# 4. 验证(可见 SKILL.md 即可)
ls -la "$PROJECT_DIR/.claude/skills/flight-query/"
# 期望: SKILL.md 出现在列出的文件里
```

**为什么 .claude/skills/ 是关键**: opencode server 的 `discoverSkills()`(`packages/opencode/src/skill/index.ts:172-232`)从 opencode 实例的工作目录**向上**扫描 `.claude/skills/**/SKILL.md` 和 `.agents/skills/**/SKILL.md`。把软链放在 `project-1/.claude/skills/` 下,opencode 自动加载 → 拼进 system prompt。

### 2.2 Step 2 — 写 Scenario YAML

新建 `work/scenarios/flight_query.scenario.yaml`:

```yaml
# ============================================================
# 飞鹤机票查询 — 演示用最简场景
# 与 flight_booking.scenario.yaml 的关系: 这只是查票,不订票
# ============================================================
name: flight_query                # 必须 ^[a-z_][a-z0-9_]*$ — 路由 ID
version: "1.0.0"
description: |
  飞鹤机票查询场景。User 提需求 → 调 flight-query skill + MCP 工具
  → 整理成表格返回。不下订,不接 HITL,纯查询。
enabled: true
tags: [travel, query]
tier: silver

# 路由: 关键词命中
routing:
  trigger_keywords: [查机票, 查航班, flight, flight query, 航班查询]
  trigger_intent: null
  url_path: null
  priority: 100        # 数字越小越先匹配;_generic 是 99999

# 执行: system_prompt + skills + tools
execution:
  system_prompt: |
    你是飞鹤差旅 AI 助手 — 机票查询专责。
    当用户问"明天北京到上海的航班"时,严格遵循 [flight-query] skill 的工作流:
    1. 解析用户需求(出发/到达/日期/舱等/筛选)
    2. 缺信息就追问(出发/到达/日期/回程必问)
    3. 调 queryFlightBasic 工具
    4. 按"输出格式"小节整理成 Markdown 表格

    严禁:
    - 编造航班号、价格、政策
    - 在用户没确认前执行任何写操作
    - 调用白名单以外的工具
  skills: [flight-query]            # ← 关键:把 OpenAgent 注册的 skill 名写在这
  tools: [query_flight_basic, get_weather]   # 来自 MCP,scenarios/injector.py 过滤后下发
  orchestration: single            # 这次只要单步聊天,不用 HITL / parallel / chain

# 安全
security:
  tool_level: safe                  # safe / standard / full
  allowed_tools: [Read, Grep, Glob] # 不让 LLM 写文件,只读 + LLM 自己的工具
  denied_tools: [Write, Edit, Bash, WebFetch, WebSearch]
  allowed_commands: []
  denied_commands: [rm -rf, sudo, dd, mkfs, "chmod 777"]
  network: local
  max_turns: 10
  max_budget_usd: 0.3
  require_approval_for_writes: true

# 工作区 — 这里是 per-session 透传给 opencode 的根
workspace:
  strategy: project_relative
  workspace_dirs:
    - ${PROJECT_DIR}                # loader 阶段已 placeholder 解析 → 实际路径
  readonly_dirs:
    - ${WORK_SHARED}/docs
  deny_dirs:
    - /etc
    - ~/.ssh
    - ~/.aws
    - ${HOME}
  deny_path_patterns:
    - "**/.env"
    - "**/.env.*"
    - "**/id_rsa"
    - "**/*.pem"
    - "**/*.key"
  launcher:
    prefer_engine: opencode
    fallback_engine: claude_code
    engine_config:
      opencode:
        config_template: standard

# A2UI(可选,本次示例不用)
a2ui:
  enabled: false
  protocol: auip

# 渐进 skill(本次不渐进,全量加载)
progressive_skill:
  strategy: all
  budget_tokens: 4000
  budget_policy: warn
  initial_skills: []
  load_on_state: {}

# 资源目录
resource_dirs:
  prompts: ${WORK_SHARED}/prompts/flight_query
  skills: ${WORK_SHARED}/skills/flight_query
  mcp_servers: ${SCENARIO_DIR}/mcp
  shared_skills: ${WORK_SHARED}/skills
  tools: ${SCENARIO_DIR}/tools
  cards: ${SCENARIO_DIR}/cards

# 资源
resources:
  agent: opencode-default           # 对应 launcher.py 注册的 agent 名称
  model: claude-sonnet-4-5
  timeout: 120

# 业务元数据
metadata:
  cost_center: T-1001
  ab_group: control
  sla_tier: silver
  dashboard_url: null
```

**关键字段解释**:

| 字段 | 作用 | 注意事项 |
|---|---|---|
| `name` | 路由 ID | `^[a-z_][a-z0-9_]*$`,跟 `X-Scenario` header / `body.scenario` 完全匹配 |
| `routing.priority` | 路由优先级,数字越小越先匹配 | `_generic=99999`、`_default=90000`,业务场景通常 50-500 |
| `execution.system_prompt` | 场景级别的"角色设定" | 跟 skill 里的"工作流"分开;system_prompt 是**人话**,skill 是**机器话** |
| `execution.skills` | 要注入的 skill 名(对应 `src/openagent/.skills/<name>/SKILL.md`) | 顺序就是注入顺序,前面的 skill 描述先进 system_prompt |
| `execution.tools` | 允许的 MCP 工具白名单(由 scenarios/injector.py 二次过滤) | caller 多传的也会被拒 |
| `workspace.workspace_dirs[0]` | **本次新增** — 透传给 opencode SDK 的 `?directory=`,决定 opencode 的工作区 + skill 发现 | 单元素 list,运行时被 `routes.py:_resolve_session_directory` 取 `dirs[0]` |
| `progressive_skill.strategy` | `none` / `all` / `on_demand` | `on_demand` 适合 skill 很大、状态机多步的场景(HITL) |

### 2.3 Step 3 — 让 ScenarioRegistry 加载它

**方式 A:热重载**(推荐,无需重启服务)

```bash
curl -X POST http://localhost:18000/agent/scenarios/reload
```

**方式 B:重启服务**(`reload` 不可用时)

```bash
# Ctrl-C 当前服务
python -m openagent.main
```

**验证已加载**:

```bash
curl -s http://localhost:18000/agent/scenarios | jq '.scenarios[] | {name, version, priority, skills: .execution.skills}'
```

期望看到 `flight_query` 在列出的 scenarios 里,`priority: 100`,`skills: ["flight-query"]`。

### 2.4 Step 4 — 发起对话(同步版)

```bash
curl -X POST http://localhost:18000/agent/chat \
  -H "Content-Type: application/json" \
  -H "X-Scenario: flight_query" \
  -d '{
    "message": "查明天北京到上海最便宜的机票"
  }'
```

**响应**(节选示意):

```json
{
  "success": true,
  "session_id": "ses_abc123",
  "agent_name": "opencode-default",
  "result": {
    "message": {
      "role": "assistant",
      "content": "✈️ 北京 → 上海 · 2026-06-04（周三）· 经济舱\n\n| # | 航班 | 起飞-到达 | ... |\n..."
    },
    "tool_calls": [
      {"id": "tu_1", "name": "query_flight_basic", "input": {"departureCity": "北京", "arrivalCity": "上海", "departureDate": "2026-06-04", "cheapest": true}}
    ]
  },
  "duration": 1.23
}
```

### 2.5 Step 5 — 发起对话(流式版)

```bash
curl -N -X POST http://localhost:18000/agent/chat/stream \
  -H "Content-Type: application/json" \
  -H "X-Scenario: flight_query" \
  -d '{
    "message": "查明天北京到上海下午的直飞,要含行李"
  }'
```

期望 SSE 流:

```
data: {"type": "session", "data": {"session_id": "ses_xyz", "agent_name": "opencode-default"}}

data: {"type": "text", "data": {"content": "正在调"}}

data: {"type": "text", "data": {"content": "正在调用 queryFlightBasic..."}}

data: {"type": "tool_use", "data": {"tool_name": "query_flight_basic", "input": {...}}}

data: {"type": "text", "data": {"content": "✈️ 北京 → 上海 · 2026-06-04 · 下午 · 直飞 · 含行李\n\n| # | ... |"}}

data: {"type": "done", "data": {}}
```

### 2.6 Step 6 — 多轮(续接已有 session)

第 2 轮不需要 `X-Scenario`(已经绑在 session 上),但建议保留以防 scenario 重启时丢失:

```bash
curl -X POST http://localhost:18000/agent/chat \
  -H "Content-Type: application/json" \
  -H "X-Scenario: flight_query" \
  -d '{
    "session_id": "ses_xyz",
    "message": "前三个里挑个最适合出差的"
  }'
```

---

## 3. 端到端 trace — 模型实际看到的 system_prompt 长什么样

当 `POST /agent/chat` 命中 `flight_query` 后,经过本批次的代码修复,模型最终拿到的 `system` 字段大致是:

```
[你 = OpenAgent 飞鹤机票查询助手 — system_prompt 部分]

你是飞鹤差旅 AI 助手 — 机票查询专责。
当用户问"明天北京到上海的航班"时,严格遵循 [flight-query] skill 的工作流:
1. 解析用户需求(出发/到达/日期/舱等/筛选)
2. 缺信息就追问(出发/到达/日期/回程必问)
3. 调 queryFlightBasic 工具
4. 按"输出格式"小节整理成 Markdown 表格

严禁:
- 编造航班号、价格、政策
- 在用户没确认前执行任何写操作
- 调用白名单以外的工具

[= SkillRegistry 注入的 flight-query.prompt_template =]

# Flight Query Agent Skill

通过 MCP 端点 `https://traveldev.feiheair.com/api/mcp` 查询航班...
... (完整 SKILL.md 正文)

## MCP 端点配置
| Endpoint | https://traveldev.feiheair.com/api/mcp |
| Token | ... |

## 自然语言 → 参数映射
...

## 输出格式
...
```

**外加**(opencode server 自己拼的):

```
<env>
  Working directory: /work/tenants/tenant-A/projects/project-1
  Workspace root folder: /work/tenants/tenant-A
  Is directory a git repo: yes
  Platform: win32
  Today's date: Wed Jun 03 2026
</env>

[opencode auto-discovered skills]
<available_skills>
  <skill>
    <name>flight-query</name>
    <description>通过 MCP 端点查询国内/国际航班,支持单程、往返、最低价...</description>
    <location>file:///work/tenants/.../project-1/.claude/skills/flight-query/SKILL.md</location>
  </skill>
</available_skills>

[opencode tools list]
- Read, Grep, Glob
- query_flight_basic
- get_weather
```

**工具调用的可见性**: LLM 看到的工具集 = `execution.tools` (场景白名单) **∩** `execution.skills` 中引用的 MCP 工具 ∩ caller 在 `body.tools` 里传的。**三方任一不过都不会下发**。

---

## 4. 数据流(从请求到 LLM)

```
POST /agent/chat  {message, X-Scenario, body.scenario, ...}
   │
   ▼
[Sanic app]
   │
   ├── 1. ScenarioMiddleware (request 中间件)
   │     ├── ScenarioRouter.route() → 6 优先级匹配 (X-Scenario 头 > URL > body.scenario > 关键词 > intent > _generic)
   │     └── request.ctx.scenario = <ScenarioConfig>
   │
   ├── 2. routes.py::chat
   │     ├── 检查 request.ctx.scenario_error (有则 400 返回)
   │     ├── _resolve_session_directory(request) = scenario.workspace.workspace_dirs[0]
   │     └── bridge.create_session(agent_name, directory=<project root>)
   │           │
   │           ▼
   │     AgentBridge.create_session → OpenCodeAdapter.create_session
   │           │
   │           ▼
   │     lc.create_session → AsyncOpencode.session.create(
   │         extra_query={"directory": "/work/tenants/.../project-1"}
   │     )
   │           │
   │           ▼
   │     opencode server: WorkspaceRoutingMiddleware
   │       ├─ 解析 ?directory=
   │       ├─ InstanceState.context.directory = ...
   │       └─ discoverSkills() 从该目录向上扫 .claude/skills/, 加载 flight-query
   │
   ├── 3. ScenarioInjector.inject()
   │     ├── 过滤 caller 的 skills / tools / system_prompt (白名单)
   │     ├── SkillRegistry.build_system_prompt_with_skills(
   │     │     system_prompt, [flight-query]
   │     │ ) → 把 flight-query.prompt_template 拼到 system_prompt 后
   │     └── 返回 {system_prompt, skills, tools}
   │
   ├── 4. bridge.chat(system_prompt=..., skills=["flight-query"], tools=[...])
   │     │
   │     ▼
   │   opencode_chat.py::blocking_chat (或 stream_chat)
   │     ├── 读 adapter._sessions[sid].directory
   │     ├── 构造 parts = [{type: "text", text: last_content, id: ...}]
   │     └── AsyncOpencode.session.chat(
   │           session_id,
   │           model_id=...,
   │           provider_id="opencode",
   │           parts=parts,
   │           system=system_prompt,                ← Fix #1: 真正传了
   │           tools={"query_flight_basic": True, "get_weather": True},
   │           **_workspace_query(session_info),     ← Fix #2: {directory: ...}
   │         )
   │
   ├── 5. opencode server 端
   │     ├── PromptHandler: 合并 {用户的 system + 自动发现的 skills + env}
   │     ├── LLM call (claude-sonnet-4-5)
   │     └── 流式返回 (event.list() SSE)
   │
   └── 6. event.list() 实时事件
         ├── message.part.updated (text deltas)
         ├── message.part.updated (tool, running)
         ├── message.part.updated (tool, completed)
         └── session.idle → 结束
```

---

## 5. 验证 checklist

| 验证项 | 命令 | 期望 |
|---|---|---|
| ① skill 已加载 | `curl -s http://localhost:18000/agent/skills \| jq '.skills[] \| select(.name=="flight-query") \| .name'` | `"flight-query"` |
| ② scenario 已加载 | `curl -s http://localhost:18000/agent/scenarios \| jq '.scenarios[] \| select(.name=="flight_query") \| .name'` | `"flight_query"` |
| ③ opencode 工作区是项目根 | 调 chat 时,日志里 `"opencode_session_created" ... "directory": "/work/tenants/.../project-1"` | 路径正确 |
| ④ LLM 知道 flight-query | 模型回复中提到 "flight-query" 或 "MCP" 或 "queryFlightBasic" | 有 |
| ⑤ LLM 真的能调工具 | 响应里 `tool_calls` 非空,或日志里 `"tool_use"` | 有 |
| ⑥ LLM 工作在项目根 | 让模型 "pwd" 或 "ls" → 输出项目根下的内容 | 项目根 |
| ⑦ skill 软链可见 | `ls work/tenants/.../project-1/.claude/skills/flight-query/SKILL.md` | 文件存在 |
| ⑧ 越权 skill 被拒 | body.skills = ["nonexistent_skill"] → routing_log.rejected_skills 含该项 | 有 |

---

## 6. 常见踩坑

| 现象 | 原因 | 修法 |
|---|---|---|
| 模型完全不知道 flight-query | scenario 里没写 `execution.skills: [flight-query]` | 加上 |
| 模型没自动调 queryFlightBasic | `execution.tools` 没列,且 caller 也没传 | 加上白名单 |
| 模型说"我无法调外部 API" | flight-query SKILL.md 没放进 opencode 工作区下的 `.claude/skills/` | 按 §2.1 Step 1 软链 |
| 模型回复"我不知道你在哪个项目" | `workspace.workspace_dirs[0]` 配错,或 `routes.py:_resolve_session_directory` 没读到 | 检查 `request.ctx.scenario` 是否被注入,看 `logger.info` 输出 |
| 改了 scenario YAML 不生效 | 没 reload | `POST /agent/scenarios/reload` |
| `pwd` 回复 `/` 而非项目根 | opencode serve 启动时 `--cwd` 不是项目根,或 per-call directory 没传 | 检查 `launcher.py` 的 `--cwd` + `routes.py` 三个调用点都传了 `directory=_resolve_session_directory(request)` |

---

## 7. 已有场景对照表

| Scenario | orchestration | 渐进 skill | A2UI | 适用场景 |
|---|---|---|---|---|
| `_generic` | single | none | no | 兜底,无业务匹配时 |
| `_default` | single | none | no | 中间兜底 |
| `flight_booking` | hitl | on_demand (4000 token) | yes (8 cards) | 完整订票流程 |
| `flight_query` ← **本例** | single | all (4000 token) | no | 只查票,不订 |
| `code_review` | delegate | all (6000 token) | no | 代码评审,4 维度委派子 agent |
| `customer_service` | (待确认) | (待确认) | (待确认) | 客服 |
| `expense_audit` | (待确认) | (待确认) | (待确认) | 报销审核 |

新建业务场景的推荐做法:**先看 `_generic` + 一个最相近的业务场景(如本例的 `code_review` 单步版)**,复制改名,只改 routing + system_prompt + skills + tools,workspace 复用现成的 `${PROJECT_DIR}` 模板。

---

## 8. 一行 cheat sheet

```bash
# 新建场景 = 3 步
# 1. 软链 skill 到 opencode 工作区
ln -sfn "$(realpath src/openagent/.skills/<skill>)" "work/tenants/<t>/projects/<p>/.claude/skills/<skill>"

# 2. 写 YAML
$EDITOR work/scenarios/<scenario>.scenario.yaml

# 3. 热重载 + 测试
curl -X POST http://localhost:18000/agent/scenarios/reload
curl -X POST http://localhost:18000/agent/chat \
  -H "X-Scenario: <scenario>" \
  -d '{"message": "..."}'
```
