# opencode 工作区 + Skill 投递 — 根因与最小修法

> **目的**: 让 opencode 引擎 (1) 在 scenario 指定的项目路径下工作, (2) 接收 OpenAgent 注入的 system_prompt (含 skill 描述), (3) 工具白名单真正生效
>
> **结论先行**: 2 个真修法(都是 OpenAgent 自己的 bug)+ 1 个用户侧配置;**不需要**把 system_prompt 拼进 parts,**不需要**软链到 `~/.claude/skills/`,**不需要**重启 opencode serve

---

## 0. 三条根因(全部从源码溯源)

| # | 根因 | 证据(文件:行) |
|---|---|---|
| 1 | OpenAgent 接 `system_prompt` 但 **没传给** opencode SDK,导致模型看不到 OpenAgent 注册的 skill | `relate_project/opencode-sdk-python/src/opencode_ai/types/session_chat_params.py:26` 有 `system: str` 字段;`src/openagent/providers/opencode_chat.py:131` 调 `client.session.chat(...)` 漏传 |
| 2 | opencode serve 启动后 cwd 固化,无法 per-session 切工作区 | `relate_project/opencode/packages/opencode/src/session/system.ts:48-63` 从 `ctx.directory` 读;`ctx.directory` 来自 `opencode serve --cwd` (launcher.py 已在做) |
| 3 | opencode skill 从**目录**发现,需要让 scenario 的工作区里有 `.claude/skills/` 或 `.agents/skills/` | `relate_project/opencode/packages/opencode/src/skill/index.ts:172-232` `discoverSkills()` 从 `global.home` + `directory` 向上扫描 + `cfg.skills.paths` |

**关键洞察**: root cause 1 是 OpenAgent **自己**没传参数,不是 SDK 不支持;root cause 2 不是 opencode 的限制(它有 per-call `?directory=`);root cause 3 不是协议问题,是部署目录问题。

---

## 1. 真修法(2 处代码改动 + 1 处配置)

### 1.1 Fix #1 — `system=system_prompt` 透传(bug fix, 2 行)

**改前** `src/openagent/providers/opencode_chat.py:131-138, 272-280`:

```python
result = await client.session.chat(
    session_id, model_id=..., provider_id=..., parts=parts,
    tools=tool_list, timeout=timeout,    # ← system_prompt 漏了
)
```

**改后**:

```python
result = await client.session.chat(
    session_id, model_id=..., provider_id=..., parts=parts,
    system=system_prompt,                # ← 加上,2 处
    tools=tool_list, timeout=timeout,
)
```

**为什么这样就够了**: opencode server 的 `prompt.ts:1695` 接 `system: string`,`system.ts:65-77` 的 `SystemPrompt.skills(agent)` 会把它和**自动发现的 skill 列表** + env 信息**拼到最终 system prompt** 送进 LLM (`llm.ts:129`)。所以:
- OpenAgent 注入的 system_prompt (含 skill 描述) → 到达模型
- opencode 自己发现的 skill → 也到达模型
- 二者**自然合并**,不需要任何 hack

### 1.2 Fix #2 — per-session directory(scenario 绑工作区)

**问题**: opencode serve 启动时 `--cwd` 决定所有 session 的工作区。scenario 之间的工作区没法隔离。

**修法**: 利用 opencode server 的 `?directory=` per-call 透传(优先级最高,见 `workspace-routing.ts:181-184`)。

**改动文件清单**:

| 文件 | 改动 |
|---|---|
| `src/openagent/providers/base.py` | `SessionInfo` 加 `directory: str \| None` |
| `src/openagent/providers/opencode_lifecycle.py` | `create_session(...)` 加 `directory` 参数;传给 `client.session.create(extra_query={"directory": dir})`;存入 `SessionInfo` + `StorageSession.metadata` |
| `src/openagent/providers/opencode_chat.py` | 新增 `_workspace_query(session_info)` 辅助;`blocking_chat` 和 `stream_chat` 的 `client.session.chat(...)` 用 `**_workspace_query(session_info)` 注入 |
| `src/openagent/providers/opencode_adapter.py` | `OpenCodeAdapter.create_session(...)` 加 `directory` 转发 |
| `src/openagent/providers/agent_bridge.py` | `AgentBridge.create_session(...)` 加 `directory` 转发 |
| `src/openagent/api/routes.py` | 新增 `_resolve_session_directory(request)` 读 `request.ctx.scenario.workspace.workspace_dirs[0]`;3 个 `create_session` 调用点(chat / chat/stream / create_session)都传 `directory=_resolve_session_directory(request)` |

**运行时流向**:

```
请求进入 → ScenarioMiddleware.route() → 命中 scenario →
request.ctx.scenario = <ScenarioConfig>
↓
routes.py chat() → _resolve_session_directory(request) →
scenario.workspace.workspace_dirs[0] = "/path/to/project"
↓
bridge.create_session(directory="/path/to/project")
↓
lc.create_session → client.session.create(extra_query={"directory": "/path/to/project"})
↓
opencode server: InstanceState 按 directory 隔离 skill / env / file 状态
↓
session.chat(..., extra_query={"directory": "/path/to/project"}) ← 每次都用同一 directory
```

### 1.3 配 #1 — scenario 工作区下放 skill 目录(零代码)

**在 scenario workspace 根下**建 `.claude/skills/` 或 `.agents/skills/`,把 OpenAgent 注册的 skill 软链进去:

```bash
# 例: scenario workspace = work/tenants/tenant-A/projects/project-1/
cd work/tenants/tenant-A/projects/project-1
mkdir -p .claude/skills
for skill_dir in ../../../shared/skills/*/; do
  ln -sfn "$(realpath "$skill_dir")" ".claude/skills/$(basename "$skill_dir")"
done
```

