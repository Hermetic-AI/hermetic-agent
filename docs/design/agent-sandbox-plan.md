# Agent Sandbox & Permission Plan

> 给 `opencode` 和 `claude_code` 两类 AI Agent 引擎设计**统一的工作区沙箱 + 工具调用权限分层**。
> 目标：让 Agent 引擎只能在指定目录里读/写，只能调用指定级别的工具，Hub 这一层在调度前就拦下越权请求。

---

## 1. 背景与威胁模型

### 1.1 现状

| 引擎            | 形态                                      | 权限边界                             | 当前风险                                                                  |
| ------------- | --------------------------------------- | -------------------------------- | --------------------------------------------------------------------- |
| `opencode`    | HTTP 客户端 → 本机 `opencode serve` 后台进程     | 进程级 — 跟 `opencode serve` 启动用户同权限 | Hub 只能传 `cwd`/model/tools，文件系统、bash、sub-agent 全部由 `opencode serve` 自管 |
| `claude_code` | 本地 `claude` CLI 子进程（`claude-agent-sdk`） | 进程级 — 跟 Hub 同用户                  | Hub 只传了 `model`/`system_prompt`/`tools`/`cli_path`，**没有任何目录/命令/网络限制** |
|               |                                         |                                  |                                                                       |

两个引擎的共同问题：
- 能读 `~/.ssh/`、`/etc/passwd`、项目里别的目录
- 能跑 `rm -rf`、`curl <外部>`、`pip install` 等任意命令
- MCP 工具一旦注册，全部对 Agent 开放

### 1.2 威胁

- 数据泄露（`.env`、数据库密码、API key 写到 LLM 上下文里）
- 破坏性操作（误删/误改系统文件、格式化磁盘）
- 资源滥用（死循环跑满 CPU/GPU、刷第三方付费 API）
- 横向越权（一个租户的 agent 触碰另一个租户的工作区）

### 1.3 目标

1. **目录边界** — Agent 只能读/写**显式声明**的目录；`/etc`、`~/.ssh`、`$HOME` 顶层默认禁止。
2. **工具边界** — 三档工具级别（Safe / Standard / Full），按租户/任务场景选择。
3. **网络边界** — 默认 `off` 或 `local`，需要外网显式开启。
4. **审计** — 每次工具调用/文件访问都有结构化日志，事故可追溯。
5. **优雅降级** — 没有按引擎单独配置时，Hub 给出明确报错而不是静默放行。

---

## 2. 设计原则

- **声明优于约定** — 一切权限必须显式声明（白名单），Hub 不在配置里就是不开放。
- **分层决策** — Hub 在调度前先做一次"授权决策"；通过后再交给引擎，引擎自己内部也可以再拒。
- **可观测** — 任何拒绝都必须留下理由（哪条策略不通过、什么参数触发的）。
- **租户隔离** — 同一物理机多租户时，工作区是**互不重叠**的子目录，互相不可见。
- **向后兼容** — 旧 `AgentConfig` 不带新字段时，落到最严的档（Safe），由 ops 显式 opt-in。

---

## 3. 权限模型

### 3.1 三个工具级别

| 级别 | 文件系统 | Bash / Sub-agent | MCP 工具 | 网络 |
|---|---|---|---|---|
| **`safe`** | 只读 declared `workspace` + `readonly_dirs` | ❌ | 只读类（`web_search`） | `off` |
| **`standard`** (默认) | 读写 declared `workspace`，可读 `readonly_dirs` | 受限白名单（`ls`/`cat`/`grep`/`git status` 等） | 注册的全部 MCP，按 `allowed_tools` 过滤 | `local`（仅 10/8 + 192.168/16 + 127/8） |
| **`full`** | 读写 declared `workspace` | 全开（仍受 `denied_commands` 拦截） | 全开 | `any` |

### 3.2 AgentConfig 扩展

```python
@dataclass
class AgentConfig:
    # ... 已有字段
    name: str
    base_url: str
    sdk_type: SDKType
    api_key: str | None = None
    default_model: str | None = None

    # === 新增 ===
    workspace_dirs: list[str] = field(default_factory=list)   # 必填；Agent 允许读/写的根
    readonly_dirs: list[str] = field(default_factory=list)    # 只读附加目录
    deny_dirs: list[str] = field(default_factory=list)        # 显式黑名单（绝对路径前缀）
    deny_path_patterns: list[str] = field(default_factory=list)  # glob 模式，如 "**/.env", "**/id_rsa"

    tool_level: Literal["safe", "standard", "full"] = "standard"
    allowed_tools: list[str] = field(default_factory=list)     # 工具白名单（空 = 用 level 默认集）
    denied_tools: list[str] = field(default_factory=list)      # 工具黑名单（叠加在白名单上）
    allowed_commands: list[str] = field(default_factory=list)  # bash 命令前缀白名单
    denied_commands: list[str] = field(default_factory=list)   # bash 命令前缀黑名单

    network: Literal["off", "local", "any"] = "local"
    max_turns: int = 50
    max_budget_usd: float = 5.0
    require_approval_for_writes: bool = True   # 写文件 / 改命令是否需要 can_use_tool 回调
```

### 3.3 请求级 override

`POST /agent/chat` / `/agent/chat/stream` body 可临时覆盖：

```json
{
  "agent_name": "claude-core",
  "message": "...",
  "workspace": "/work/tenant-A/project-1",   // 临时切换工作区
  "tool_level": "safe",                       // 临时降到更严
  "extra_readonly_dirs": ["/data/public"],
  "max_turns": 5
}
```

Hub 在 `bridge.chat()` 里把请求级 override 与 AgentConfig 合并，生成**有效策略**（effective policy），并把合并结果记到 `audit_log` 里。

---

## 4. 引擎实现路径

### 4.1 `claude_code` (claude-agent-sdk)

`ClaudeAgentOptions` 已经支持大部分字段，Hub 只需要正确传递：

```python
opts = ClaudeAgentOptions(
    model=config.default_model or "claude-sonnet-4-20250514",
    system_prompt=...,
    cwd=primary_workspace,                    # ← 新增：限制子进程 cwd
    allowed_tools=effective.allowed_tools,    # ← 新增
    disallowed_tools=effective.denied_tools,
    add_dirs=effective.workspace_dirs + effective.readonly_dirs,
    permission_mode="default" if require_approval else "acceptEdits",
    can_use_tool=hub_can_use_tool_callback,   # ← 新增：Hub 拦截每一次工具调用
    max_turns=effective.max_turns,
    max_budget_usd=effective.max_budget_usd,
    # setting_sources=["project", "user"]  ← 可选：让子进程读 .claude/settings.json
)
```

`hub_can_use_tool_callback(tool_name, tool_input, context)` 由 Hub 实现，统一做：
1. **路径检查** — `tool_input` 里的每个 `path`/`file_path` 字段必须落在 `workspace_dirs` 内，且不命中 `deny_path_patterns`
2. **命令检查** — `Bash` 工具的 `command` 字段必须命中 `allowed_commands` 且不命中 `denied_commands`
3. **网络检查** — Agent 不直接出网（`WebFetch`/`WebSearch` 工具按 `network` 决定）
4. **审计** — `{allow/deny, tool, input, reason, session_id, ts}` 落日志
5. 返回 `Allow` / `Deny(reason)`

**`safe` 级别** → `permission_mode="plan"`（只读规划，不实际执行） + `allowed_tools=["Read", "Grep", "Glob"]` + `WebSearch`（按网络策略）。

### 4.2 `opencode` (opencode-ai)

`opencode serve` 自带权限系统，配置通常在 `~/.config/opencode/config.json`。Hub 走两条路：

**(a) 启动时通过 env 注入** — 我们封装一层 launcher，按 effective policy 渲染 `opencode.config.json`：

```python
def render_opencode_config(effective: EffectivePolicy) -> dict:
    return {
        "permission": {
            "edit":   "allow" if effective.tool_level != "safe" else "deny",
            "bash":   effective.allowed_commands or ("deny" if effective.tool_level == "safe" else "ask"),
            "webfetch": "allow" if effective.network == "any" else ("deny" if effective.network == "off" else "allow"),
        },
        "cwd": effective.workspace_dirs[0],
        "tools": {"Bash": False} if effective.tool_level == "safe" else {"Bash": True},
    }
```