**为什么有效**: opencode 的 `discoverSkills()` 从 `directory` 向上扫到 `worktree`,看到 `.claude/skills/flight-query/SKILL.md` 就加载。`system.ts:65-77` 把所有发现的 skill 拼进 system prompt。

**应急**(代码没改前): 也可软链到 `~/.claude/skills/`,走 `global.home` 路径,但不推荐(绕过 scenario 隔离)。

---

## 2. 不需要做的事(原文档 §2 / §5 列的"必须改代码"大多不需要)

| 原文档建议 | 为什么不需要 |
|---|---|
| 把 system_prompt 拼进 parts[0] + `<system_prompt>` 包裹 | SDK 有原生 `system: str` 字段 (`session_chat_params.py:26`),原 §2.1 方案是 workaround |
| 改 `agent_bridge.create_session` 加 cwd 校验 + warning | root cause 2 已经在 server 端用 `?directory=` 解决;OpenAgent 端只要把 directory 透传过去即可 |
| 把 OpenAgent 的 skill **也**作为 opencode 工具暴露 | skill 是 prompt 知识,不是 tool;opencode 的 `skill` 工具已支持加载 skill (`system.ts:75`),model 知道 `use the skill tool to load a skill` |
| 软链到 `~/.claude/skills/` | 应急方案;在 scenario 工作区下建 `.claude/skills/` 才是正确路径 |
| 重启 opencode serve 才能切 cwd | 错。`?directory=` per-call 就能切,session 期间不需要重启 |

---

## 3. 验证(端到端)

### 3.1 验证 skill 真的进 system prompt

```bash
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -H "X-Scenario: flight_booking" \
  -d '{"message":"查 2026-06-04 PEK-SHA 航班,用 flight-query skill"}'
# 期望: 模型回中提到 flight-query 描述、调用 MCP 拿数据
```

如果模型**不**知道 flight-query 存在 → 说明:
- (a) Fix #1 没生效 → 检查 `client.session.chat` 调用的 `system` 参数
- (b) scenario workspace 下没 `.claude/skills/flight-query/SKILL.md` → 软链

### 3.2 验证 cwd 真的是 scenario 的工作区

```bash
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -H "X-Scenario: flight_booking" \
  -d '{"message":"pwd"}'
# 期望: 回 scenario workspace 根(非 opencode serve 启动 cwd,非 /)
```

如果回的不是 scenario workspace → 检查 `_resolve_session_directory()` 取的是 `request.ctx.scenario.workspace.workspace_dirs[0]`,且 routes.py 三个调用点都传了。

### 3.3 验证 skill 越权被拒

```bash
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -H "X-Scenario: _generic" \
  -d '{"message":"x", "skills":["evil_skill"]}'
# 期望: 200, 但 routing.rejected_skills 含 "evil_skill"
# (走的是 scenario injector 的白名单,与 directory 无关)
```

---

## 4. 不变的边界

- **opencode serve 启动 cwd** 仍由 `providers/launcher.py` 决定 — 那是进程级默认;Fix #2 不改这个,只让 session-level 优先级更高
- **tool 白名单** 链路 (`scenarios/injector.py → bridge.chat(tools=...) → mcp_registry.to_opencode_format`) 不动,已经通了
- **scenario injector** 不动 — skills / tools / system_prompt 的 caller 越权过滤已经在它里面
- **chat 端点** URL 不动 — `POST /agent/chat` 和 `POST /agent/chat/stream` 是唯一对话入口(CLAUDE.md HARD CONSTRAINT)

---

## 5. 变更影响面(2 处代码 fix + per-session directory 6 文件)

- `opencode_chat.py` — 加 `system=system_prompt` (2 行) + `_workspace_query` 辅助 (1 函数, ~10 行) + 2 处 `**_workspace_query(session_info)` 注入
- `base.py` — `SessionInfo` 加 `directory` 字段 (1 行)
- `opencode_lifecycle.py` — `create_session` 加 `directory` 参数 + SDK 透传 + 持久化
- `opencode_adapter.py` — `create_session` 加 `directory` 转发
- `agent_bridge.py` — `create_session` 加 `directory` 转发
- `routes.py` — `_resolve_session_directory` 辅助 + 3 个调用点加 `directory=...`
- `docs/design/opencode-skill-and-workspace-constraint.md` — 本文档(重写)

**测试**: 原 483 tests 不动(纯新增参数,全部默认 None);建议在 `tests/test_providers_opencode.py` 新增 1 个用例验证 `system=system_prompt` 真的传过去(用 `unittest.mock.AsyncMock` 拦截 `client.session.chat` 并 assert kwargs 含 `system=...)。

---

## 6. 关联文档 / 源码

- `docs/design/integrated-orchestration-plan.md` §4 资源目录, §12 接口契约
- `docs/design/scenario-routing-proposal.md` §3 schema, §6 注入机制
- `CLAUDE.md` §"🚨 HARD CONSTRAINT: 统一对话入口" — 永远从 /agent/chat 入口
- `relate_project/opencode-sdk-python/src/opencode_ai/types/session_chat_params.py` — `system: str` 字段
- `relate_project/opencode/packages/opencode/src/server/routes/instance/httpapi/middleware/workspace-routing.ts` — directory 解析与透传
- `relate_project/opencode/packages/opencode/src/session/system.ts` — system prompt 合并(skills + env + 用户 system)
- `relate_project/opencode/packages/opencode/src/skill/index.ts` — skill 发现机制