把这份配置写到一个临时目录，启动 `opencode serve` 时 `--config <tmp>/opencode.json`，或者在多租户场景下 `cwd` 隔离 + 各自 config。

**(b) Hub 层用 `opencode_ai` SDK 的事件流做兜底拦截** — 订阅 `client.event.list()`，在 `tool_use` 事件上做同样的路径/命令/网络检查（与 Claude 同一套回调），不通过就 `client.session.abort(...)` 并返回 SSE 错误事件。

### 4.3 共享的"Hub-level policy engine"

把"路径/命令/网络/工具"四类规则提到 Hub 一个独立模块 `openagent/policy/`：

```
openagent/policy/
├── __init__.py
├── engine.py        # EffectivePolicy dataclass + merge(config, request_override)
├── path_check.py    # normalize, glob match, is_within(workspace, path)
├── command_check.py # 解析 bash 命令，按前缀 / shell metachars 处理
├── tool_filter.py   # 已知工具清单 (Read/Write/Bash/Edit/Glob/Grep/WebFetch/WebSearch + MCP 名字)
├── network_check.py # URL scheme/host 白名单
└── audit.py         # AuditLogger: 写 structlog + 可选落 Postgres
```

两个 adapter 都调它，避免重复实现。

---

## 5. 工作区规范

### 5.1 目录布局

```
/work/
├── tenants/
│   ├── tenant-A/
│   │   ├── project-1/        ← workspace
│   │   │   ├── src/
│   │   │   ├── data/         ← 可写
│   │   │   └── .git/
│   │   └── project-2/        ← 另一个 workspace
│   └── tenant-B/
│       └── ...
├── shared/
│   ├── skills/               ← 全部租户可读的 SKILL.md
│   ├── mcp/                  ← MCP 工具定义
│   └── docs/                 ← 公共文档
└── archive/                  ← 只读历史数据
```

- `workspace_dirs[0]` 是 cwd（Hub 通过 env `cwd=` 传给引擎）
- 其余 `workspace_dirs` 走 SDK 的 `add_dirs`/`include`
- `readonly_dirs` 不会出现在 cwd 候选里，但能 Read

### 5.2 路径解析规则

Hub 在拦截路径访问时**必须**做以下规范化：
1. `os.path.realpath` 解析 `..` 和 symlink
2. 在 Windows 上用 `pathlib.Path.resolve()` + 大小写不敏感比较
3. 拒绝落到 `workspace_dirs` 之外的路径
4. 拒绝任何匹配 `deny_path_patterns` glob 的路径（用 `pathspec` 库或自己写 fnmatch）

### 5.3 "敏感文件" 兜底

无论 `deny_path_patterns` 怎么配，下列路径**永远**拒：

- `**/.env`, `**/.env.*`
- `**/id_rsa`, `**/id_ed25519`, `**/.ssh/**`
- `**/.aws/credentials`, `**/.config/gcloud/**`
- `**/*.pem`, `**/*.key`, `**/*.p12`
- `**/secrets/**`, `**/credentials/**`

由 `policy/path_check.py` 里的 `BLOCKED_PATTERNS` 硬编码，不需要用户配置。

---

## 6. 网络策略

`network` 字段控制：

| 值 | 含义 | 实现 |
|---|---|---|
| `off` | 完全禁止 HTTP 出网 | `WebFetch`/`WebSearch` 工具从 allowed 列表里删；Hub 拦截引擎尝试直连 (opencode 的 custom commands) |
| `local` | 仅内网 | 拦截 URL，校验 host 在 `10.0.0.0/8`、`172.16.0.0/12`、`192.168.0.0/16`、`127.0.0.0/8` |
| `any` | 不限 | 透传 |

URL 校验在 `policy/network_check.py`，要处理 IPv6 (`::1`, `fc00::/7`, `fe80::/10`)。

---

## 7. 审计日志

### 7.1 落地点

- **结构化日志**（structlog JSON，stdout + 文件）— 实时可看
- **Postgres `audit_log` 表**（可选，配置 `audit_backend=postgres`）— 长期可查

### 7.2 schema

```sql
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    session_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    event_type TEXT NOT NULL,  -- tool_call | file_access | command_run | policy_decision
    tool_name TEXT,
    decision TEXT NOT NULL,    -- allow | deny | prompt
    reason TEXT,
    input_hash TEXT,           -- sha256 of tool input (避免存完整输入)
    input_summary JSONB,       -- 截断/脱敏后的输入摘要
    duration_ms INT,
    tenant_id TEXT             -- 未来多租户预留
);
CREATE INDEX idx_audit_session ON audit_log(session_id);
CREATE INDEX idx_audit_agent_ts ON audit_log(agent_name, ts);
```

### 7.3 脱敏

工具输入里**字段级脱敏**后再写库（避免把 `.env` 内容真存进 audit）：
- `*.env*`, `*.key`, `*.pem` → 整个输入替换为 `<redacted:env-file>`
- `*password*`, `*token*`, `*secret*` → 字段值替换为 `<redacted>`
- bash command → 头 200 字符 + sha256

---

## 8. API 表面

### 8.1 注册时声明权限

```bash
POST /agent/pool/register
{
  "name": "claude-core",
  "base_url": "local",
  "sdk_type": "claude_code",
  "default_model": "claude-sonnet-4-20250514",
  "workspace_dirs": ["/work/tenants/tenant-A/project-1"],
  "readonly_dirs": ["/work/shared/docs"],
  "tool_level": "standard",
  "network": "local",
  "max_turns": 30,
  "max_budget_usd": 2.0
}
```

### 8.2 运行时查询

```bash
GET /agent/claude-core/policy
→ 200 { "effective": { ... }, "source": { "agent_config": {...}, "request_override": null } }

GET /agent/claude-core/audit?session_id=xxx&limit=100
→ 200 { "events": [ {ts, event_type, tool_name, decision, reason, ...}, ... ] }
```

### 8.3 `/ready` 扩展

`/ready` 的 `checks` 里新增：
```json
"policy_engine": {"ok": true, "detail": "all default agents have workspace_dirs configured"},
"audit_log":     {"ok": true, "detail": "writing to stdout (audit_backend=stdout)"}
```

任何 Agent 的 `workspace_dirs` 是空数组 → `not_ready` + 明确 reason。

---

## 9. 实施路线（5 个阶段，每个阶段独立可上线）

### Phase 1 — Hub 策略引擎 + 默认拒绝
- 实现 `openagent/policy/` 四个模块
- `AgentConfig` 加新字段（带默认值，向后兼容：旧配置落到 `safe`）
- 两个 adapter 的 `create_session` 路径上做"workspace_dirs 必须非空"硬校验
- 不修改引擎的运行时行为 — 只在 Hub 入口拦截
- 验证：把 `workspace_dirs` 留空，看 `/ready` 是不是 503

### Phase 2 — Claude Code 路径集成
- `_build_options` 透传 `cwd`/`allowed_tools`/`add_dirs`/`max_turns`
- 实现 `hub_can_use_tool_callback`，每次工具调用前查 policy
- 集成 `policy/audit.py` 写结构化日志
- 验证：写一个测试用例让 agent 试图读 `/etc/passwd`，看 SSE 收到 `deny` 事件

### Phase 3 — OpenCode 路径集成
- 实现 `OpenCodeLauncher`，启动 `opencode serve` 时按 policy 渲染 config
- 订阅 `client.event.list()` 拦截 `tool_use` 事件，复用 Phase 2 的 `hub_can_use_tool_callback`
- 验证：opencode agent 试图写 `/etc/hosts`，看是否被拒

### Phase 4 — 网络策略 + 审计落库
- `policy/network_check.py` 实现三档
- `AuditLogger` 写 Postgres
- 脱敏逻辑

### Phase 5 — UI 集成
- 前端 `Agent 管理` 页加 workspace / tool level 表单
- 审计页（按 session 查）

---

## 10. 失败模式 & 兜底

| 失败模式 | 兜底 |
|---|---|
| Agent 用 `..` 越权访问 | realpath 规范化 + 严格前缀匹配 |
| Agent 用 symlink 逃逸 | realpath 解开 symlink 后再匹配 |
| `opencode serve` 启动失败 | Hub 端 `LaunchFailed` 异常 → SSE error 事件 |
| `can_use_tool` 回调超时 | Hub 默认 `deny(timeout)`，超时 5s |
| MCP 工具 `handler` 内部误操作 | 沙箱不替代 handler 自己的参数校验；Hub 只控制 Agent 能不能调它 |
| Windows 大小写不敏感 | `Path.resolve()` 后 `os.path.normcase` 再比较 |
| 同一 workspace 被两个 agent 抢占 | 工作区锁（`fcntl.flock` / `msvcrt.locking`），写时获取，读时共享 |
| 用户把 `tool_level="full"` 又 `network="any"` | 允许（这是用户显式选择），但 audit 必须记录 `{level: full, network: any, ts}` 并给运维打一条 ALERT 日志 |

---

## 11. 与现有功能的关系

| 现有 | 与本方案的关系 |
|---|---|
| `SkillRegistry` | Skills 目录会作为 `readonly_dirs` 注入；不再放 workspace 里 |
| `MCPRegistry` | `allowed_tools` 字段对 MCP 工具同样生效；MCP handler 自己做的事 Hub 不管 |
| `StorageBackend` | 审计日志写 Postgres 时复用同一个 connection pool；不重开连接 |
| `bridge.create_session` | 合并 request_override 与 AgentConfig，产出 `EffectivePolicy`，落 audit |
| `chat_stream` 路由 | 在 `bridge.chat` 入口把 effective policy 一并写进 session_info（方便审计关联） |
| 旧的 `register_agent` 路由 | 接受新字段；`workspace_dirs` 缺省时 Hub 启动期就 4xx 拒绝注册 |

---

## 12. 验证清单

每个 Phase 结束都要跑：

```python
def test_policy_blocks_etc_passwd():
    cfg = AgentConfig(workspace_dirs=["/work/x"], tool_level="standard", ...)
    eff = merge_policy(cfg, request_override=None)
    assert not path_check.is_allowed(eff, "/etc/passwd", "read")

def test_safe_level_disables_bash():
    cfg = AgentConfig(workspace_dirs=["/work/x"], tool_level="safe")
    eff = merge_policy(cfg, request_override=None)
    assert "Bash" not in eff.allowed_tools
    assert path_check.is_within(eff, "/work/x/foo.py", "read") is True

def test_audit_redacts_env():
    log = audit.record(tool="Read", input={"file_path": "/work/x/.env", ...})
    assert log["input_summary"]["file_path"] == "<redacted:env-file>"

def test_network_off_blocks_fetch():
    cfg = AgentConfig(network="off", ...)
    assert network_check.is_allowed(cfg, "https://example.com") is False
    assert network_check.is_allowed(cfg, "http://10.0.0.1") is False

def test_effective_policy_merge():
    cfg = AgentConfig(tool_level="standard", allowed_tools=["Read","Write"], max_turns=10)
    eff = merge_policy(cfg, {"tool_level": "safe", "max_turns": 2})
    assert eff.tool_level == "safe"
    assert eff.max_turns == 2
    # allowed_tools 沿用 cfg 的，因为 override 没改
    assert "Write" not in eff.allowed_tools
```

E2E（用 `claude-agent-sdk` mock）：

```python
async def test_claude_can_use_tool_denies_root():
    cfg = AgentConfig(workspace_dirs=["/work/x"], tool_level="standard", ...)
    captured = []
    async def cb(tool, inp, ctx):
        captured.append((tool, inp))
        return deny("path /etc/passwd not in workspace")
    # Patch ClaudeSDKClient.query/receive to feed a synthetic tool_use
    # Then assert cb was called and the response was "deny"
```

---

## 13. 决策记录（待确认）

1. **`tool_level="full"` 是否需要二次确认（双因素/admin token）？** —— 推荐是，否则白名单 + 审计就是空话
2. **多租户用什么隔离？** —— 工作区子目录（轻） vs Docker 容器（重） vs Windows Job Object（OS 级）—— 推荐子目录起步
3. **审计保留期？** —— 90 天 / 180 天 / 永久？需要合规确认
4. **网络 `local` 范围** —— 是否包含 169.254/16（link-local，metadata 服务）？推荐拒绝
5. **要不要支持 `dry_run`？** —— 让用户先看 agent 计划做什么再决定是否放行（Claude SDK 的 `permission_mode="plan"` 可以做到）
