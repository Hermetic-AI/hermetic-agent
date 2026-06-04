# Agent Sandbox Runtime — 容器级沙箱服务设计

> **目的**: 把 OpenAgent 当前**本机进程级**的 opencode/claude_code 启动 (`providers/launcher.py`) 演进为**容器/集群级**沙箱运行时,解决"skill 用完要清""opencode 跑挂拖垮主进程""多租户互相污染""集群化无从下手"等问题。
>
> **范围**: 一次 chat 请求从 Hub 入口到 opencode 进程执行,中间这段"运行环境"的设计。
>
> **状态**: 草案 **v0.3**,2026-06-04 修订。本次修订做 3 个关键转向 (使用**原生 Docker CLI** 启动容器,不再依赖任何外部 sandbox wrapper):
> 1. **持久化优先** — 容器 stop 保留环境,只有 `rm` 才清
> 2. **Workspace 保持 host 绝对路径** — agent 看到的路径跟 host 一致
> 3. **凭证走 env 挂载** — LLM API key / 业务 API key 通过 `docker run -e` 直接进 sandbox,**不引入 egress 代理**
>
> 历史版本: v0.1 (沙箱池) → v0.2 (容器集群 + 路由) → **v0.3 (持久化 + 路径保持 host + env 凭证 + clone mode)**

---

## 0. 与 `agent-sandbox-plan.md` 的边界

| 文档 | 关注层次 | 关键词 |
|---|---|---|
| **`agent-sandbox-plan.md`** (已有) | **应用层** — 进程内 | `tool_level` / `workspace_dirs` / `network` 白名单 / `can_use_tool` 回调 / `audit_log` |
| **本文** (`agent-sandbox-runtime-design.md`) | **进程/容器层** — 进程外 | Docker 隔离 / tmpfs / skill 挂载 / 集群路由 / 资源限制 |

两者是**正交的**。应用层策略由 Hub 在 spawn 容器时**透传**成 `policy.json`,容器内的 opencode 进程继续按它自带的权限系统执行;容器外的 sandbox runtime 负责"它能不能跑、跑在哪、跟谁隔离"。

> 类比: `agent-sandbox-plan.md` 是"在公司里员工能干什么",本文是"员工在几号隔间办公、隔间几点关门、换部门要不要换楼层"。

---

## 0.5 核心概念澄清(Sandbox ≠ Session)

**v0.1 文档里把"容器即 session"写得太简化,这里修正**。本文涉及 3 个不同层级的对象:

```
┌─────────────────────────────────────────────────────────────┐
│ OpencodeNode  (1 个 docker 容器 = 1 个 long-running 进程)    │
│   ├─ opencode serve (单进程, 监听 :8080)                     │
│   │   ├─ session-A  (用户甲的对话, in-memory 状态)          │
│   │   ├─ session-B  (用户乙的对话, in-memory 状态)          │
│   │   └─ session-C  (用户甲第 2 轮, 复用 session-A)         │
│   │                                                          │
│   lifecycle: 几小时 ~ 几天 (直到 idle 超时 / 主动 stop)      │
└─────────────────────────────────────────────────────────────┘
```

| 概念 | 数量级 | 生命周期 | 谁管理 |
|---|---|---|---|
| **OpencodeNode** (容器) | 集群里 N 个 (默认 2~3) | 长活,几小时~几天 | Hub Router |
| **session** (opencode 内) | 每个 node 上 10~50 个并发 | 几分钟~几十分钟 | opencode 自身 |
| **chat turn** (一次对话) | 每次请求 1 个 | 几百 ms~几十秒 | 用户驱动 |

**关键含义**:

- **不是每次对话启动新容器**。用户开 10 轮对话 = 10 次 chat turn,可能全在同一个 session 里,共享 1 个容器。
- **session 是 opencode 自己的概念** (`POST /session` 创建,`POST /session/{id}/message` 续接)。同一个 session 的多轮 chat 共享上下文。
- **容器的销毁时机** = 节点 idle 超时 / 主动 stop / 资源回收。**不**是 chat 结束。
- **单容器能并发多个 session**。opencode serve 本身是 HTTP server,1 个进程并行处理 N 个 session。

> 旁证: E2B / Modal / Daytona 都是这个模型 — 1 sandbox = 1 长活进程,SDK 持有 `sandbox_id` 跨多次调用复用。opencode 跟它们是同一类。

---

## 1. 背景与痛点

### 1.1 现状

`src/openagent/providers/launcher.py` 是当前的 L4 引擎启动器:

- `opencode` → `Popen(["opencode", "serve", "--port", ...])` 长期跑在本机,绑定 `127.0.0.1`
- `claude_code` → per-session 子进程
- 配置 `work/cache/opencode-configs/{name}.json` 写磁盘

**本机进程级的 5 个具体问题**:

| # | 问题 | 触发场景 |
|---|---|---|
| 1 | skill 污染 — 每次注入 skill 写到本机 `~/.claude/skills/` (软链也走这里),opencode 下次启动还认 | scenario A 跑完留了个临时 skill,scenario B 启动看到这个 skill |
| 2 | opencode 跑挂拖垮主进程 — `opencode serve` 内存泄漏/CPU 跑满时 Hub 跟着抖 | skill 写得差触发死循环 |
| 3 | 多租户互相可见 — 同一台机跑两个租户,都能 `ps aux` 看到对方 | 暂未支持多租户,提前防 |
| 4 | skill 是"热修改"状态 — 中心服务更新 skill 后,opencode 进程里读的是旧版 | skill 迭代期间请求拿到混合内容 |
| 5 | 集群化无从下手 — 想加 1 台机器分流,需要重做调度、状态机、资源限制 | 规模到 N 以后 |

### 1.2 目标

1. **持久化优先** — sandbox 内的工作进度、装好的包、agent 状态全部保留,**只有 `rm` 才清**
2. **进程隔离** — 一个 opencode 跑挂只挂自己的容器,Hub 进程健康
3. **skill 不可变** — 容器生命周期内 skill 文件**内核层只读**(ro bind mount)
4. **快速扩缩** — 集群加节点 = 改 compose / 起新 docker,Hub 自动发现并加入路由
5. **零侵入 chat 入口** — `/agent/chat` 协议不变,后端从 `Popen` 切到容器路由对调用方透明
6. **热路径 < 100ms** — 命中已起容器时,chat turn 延迟只取决于 HTTP 跳数,不重新启 opencode
7. **Workspace 路径保持 host 绝对路径** — agent 看到 `/work/tenant-A/p1`,host 上也是这个路径(参考 Docker 的 "absolute paths preserved")

### 1.3 非目标

- 不做 microVM (Firecracker/gVisor) — 阶段一用 Docker + cgroup 就够;Phase 5 评估
- 不替代 `agent-sandbox-plan.md` 的应用层策略 — 两个层次各自做各自的事
- 不实现 opencode 自身的 session 调度 — 那在 opencode 进程内部
- **不在 MVP 阶段搞"沙箱池/预热池"** — opencode 容器就是长活的,本身不需要"池化"
- **不**强制"容器销毁即清" — 抗污染靠 ro bind mount + workspace 隔离,不靠"销毁=干净" (v0.1 旧设计,v0.3 弃)

---

## 2. 设计原则

- **容器即节点, 节点即 sandbox** — 1 个 docker 容器 = 1 个 long-running opencode 节点 = 1 个 sandbox
- **持久化优先** — sandbox 内的工作进度全部保留,**只有 `rm` 才清** (v0.3 转向)
- **session 在容器内** — opencode 内部维护 session 状态,跨 chat turn 复用
- **immutable by default** — skill 走 ro bind mount,容器根 FS ro
- **workspace 保持 host 路径** — bind mount 到 host 绝对路径,agent 看到跟 host 一致 (v0.3 转向)
- **Hub 无状态** — Hub 只存元数据(session→node 映射表、节点健康状态),执行状态都在容器内
- **凭证走 env 挂载** — LLM API key / 业务 API key 通过 `docker run -e` 进 sandbox;sandbox 被攻破 = key 泄露,**MVP 阶段接受这个风险** (Phase 5 评估 egress 代理的必要性)
- **可降级** — 单机模式能独立工作(1 hub + 1 opencode),加节点不破坏单机体验
- **2 种部署都支持** — docker-compose 一并起 / 独立 `docker run` 后接 Hub
- **opt-in ephemeral** — 极少数敏感场景 (执行不可信代码) 才用 `mode: ephemeral` (tmpfs + 销毁即清)

---

## 3. 核心抽象

### 3.1 `OpencodeNode` — 集群里的一个节点 (= 1 个 sandbox)

**1 个 docker 容器 = 1 个 OpencodeNode = 1 个 opencode serve 进程**。

```python
@dataclass
class OpencodeNode:
    id: str                          # 节点 id,如 "opencode-1"
    base_url: str                    # http://opencode-1:8080
    container_id: str | None         # docker container id (本机起的有,远端注册的可能没有)
    
    # 状态机 (v0.3 改: 拆 agent 和 container 状态)
    container_state: Literal["created", "running", "stopped", "removed"]
    agent_state: Literal["starting", "ready", "executing", "unhealthy", "stopped"]
    
    # 工作模式
    mode: Literal["persistent", "ephemeral"] = "persistent"
    # persistent: 默认,stop 保留环境,rm 才清
    # ephemeral: opt-in,tmpfs,rm 时全清 (敏感场景)
    
    # 引用资源
    workspace: WorkspaceSpec         # 主工作区 (bind mount 到 host 路径)
    extra_workspaces: list[WorkspaceSpec]  # 额外 workspace (总是 ro)
    mode_workspace: Literal["direct", "clone"] = "direct"  # direct / clone
    skill_bundles: list[SkillBundle] # 节点预装/挂载的 skill (ro)
    policy_version: str              # 节点当前生效的 policy 版本
    
    # 状态
    health: NodeHealth               # last_check_ts, latency_ms, error_count
    current_sessions: int            # 当前并发 session 数 (从 opencode 拉)
    max_concurrent_sessions: int = 50
    
    # 时间
    created_at: datetime
    last_used_at: datetime
    started_at: datetime | None      # 上次 start 时间
    stopped_at: datetime | None      # 上次 stop 时间
```

**Lifecycle (4 个动作, `docker create` / `docker start` / `docker stop` / `docker rm`)**:

```
                create            run (docker start)        stop (docker stop)
   (none) ──────────────▶ created ──────────────▶ running ──────────────▶ stopped
                            │                       │  ↑                       │
                            │ rm                    │ run                     │ run
                            ▼                       │  │                       │
                        removed                     └──┘───────────────────────┘
                                                     (保留所有状态: skill, history, 
                                                      installed packages, etc.)
```

| 动作 | 内部操作 | 数据保留 |
|---|---|---|
| **`create`** | `docker create` (不起 opencode) | 容器层 + 镜像 layer |
| **`run`** (= start) | `docker start` + 启 opencode | + agent 状态 + session |
| **`stop`** | `docker stop` (opencode 收到 SIGTERM,优雅退出) | 容器层 + 镜像 layer + opencode 历史文件 |
| **`rm`** | `docker rm` | 只剩 host 上的 workspace (workspace 是 host bind mount,不进容器层) |

**重要含义**:
- **stop 不删** — 装好的包、agent state、history 全保留
- **rm 才删** — 容器层清掉,但 host 上的 workspace 目录**不动**
- **restart 不丢** — opencode 进程重启后,之前 chat 的 session 状态可以从 `/root/.local/share/opencode/` (容器内) 恢复 (取决于 opencode 自身是否持久化)
- **ephemeral 模式** — 容器 stop 时自动 rm,workspace 是 tmpfs,rm 后什么都不剩

### 3.2 `SkillBundle` — 抗污染的关键

不直接挂 skill 目录,而是定义一个"不可变快照":

```yaml
# skill-bundle.yaml
id: flight-query-v1.4.0
name: flight-query
version: 1.4.0
digest: sha256:abc123...           # 内容指纹,用于缓存命中 + 镜像层复用
mount_target: /workspace/.skills/flight-query
readonly: true                     # ★ 关键:ro 挂载,内核层禁写
files:
  - SKILL.md
  - scripts/
  - references/
depends_on:                        # 依赖其他 skill
  - query_flight_basic
```

**3 个核心特性**:

| 特性 | 怎么做 | 防什么 |
|---|---|---|
| **immutable** | `sha256(digest)` 作为版本 tag,同 digest 复用 | 中心更新 skill 后旧容器仍能跑旧版(rollback 友好) |
| **readonly** | `docker run --mount ...:ro` | opencode 自己想改也改不动(内核 EROFS) |
| **versioned** | bundle id 含 `version`,并行挂多版 | skill 灰度发布 |

> 注: skill 本身不带 `env:` 字段 (v0.3 调整)。凭证类 (LLM API key) 走 sandbox 启动时的 `docker run -e` 注入,不在 skill 资源里。

### 3.3 `Workspace` — 默认 bind mount 到 host 绝对路径 (v0.3 关键转向)

```python
@dataclass
class WorkspaceSpec:
    # 类型
    mode: Literal["direct", "clone"] = "direct"
    # direct:  bind mount host 目录到 sandbox 同路径 (默认,Docker direct mode)
    # clone:  sandbox 内 git clone,host 目录 ro mount,expose 成 git remote (Docker clone mode)
    
    # host 路径
    host_path: str                   # e.g. "/work/tenant-A/project-1"
    # ★ v0.3 关键: 容器内 mount 到相同绝对路径,不是 /workspace
    # 容器内路径 = host_path (保留绝对路径)
    
    # 只读
    read_only: bool = False          # extra workspaces 默认 True
```

**v0.3 转向**: 从 `tmpfs 默认` 改为 **`bind mount 到 host 绝对路径`** (agent 看到跟 host 一致,错误信息、log 路径可直接在 host 用)。

**两种 workspace 模式**:

| 模式 | 行为 | 用例 |
|---|---|---|
| **`direct`** (默认) | bind mount host 目录到 sandbox 同路径,**agent 直接改 host 文件** | 单一 agent 改单一项目,边改边 review |
| **`clone`** | host 目录 ro mount,sandbox 内有私有 git clone,expose 成 git remote | 多 agent 并行改同一 repo,或不可信代码,或工作树要保持干净 |

**为什么默认 `direct` 而不是 `tmpfs`**:
- agent 的工作进度 (装好的包、调试中间状态) **有价值**,rm 才清
- bind mount 到 host 路径 → 错误信息、build 输出、log 路径**直接在 host 上能用**
- opencode 的 skill 发现机制**因为 `~/.claude/skills/` 真实位置能看到**,更符合直觉

**`ephemeral` 模式** (opt-in, 敏感场景):
```python
OpencodeNode(
    mode="ephemeral",
    workspace=WorkspaceSpec(mode="direct", host_path="/tmp/scratch"),
    # 容器内 /tmp/scratch 是 tmpfs
    # stop = 自动 rm
    # 不持久化任何东西
)
```

### 3.4 `Policy` — 容器内场景信息载体

**应用层策略 (`EffectivePolicy` from `agent-sandbox-plan.md`) 序列化后写进容器**:

```json
// /opt/sandbox/policy.json (ro bind mount,容器内)
{
  "policy_version": "v1",
  "scenario": "flight_booking",
  "agent": {
    "name": "opencode",
    "model": "anthropic/claude-sonnet-4-20250514"
  },
  "skills": ["flight-query"],
  "workspace_mode": "direct",
  "tool_level": "standard",
  "network": "local",
  "max_turns": 30,
  "max_budget_usd": 2.0
}
```

> 注 (v0.3): 不再有 `workspace.type: tmpfs` (默认 bind),`env: {MCP_TOKEN: ...}` (凭证走 sandbox 启动 env,不在 policy.json 里)。

容器内 `entrypoint.sh` 读 `policy.json` → 渲染 opencode `config.json` → exec opencode serve。**LLM API key / 业务 API key 通过 `docker run -e` 在节点启动时注入**,不进 policy.json 也不进 skill 资源。

---

## 4. 容器内路径布局 + 加载链路

### 4.1 路径布局(v0.3: workspace 保持 host 绝对路径)

```
/ (容器根, --read-only)
│
├── opt/sandbox/                  ← 镜像自带,只读
│   ├── entrypoint.sh
│   ├── health_server.py
│   ├── render_config.py
│   └── policy.json               ← ★ Hub 注入,ro bind mount
│
├── usr/ etc/ var/ ...            ← 系统目录,只读
│
# ====== 下面是容器层,跟镜像一起,stop 保留 / rm 才清 ======
│
/root/.config/opencode/           ← entrypoint 渲染,容器层
└── config.json                   ← 含 "skills": {"paths": [...]}
                                   ← + model / permission / 等

/root/.local/share/opencode/      ← opencode session/history 持久化
├── session-db.sqlite             ← opencode 自己管理
└── ...

/root/.claude/                    ← opencode 自己的 skill 发现
└── skills/                       ← (空目录或被覆盖,见 §4.4)

# ====== 下面是 bind mount 到 host 绝对路径 ======
│
/work/tenant-A/project-1/         ← ★ v0.3 关键: bind mount 到 host 同路径
├── .skills/                      ← Hub 注入 skill (ro bind)
│   ├── flight-query/             ← 内层是 ro
│   └── weather-query/
├── src/                          ← host 真实目录 (rw, agent 可改)
├── data/
└── ...

/tmp/                             ← tmpfs (临时)
```

**v0.3 关键变化**:
- ❌ **不再强制 mount 到 `/workspace`**
- ✅ **直接 mount 到 host 绝对路径** (e.g. `/work/tenant-A/project-1`)
- ✅ opencode 看到的路径 = host 路径 = 错误信息里看到的路径
- ✅ opencode 的 `~/.claude/skills/` 仍然存在(因 tmpfs 化),但由 `cfg.skills.paths` 主导,不会被自动污染

### 4.2 Skill 加载链路(4 步,不污染)

```bash
# 1. Hub 端: docker create 时挂载
docker create \
  --name opencode-1 \
  -v /work/tenant-A/project-1:/work/tenant-A/project-1 \  # 主 workspace (rw)
  -v /work/shared/skills/flight-query:/work/tenant-A/project-1/.skills/flight-query:ro \
  -v /opt/sandbox/policy.json:/opt/sandbox/policy.json:ro \
  --read-only \
  --tmpfs /tmp:size=100m \
  opencode-sandbox:base-v1.4

# 2. Hub 端: docker start (起 opencode)
docker start opencode-1

# 3. 容器内 entrypoint.sh 启动
#    - 读 /opt/sandbox/policy.json
#    - 渲染 /root/.config/opencode/config.json
#    - exec opencode serve --config .../config.json

# 4. opencode 启动
#    - 从 cfg.skills.paths 加载 skill (ro bind, 只读)
#    - 从 cwd = /work/tenant-A/project-1 启动
#    - opencode 看到的路径跟 host 一致
```

### 4.3 场景信息(Policy)加载链路

```
Hub 端:
  EffectivePolicy (合并 AgentConfig + request_override)
        ↓ 序列化
  /opt/sandbox/policy.json (ro bind mount,容器内)
        ↓ entrypoint.sh 读
  渲染 /root/.config/opencode/config.json (容器层,stop 保留)
        ↓
  opencode serve --config .../config.json
```

**v0.3 变化**: `config.json` 写在**容器层** (而不是 tmpfs),所以 `stop` 后 `start` 还能复用,**`rm` 才清**。

### 4.4 opencode 视角:它看到什么

```bash
$ pwd
/work/tenant-A/project-1
# 跟 host 完全一致

$ ls /work/tenant-A/project-1/.skills/
flight-query/

$ cat /work/tenant-A/project-1/.skills/flight-query/SKILL.md
<skill 内容>

$ ls /root/.claude/skills/
ls: cannot access '/root/.claude/skills/': No such file or directory
# ★ 关键: opencode 的 ~/.claude/skills/ 不被注入 (避免污染)
# skill 走 cfg.skills.paths 显式加载

$ echo x > /work/tenant-A/project-1/.skills/flight-query/SKILL.md
bash: /work/tenant-A/project-1/.skills/flight-query/SKILL.md: Read-only file system
# ★ 内核层 EROFS,root 也改不动

$ opencode serve --config /root/.config/opencode/config.json ...
# opencode 从 cfg.skills.paths 加载 /work/tenant-A/project-1/.skills
# cwd = /work/tenant-A/project-1
# 错误信息、log 路径、build 输出**全部是 host 真实路径**
```

---

## 5. 架构:Hub + OpencodeNode 集群

```
┌────────────────────────────────────────────────────────────────┐
│ L1  API  (api/controllers/chat_controller.py)                  │
│     └─▶ 收到请求 → 解析 scenario → 调 Router.route()          │
├────────────────────────────────────────────────────────────────┤
│ L2  Hub Router  (sandbox/router.py, ~250 行)                   │
│     ├─ SessionTable: session_id → node_id  (粘性路由)          │
│     ├─ NodeRegistry: 所有 OpencodeNode 的健康状态              │
│     ├─ RoutingStrategy: sticky / least_sessions / round_robin │
│     ├─ SkillDistributor: 预装 skill 到各 node (ro bind)        │
│     └─ PortForwarder: 转发 host:port → sandbox:port            │
├────────────────────────────────────────────────────────────────┤
│ L3  OpencodeNode × N  (sandbox/node.py, ~150 行/节点)          │
│     ├─ 节点 1: docker create opencode-sandbox:base             │
│     ├─ 节点 2: docker create opencode-sandbox:base             │
│     └─ 节点 3: docker create opencode-sandbox:base             │
│     (每个节点内: 1 个 opencode serve 进程 + N 个 session)     │
├────────────────────────────────────────────────────────────────┤
│ L4  Container  (镜像: opencode-sandbox:base-v1.4)              │
│     ├─ ENTRYPOINT: 读 policy.json → 渲染 config → 启 opencode│
│     ├─ env:  LLM_API_KEY / 业务 API key (docker run -e 注入)  │
│     ├─ /opt/sandbox/policy.json  (ro bind,Hub 注入策略)        │
│     ├─ /<host_path>/  (bind mount 到 host 绝对路径,rw)        │
│     ├─ /<host_path>/.skills/  (ro bind,Hub 注入 skill)         │
│     ├─ /root/.config/opencode/  (容器层,stop 保留)            │
│     ├─ /root/.local/share/opencode/  (容器层,stop 保留)        │
│     └─ health_server.py: 周期 /healthz 上报状态                │
└────────────────────────────────────────────────────────────────┘
```

### 5.2 Hub Router 接口 (v0.3 增 run/stop/rm)

```python
class HubRouter:
    # 节点生命周期 (v0.3: 拆 run/stop/rm)
    async def create_node(self, image: str, workspace: WorkspaceSpec, 
                         skills: list[str], mode: str = "persistent") -> OpencodeNode
    async def run_node(self, node_id: str) -> None                 # docker start + 起 opencode
    async def stop_node(self, node_id: str) -> None                # docker stop,环境保留
    async def rm_node(self, node_id: str) -> None                  # docker rm,清理 (ephemeral 模式额外清理 tmpfs)
    
    # 路由 + 业务
    async def register_node(self, base_url: str) -> OpencodeNode   # 远端注册
    async def heartbeat_loop(self) -> None
    async def route(self, session_id: str | None, prompt: str) -> RoutingDecision
    async def exec_chat(self, node: OpencodeNode, session_id: str, prompt: str) -> ChatResult
    
    # 端口转发 (v0.3 新增)
    async def publish_port(self, node_id: str, sandbox_port: int, host_port: int | None = None) -> int
    async def unpublish_port(self, node_id: str, host_port: int) -> None
    async def list_ports(self, node_id: str) -> list[PortMapping]
    
    # 查询
    async def list_nodes(self) -> list[OpencodeNode]
    async def health(self) -> RouterHealth
```

### 5.3 路由策略 (同 v0.2)

| 策略 | 行为 | 适用 |
|---|---|---|
| `sticky_session` (**默认**) | 同 `session_id` 永远路由到同一节点;新 session 选最闲的节点 | 保留 opencode in-memory 状态(chat history、context) |
| `least_sessions` | 每次按 `current_sessions` 最少选节点,**不粘性** | 纯负载均衡,接受每次请求路由可能变 |
| `round_robin` | 轮询分配 | 测试/调试 |
| `weighted` | 按 `weight` 配置分配 (e.g. 节点 1:2, 节点 2:1) | 异构硬件 |

### 5.4 节点健康检查

```python
async def heartbeat_loop(self):
    while True:
        for node in self.nodes.values():
            try:
                resp = await self.http.get(f"{node.base_url}/health", timeout=2)
                if resp.status == 200:
                    node.agent_state = "ready"
                    node.health.error_count = 0
                else:
                    node.health.error_count += 1
            except Exception:
                node.health.error_count += 1
            
            if node.health.error_count >= 3:
                node.agent_state = "unhealthy"
                # 容器还在,但 opencode 死了 → 自动 restart
                await self.run_node(node.id)
        await asyncio.sleep(5)
```

### 5.5 Port Forwarding (v0.3 新增)

**场景**: opencode 跑 `npm run dev` 起了一个 dev server (在 sandbox 内的 0.0.0.0:3000),用户要在 host 浏览器访问 `http://localhost:3000`。

**API**:

```bash
# Hub API
POST /sandboxes/{id}/ports
  {"sandbox_port": 3000, "host_port": 8080}
  → 200 {"host_port": 8080, "sandbox_port": 3000, "status": "active"}

POST /sandboxes/{id}/ports
  {"sandbox_port": 3000}    # host_port 留空,自动分配
  → 200 {"host_port": 32768, "sandbox_port": 3000, "status": "active"}

GET /sandboxes/{id}/ports
  → 200 {"mappings": [{"host_port": 8080, "sandbox_port": 3000}]}

DELETE /sandboxes/{id}/ports/{host_port}
  → 204
```

**实现**: Hub 调 `docker port` 或直接 `iptables` / `socat` 做端口映射。MVP 阶段用 `socat` 简单实现。

**注意 (loopback 隔离的坑)**:
- sandbox 内服务必须 bind `0.0.0.0`,不能 `127.0.0.1` (容器 loopback 跟 host loopback 不是同一个)
- host 端口冲突时返回 409
- `host.docker.internal` 从 sandbox 内访问 host 服务 (e.g. host 上的 PostgreSQL)

---

## 6. 关键执行流

### 6.1 启动节点 (v0.3: docker create + start, 持久化优先)

```bash
# docker create: 起容器 (不起 opencode),所有 mount 在 create 时定
docker create \
  --name opencode-1 \
  --hostname opencode-1 \
  --network sandbox-net \
  --read-only \
  --tmpfs /tmp:size=100m \
  --memory 2g \
  --cpus 2 \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --pids-limit 128 \
  --health-cmd "curl -f http://127.0.0.1:7777/healthz" \
  --health-interval 5s \
  -v /work/tenant-A/project-1:/work/tenant-A/project-1 \  # ★ v0.3: host 绝对路径
  -v /work/shared/skills/flight-query:/work/tenant-A/project-1/.skills/flight-query:ro \
  -v /opt/sandbox/policy.json:/opt/sandbox/policy.json:ro \
  -e ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}" \          # ★ v0.3: 凭证走 env 挂载
  -e OPENAI_API_KEY="${OPENAI_API_KEY}" \
  -e FLIGHT_API_KEY="${FLIGHT_API_KEY}" \
  opencode-sandbox:base-v1.4

# docker start: 容器起,entrypoint.sh 跑,opencode serve 起来
docker start opencode-1
```

### 6.2 Skill 分发 (v0.3: docker create 时挂, stop 保留)

```python
async def create_node(self, image: str, workspace: WorkspaceSpec, 
                      skills: list[str], mode: str = "persistent") -> OpencodeNode:
    """docker create 节点,所有 mount 在 create 时定。"""
    
    # 1. 主 workspace: bind mount 到 host 绝对路径 (v0.3 关键)
    mounts = [
        Mount(type="bind", source=workspace.host_path, target=workspace.host_path),
    ]
    
    # 2. extra workspaces: 总是 ro
    for extra in workspace.extra_workspaces:
        mounts.append(Mount(type="bind", source=extra.host_path, 
                            target=extra.host_path, read_only=True))
    
    # 3. skill: bind mount 到 workspace/.skills/<name>:ro
    for skill_name in skills:
        bundle = self.skill_registry.get(skill_name)
        skill_target = f"{workspace.host_path}/.skills/{bundle.name}"
        mounts.append(Mount(type="bind", source=bundle.local_path, 
                            target=skill_target, read_only=True))
    
    # 4. policy.json: ro bind
    mounts.append(Mount(type="bind", source=self._write_policy(skills, workspace),
                        target="/opt/sandbox/policy.json", read_only=True))
    
    # 5. 凭证 env (v0.3: 从 host 注入,sandbox 启动时拿到)
    env = {
        "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY", ""),
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", ""),
        "FLIGHT_API_KEY": os.environ.get("FLIGHT_API_KEY", ""),
    }
    
    # 6. docker create
    container = self.docker.containers.create(
        image=image,
        name=f"opencode-{uuid}",
        mounts=mounts,
        environment=env,
        read_only=True,
        tmpfs={"/tmp": "size=100m"},
        network="sandbox-net",
        mem_limit="2g",
        cpu_quota=2.0,
        cap_drop=["ALL"],
        security_opt=["no-new-privileges"],
        pids_limit=128,
        healthcheck={"test": ["CMD", "curl", "-f", "http://127.0.0.1:7777/healthz"],
                     "interval": 5 * 10**9},
        detach=True,
    )
    
    # 7. 立刻 start (或者用户显式 run 时再 start)
    container.start()
    
    return OpencodeNode(
        id=f"opencode-{uuid}",
        container_id=container.id,
        container_state="running",
        agent_state="starting",
        mode=mode,
        workspace=workspace,
        ...
    )
```

**关键限制**: docker **不允许在容器运行时改 bind mount**。所以 skill 分发 = **create 时挂**。运行中加 skill = rm + 重建。

### 6.3 一次 chat 请求的完整旅程 (v0.3: 凭证走 env, 直连出站)

```
1. Client → POST /agent/chat
   {session_id: "s-001", scenario: "flight", prompt: "查明天到深圳的航班"}

2. ChatController 解析 scenario
3. ScenarioRouter.route("flight") → 查表得到 skills=["flight-query"]
   (这些 skill 已在节点 create 时预装)

4. HubRouter.route(session_id="s-001", prompt=...)
   ├─ 查 SessionTable: s-001 → opencode-1
   ├─ 选 opencode-1 (sticky 命中)
   └─ 返回 RoutingDecision(node=opencode-1)

5. HubRouter.exec_chat(opencode-1, session_id="s-001", prompt=...)
   ├─ 调 opencode-1 容器内 opencode: POST /session/s-001/message
   │   (s-001 已存在 → opencode 复用 session 上下文)
   ├─ opencode 读到 /work/tenant-A/project-1/.skills/flight-query/SKILL.md
   ├─ 按 skill 步骤调 MCP
   │   opencode → HTTP POST https://api.flight.com/search
   │     │ (从 env 读 FLIGHT_API_KEY,直接发 X-API-Key header)
   │     ↓ (直连)
   │   api.flight.com
   └─ 返回结果 + 更新后的 session 状态

6. Controller 返回结果给 Client
   (节点不动,session 状态保留在 opencode-1 内存;
    workspace 改动直接落 host 文件,用户能直接 review)
```

**抗污染 + 持久化校验点**:

| 时机 | 校验 |
|---|---|
| 节点 create 后 | `docker exec <id> ls /work/tenant-A/project-1/.skills/` 可见 skill |
| 节点 create 后 | `docker exec <id> bash -c "echo x > /work/tenant-A/project-1/.skills/flight-query/SKILL.md"` 失败 (RO) |
| chat 进行中 | `docker exec <id> ls /root/.claude/skills/` 不存在 (opencode 没用这里) |
| chat 进行中 | `docker exec <id> env \| grep -i key` 看到 `ANTHROPIC_API_KEY` / `FLIGHT_API_KEY` 等 (env 挂载验证) |
| chat 进行中 | `ls /work/tenant-A/project-1/` 在 host 上能直接看到 agent 改的文件 ✓ |
| 节点 **stop** 后 | `docker start opencode-1` 起来,环境全保留 (skill / history / installed packages) |
| 节点 **rm** 后 | 容器删,**host 上** `/work/tenant-A/project-1/` 还在 (workspace 是 host bind,不是容器层) |

### 6.4 节点 lifecycle 决策 (v0.3: 拆 container 和 agent 状态)

```
                  create              run (start)            stop            rm
   (none) ─────────────────▶ created ─────────▶ running ─────────▶ stopped ─────────▶ removed
                                │                  │  ↑                 │                │
                                │ rm               │ run               │ run            │ (终态)
                                ▼                  │  │                 │                │
                            removed                └──┘─────────────────┘                │
                                                                                          │
   persistent 模式: stop 保留容器层,rm 才清                                              │
   ephemeral  模式: stop 触发自动 rm (敏感场景)  ────────────────────────────────────────┘
```

**Hub 决策表**:

| 状态 | 动作 | 内部操作 |
|---|---|---|
| `created` | `run` | `docker start` → 容器层启,entrypoint.sh 跑,opencode serve 起来 |
| `running` | `stop` | `docker stop` (SIGTERM, 等 10s) → opencode 优雅退出,容器层保留 |
| `stopped` | `run` | `docker start` → 复用容器层,entrypoint.sh 跑,opencode 起来,history 保留 |
| `stopped` | `rm` | `docker rm` → 容器层清,host workspace 不动 |
| `running` (unhealthy) | 自动 `run` | `docker restart` (等同 stop+start) |
| `running` (ephemeral) | `stop` | `docker stop` + 立即 `docker rm` |

### 6.5 Clone Mode (v0.3 新增) ★

**问题**: 用户让 2 个 agent 同时改同一 repo (e.g. 一个改 feature-a,一个改 feature-b),direct mode 下它们会互相冲突。

**解法 (git 隔离,多 agent 并行)**:

```
Host 上:
  /work/tenant-A/project-1/       ← host repo (ro 挂到 sandbox)
  
Sandbox 内:
  /work/tenant-A/project-1/       ← ro bind mount (read-only!)
  /home/opencode/clone/           ← ★ sandbox 内私有 git clone (rw)
  ├─ .git/                        ← git daemon 暴露成 sandbox-<id> remote
  └─ (working tree)
  
  agent 改文件 → 写到 /home/opencode/clone/ → commit
  host 用户 → git fetch sandbox-<id> → 拿到 agent 的 commits
```

**实现要点**:
- Hub 调 `git clone --reference` 复用 host repo 的对象 (省空间, 加速)
- sandbox 内跑 `git daemon --base-path=/home/opencode/clone --export-all`
- Hub 在 host 用户的 `~/.gitconfig` 注册 remote: `sandbox-<id> = http://<sandbox-git-port>`
- agent 提交时自动 commit 到新分支 (可配置默认分支名)

**API**:

```bash
# 启 clone mode sandbox
POST /sandboxes
  {
    "agent": "opencode",
    "workspace": {
      "host_path": "/work/tenant-A/project-1",
      "mode": "clone",         # ★ v0.3 新增
      "default_branch": "agent/sandbox-001"
    }
  }
  → 201 {
    "id": "sandbox-001",
    "git_remote": "http://opencode-1:9418/sandbox-001",
    "default_branch": "agent/sandbox-001"
  }

# 用户在 host 上 fetch
$ git fetch sandbox-001
$ git log sandbox-001/agent/sandbox-001
$ git diff main..sandbox-001/agent/sandbox-001
$ git checkout -b feature-a sandbox-001/agent/sandbox-001
$ git push -u origin feature-a
$ gh pr create
```

**限制**:
- workspace 必须是 git repo
- 不能在 git worktree 里跑 (`.git` 是 pointer file,ro mount 解析不了)
- `mode: clone` 是 **create-time flag**,改 mode = rm + 重建

### 6.6 Port Forwarding (v0.3 新增)

**场景**: opencode 跑 `npm run dev`,dev server 在 sandbox 的 0.0.0.0:3000,用户要 host 浏览器访问。

**API**:

```bash
# 转发 host 8080 → sandbox 3000
POST /sandboxes/opencode-1/ports
  {"sandbox_port": 3000, "host_port": 8080}
  → 200 {"host_port": 8080, "sandbox_port": 3000}

# host_port 留空 = 随机分配
POST /sandboxes/opencode-1/ports
  {"sandbox_port": 3000}
  → 200 {"host_port": 32768, "sandbox_port": 3000}

# 查询
GET /sandboxes/opencode-1/ports
  → 200 {"mappings": [
    {"host_port": 8080, "sandbox_port": 3000, "protocol": "tcp"}
  ]}

# 取消
DELETE /sandboxes/opencode-1/ports/8080
  → 204
```

**实现**: Hub 在 host 上跑 `socat TCP-LISTEN:8080,fork,reuseaddr TCP:opencode-1:3000`。
或: 直接 `docker port` 走 docker 自身的端口映射 (简单但要 restart 容器)。

**注意 (loopback 隔离的坑)**:
- sandbox 内服务必须 bind `0.0.0.0`,不能 `127.0.0.1` (容器 loopback 跟 host loopback 不是同一个)
- host 端口冲突 → 409
- 不持久化: `stop` 后端口映射失效, `start` 后要重新 publish

---

## 7. 关键决策表 (v0.3 修订)

| 决策点 | 选项 | 推荐 (v0.3) | 理由 |
|---|---|---|---|
| **隔离层** | Docker / gVisor / Firecracker / Kata | **Docker + --read-only** | 开发友好,资源限制够用;Phase 5 评估 gVisor |
| **持久化策略** | tmpfs 销毁即清 / bind 持久 | **bind 持久 (rm 才清)** | 保留 agent 工作进度,跟 stop/rm lifecycle 对齐 |
| **Workspace 路径** | 容器内 /workspace / host 绝对路径 | **host 绝对路径** | agent 看到的路径跟 host 一致,错误信息可直接用 |
| **Workspace 模式** | direct / clone | **direct (默认) + clone (opt-in)** | direct 边改边 review,clone 多 agent 并行 |
| **网络出站** | 直连 / host 代理 | **直连 (env 凭证)** | 简单;MVP 阶段可接受;sandbox 攻破 = key 泄露,Phase 5 再评估 egress |
| **凭证存放** | sandbox 内 env / host 代理注入 | **sandbox env (`docker run -e`)** | 简单,跟 docker 原生;**不隔离凭证,sandbox 攻破 = key 泄露** |
| **Skill 分发时机** | create 时挂 / 运行时注入 | **create 时挂** | docker 不支持运行时改 bind mount |
| **Skill 防写** | chmod a-w / chattr +i / ro bind | **ro bind mount** | 内核 EROFS,root 改不动 |
| **Workspace 类型** | tmpfs / volume / bind | **bind mount (默认) / tmpfs (ephemeral 模式)** | v0.3 转向,持久优先 |
| **容器根 FS** | rw / ro | **--read-only** | 防 opencode 写镜像层 |
| **opencode 配置** | env / config 文件 / CLI 参数 | **config 文件** (从 policy.json 渲染) | 可审计、可版本化 |
| **Skill 发现机制** | `~/.claude/skills/` / `directory` 向上扫 / `cfg.skills.paths` | **`cfg.skills.paths`** | 显式指定,不污染全局 |
| **状态** | 有状态 / 无状态 | **节点有状态 + Hub 无状态** | 跟 opencode 模型对齐 |
| **启动** | 冷启 / 预热池 | **直接冷启 (`docker compose up` / `docker run`)** | 容器 1~3s 起;用原生 Docker CLI |
| **健康检查** | docker healthcheck / 自定义 | **容器内 http /healthz** | 区分"启动中"和"挂了" |
| **路由策略** | sticky / least_sessions / round_robin / weighted | **sticky_session (默认)** | 保留 opencode session 上下文 |
| **集群发现** | 静态配置 / 注册中心 / DNS / env | **环境变量 OPENCODE_NODES** | 2~3 节点规模够用 |
| **故障转移** | 客户端重试 / Router 自动迁移 | **Router 检测 unhealthy → restart** | sandbox 持久化,restart 不丢状态 |
| **端口转发** | 不支持 / docker port / socat | **Hub API + socat** | agent 跑 dev server 时用户要访问 |
| **Docker daemon 隔离** | 共享 host / 独立 daemon | **共享 host** | opencode 不起子容器,不需要独立 daemon |
| **沙箱 wrapper 依赖** | 第三方 `sbx` / 原生 docker CLI | **原生 `docker` CLI** | 少一层抽象,运维跟生产环境一致 |

---

## 8. 实施路线 (5 阶段, v0.3 调整)

### Phase 1 — 单 opencode 容器 + 持久化 (3-5 天)

**目标**: 跑通"起容器 → 注入 skill/workspace → 跑 opencode → 验 workspace 跟 host 一致 + 验不污染 + 验 rm 才清",**不接 Hub**。

**交付物**:
- `docker/Dockerfile.opencode-sandbox` — 基础镜像
- `docker/entrypoint.sh` — 容器内启动脚本 (读 policy.json → 渲染 config.json)
- `docker/health_server.py` — /healthz 实现
- `docker/render_config.py` — policy → opencode config 渲染
- `scripts/spawn_node.sh` — 手工 spawn 脚本
- `tests/manual/test_node_smoke.sh` — 烟测脚本

**Dockerfile 草案** (v0.3: 不再需要 egress CA 证书):

```dockerfile
FROM node:20-slim

# opencode CLI
RUN npm install -g opencode-ai@latest

# 准备路径
RUN mkdir -p /opt/sandbox /root/.config/opencode

# 复制 sandbox 内部件
COPY entrypoint.sh /opt/sandbox/entrypoint.sh
COPY health_server.py /opt/sandbox/health_server.py
COPY render_config.py /opt/sandbox/render_config.py
RUN chmod +x /opt/sandbox/entrypoint.sh

EXPOSE 7777 8080
ENTRYPOINT ["/opt/sandbox/entrypoint.sh"]
HEALTHCHECK --interval=5s --timeout=2s CMD curl -f http://127.0.0.1:7777/healthz || exit 1
```

**entrypoint.sh 草案** (v0.3: 不再注入 proxy env,凭证由 `docker run -e` 提供):

```bash
#!/bin/bash
set -e

# 1. 启动 health server
python3 /opt/sandbox/health_server.py &

# 2. 渲染 opencode config (从 policy.json → config.json)
if [ -f /opt/sandbox/policy.json ]; then
    python3 /opt/sandbox/render_config.py \
        --policy /opt/sandbox/policy.json \
        --output /root/.config/opencode/config.json
fi

# 3. 启动 opencode serve (凭证从 env 读,直接连 LLM / 业务 API)
#    - ANTHROPIC_API_KEY / OPENAI_API_KEY / FLIGHT_API_KEY 等已由 docker run -e 注入
#    - opencode 进程内可直接读 env

exec opencode serve \
    --port 8080 \
    --hostname 127.0.0.1 \
    --config /root/.config/opencode/config.json
```

**Phase 1 验收** (v0.3 重点):
- [ ] 镜像构建成功
- [ ] `docker run -v /work/p1:/work/p1 ...` 起容器,容器内 `pwd` 显示 `/work/p1`,**不是** `/workspace`
- [ ] 容器内 `ls /work/p1/.skills/flight-query/` 可见 skill (ro bind)
- [ ] 容器内 `echo x > /work/p1/.skills/flight-query/SKILL.md` 失败 (Read-only file system)
- [ ] 容器内 `ls /root/.claude/skills/` 不存在
- [ ] 容器内 `echo test > /work/p1/foo.txt`,**host 上** `/work/p1/foo.txt` 立即可见 (bind mount 验证)
- [ ] `docker stop` 后,容器状态 stopped,容器层保留
- [ ] `docker start` 后,opencode 起来,环境全保留 (history / installed packages)
- [ ] `docker rm` 后,host 上 `/work/p1/` 还在 (workspace 是 host bind,不是容器层)
- [ ] `docker exec <id> env | grep KEY` 能看到 `ANTHROPIC_API_KEY` / `FLIGHT_API_KEY` (env 挂载验证)

### Phase 2 — 集群 + Hub Router (1-2 周)

**目标**: 2~3 个 opencode 容器 + Hub 做路由,`POST /agent/chat` 走 Hub 分配到节点。**凭证走 env 挂载,不做 egress 代理**。

**新增模块**:
- `src/openagent/sandbox/router.py` (L2, ~250 行) — HubRouter + SessionTable + 4 种策略
- `src/openagent/sandbox/node.py` (L3, ~150 行) — OpencodeNode 数据类 + healthcheck
- `src/openagent/sandbox/skill_bundle.py` (L3, ~150 行) — bundle 定义 + digest 计算
- `src/openagent/sandbox/policy_renderer.py` (L3, ~100 行) — `policy.json` → opencode `config.json`
- `src/openagent/providers/launcher.py` (改造) — 保留旧 API,内部从 `Popen` 切到 `HubRouter`

**docker-compose.yml** (v0.3: 凭证走 env,egress sidecar 移除):

```yaml
version: '3.8'

x-opencode-template: &opencode-template
  build:
    context: ./docker/opencode-sandbox
  read_only: true
  cap_drop: [ALL]
  security_opt: [no-new-privileges]
  tmpfs:
    - /tmp:size=100m
  mem_limit: 2g
  cpus: 2
  environment:                                    # ★ v0.3: 凭证走 env
    ANTHROPIC_API_KEY: "${ANTHROPIC_API_KEY:?required}"
    OPENAI_API_KEY: "${OPENAI_API_KEY:-}"
    FLIGHT_API_KEY: "${FLIGHT_API_KEY:-}"
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:7777/healthz"]
    interval: 5s
    timeout: 2s
    retries: 3
  networks: [sandbox-net]

networks:
  sandbox-net:
    driver: bridge

services:
  opencode-1:
    <<: *opencode-template
    hostname: opencode-1
    container_name: opencode-1
    volumes:
      - /work/tenant-A/project-1:/work/tenant-A/project-1    # ★ v0.3: host 绝对路径
      - /work/shared/skills/flight-query:/work/tenant-A/project-1/.skills/flight-query:ro

  opencode-2: { <<: *opencode-template, hostname: opencode-2, container_name: opencode-2, ... }
  opencode-3: { <<: *opencode-template, hostname: opencode-3, container_name: opencode-3, ... }

  hub:
    build:
      context: .
      dockerfile: docker/Dockerfile.hub
    container_name: openagent-hub
    ports: ["8000:8000"]
    environment:
      OPENCODE_NODES: "http://opencode-1:8080,http://opencode-2:8080,http://opencode-3:8080"
      ROUTING_STRATEGY: "sticky_session"
    depends_on:
      opencode-1: { condition: service_healthy }
      opencode-2: { condition: service_healthy }
      opencode-3: { condition: service_healthy }
    networks: [sandbox-net]
```

**两种部署方式都支持** (跟 v0.2 一致, 无变化):

```bash
# 方式 A: docker-compose 一并起
docker compose up -d

# 方式 B: 独立启动
docker run -d --name opencode-1 --network sandbox-net --hostname opencode-1 \
  -v /work/tenant-A/project-1:/work/tenant-A/project-1 \
  -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
  -e FLIGHT_API_KEY="$FLIGHT_API_KEY" \
  --read-only --cap-drop ALL --security-opt no-new-privileges \
  opencode-sandbox:base-v1.4

docker run -d --name openagent-hub -p 8000:8000 \
  -e OPENCODE_NODES="http://opencode-1:8080" \
  -e ROUTING_STRATEGY=sticky_session \
  openagent-hub:latest
```

**Phase 2 验收**:
- [ ] `pytest tests/test_router.py` 全过 (4 种路由策略)
- [ ] `docker compose up -d` 一次起 4 个容器 (3 opencode + hub)
- [ ] `curl POST /agent/chat` 走通,opencode 直连 LLM / 业务 API
- [ ] sandbox 内 `echo test > /work/p1/foo.txt` → host 上 `/work/p1/foo.txt` 立即可见
- [ ] 凭证 env 注入: `docker exec <id> env | grep -E 'ANTHROPIC_API_KEY|FLIGHT_API_KEY'` 都能看到
- [ ] 同一 session 连续 5 次,每次命中**同一节点** (sticky)
- [ ] 杀 opencode-1,Hub 5s 内检测 unhealthy,自动 restart (不丢环境)
- [ ] `/ready` 报告所有节点状态

### Phase 3 — Clone Mode + Port Forwarding (1 周)

**目标**: 支持多 agent 并行改同一 repo + agent 跑 dev server 时用户能访问。

**新增**:
- `src/openagent/sandbox/clone_mode.py` (~200 行) — git clone 编排 + git daemon 配置 + host remote 注册
- `src/openagent/sandbox/port_forwarder.py` (~100 行) — socat 端口映射
- Hub API 新增: `POST /sandboxes/{id}/ports`, `POST /sandboxes` 加 `workspace.mode=clone`

**Phase 3 验收**:
- [ ] clone mode 启动后,host 上 `git fetch sandbox-<id>` 能拿到 agent 的 commits
- [ ] 2 个 clone mode sandboxes 改同一 repo,**互不冲突** (各 commit 各的)
- [ ] `POST /sandboxes/{id}/ports` 后,host 浏览器能访问 sandbox 内的 dev server
- [ ] `sandbox 内 service bind 127.0.0.1` 时 publish 失败 (明确错误信息)

### Phase 4 — 容量压测 + 监控 (1 周)

**目标**: 知道 1 个节点能并发多少 session,知道系统极限在哪。

**交付物**:
- `tests/load/test_node_capacity.py` — 单节点压测
- `tests/load/test_cluster_capacity.py` — 集群压测
- `work/logs/sandbox/` 目录 — 节点日志聚合
- Prometheus exporter (可选, Phase 5 再定)

**Phase 4 验收**:
- [ ] 测出单节点 session 上限 (目标 25+, 实测后填进 §3.1)
- [ ] 测出集群 QPS 上限
- [ ] 监控看板: 各节点 session 数 / 内存 / CPU / 错误率 / 出站流量

### Phase 5 — 高级特性 (按需)

**触发条件** (满足任一即上):
- 单 host 节点数 ≥ 20 → 评估 sandbox pool / gVisor
- 需要跨可用区部署 → K8s
- 业务 SLA 要求 P99 < 500ms → 全链路优化
- 客户需要 microVM 隔离 → 评估 microVM (gVisor / Firecracker)

**不在 MVP 范围**:本文 v0.3 不实现。

---

## 9. 失败模式 & 兜底

| 失败模式 | 兜底 |
|---|---|
| Agent 用 `..` 越权访问 workspace | `os.path.realpath` 规范化 (应用层 plan 管) |
| Agent 用 symlink 逃逸 | tmpfs 不持久化,逃出去也写不到 (Runtime 层兜底) |
| `opencode serve` 启动失败 | 节点 `state=unhealthy`,Hub 标记,流量路由到其他节点 |
| 节点 OOM | `--memory 2g` 内核强杀,Hub 检测 unhealthy 3 次后 `stopped` |
| 节点跑满 CPU | `--cpus 2` cgroup 限制,不影响宿主 |
| 网络外联 (skill 偷偷 curl) | docker network policy + 容器 iptables 限制 (Phase 2 简化,Phase 5 评估 egress) |
| 节点失联 | Hub 15s 心跳超时,标记 unhealthy,新请求不路由到该节点;**粘性 session 失效** |
| 粘性 session 失效 | 客户端重试 → Hub 重新选节点 (session in-memory 状态丢失,可接受) |
| 磁盘写满 (bind 模式 workspace) | 节点用 tmpfs,不存在此问题 |
| skill 版本冲突 (2 个 skill 同名不同 version) | bundle.id 含 version,bundle.digest 含内容,无歧义 |
| docker 运行时不能改 bind mount | skill 在节点启动时挂,变更 = 滚动重启节点 |
| `chmod a-w` 后 root 还能改 | 用 ro bind mount 兜底 (mount flag 在 host 侧) |
| 节点跑挂但容器没退 | healthcheck 5s 一次,3 次失败 docker kill |

---

## 10. 与现有功能的关系

| 现有模块 | 与本方案的关系 |
|---|---|
| `src/openagent/providers/launcher.py` (L4) | **演进目标** — `EngineLauncher` 内部从 `Popen` 切到 `HubRouter`;保持 API 兼容 |
| `src/openagent/scenarios/middleware.py` (L1) | 调用方不变,`request.ctx.scenario` 仍带 skills / model / scenario_id |
| `src/openagent/scenarios/router.py` (L2) | 不动;skill 列表从 `scenario.skills` 透传给 HubRouter |
| `src/openagent/skills/registry.py` (L3) | **复用** — `SkillRegistry.get(name)` 给出元数据,加 `local_path` 字段后透传给节点 |
| `src/openagent/policy/engine.py` (L5) | **复用** — `EffectivePolicy` 序列化成 `policy.json` 写容器内 `/opt/sandbox/` |
| `docs/design/agent-sandbox-plan.md` (L5) | **互补** — 见 §0,本文不重复应用层策略 |
| `docs/design/opencode-skill-and-workspace-constraint.md` | **共存** — 那篇讲"opencode 进程内怎么发现 skill" (`cfg.skills.paths`),本文讲"skill 怎么进容器" (ro bind mount),两者协作 |
| `work/cache/opencode-configs/` | 旧 launcher 的产物,Phase 2 后不再写入,保留只读历史 |
| `work/scenarios/*/skills/` | **复用** — 中心服务的 skill 源目录,Hub 启动时按 `scenario.skills` 列表把目录 ro bind mount 到各节点 |

---

## 11. 验证清单 (E2E, v0.3 修订)

### 11.1 抗污染 + 持久化验证 (每次 Phase 结束必跑, v0.3 修订)

```python
async def test_skill_isolation_no_pollution():
    """skill 注入不污染 ~/.claude/skills/, host workspace 不被 skill 污染"""
    # 启动节点,挂载 skill 到 host workspace 内的 .skills/
    node = await spawn_node(
        skills=["flight-query"],
        workspace_host_path="/tmp/test-p1",
    )
    await wait_ready(node)
    
    # 验证 1: 节点内 ~/.claude/skills/ 不存在 (opencode 走 cfg.skills.paths)
    r = await node.exec("ls /root/.claude/skills/ 2>&1 || true")
    assert "No such file" in r.output or "cannot access" in r.output
    
    # 验证 2: 节点内 skill 只读 (ro bind mount)
    r = await node.exec("bash -c 'echo x > /tmp/test-p1/.skills/flight-query/SKILL.md'")
    assert r.exit_code != 0
    assert b"Read-only" in r.output or b"Operation not permitted" in r.output
    
    # 验证 3: workspace 路径保持 host 绝对路径
    r = await node.exec("pwd && ls /tmp/test-p1/.skills/")
    assert r.output.startswith(b"/tmp/test-p1")  # 不是 /workspace
    assert b"flight-query" in r.output


async def test_workspace_persistence_v0_3():
    """v0.3 关键: stop 保留环境,rm 才清"""
    # 1. 起节点,装个包,改个文件
    node = await spawn_node(workspace_host_path="/tmp/test-p2")
    await wait_ready(node)
    
    await node.exec("apt-get install -y htop 2>/dev/null || npm install -g cowsay")
    await node.exec("echo 'session data' > /tmp/test-p2/state.txt")
    
    # 2. stop
    await node.stop()
    assert node.container_state == "stopped"
    
    # 3. host 上 workspace 文件还在 (host bind,不是容器层)
    assert Path("/tmp/test-p2/state.txt").exists()
    assert Path("/tmp/test-p2/state.txt").read_text() == "session data\n"
    
    # 4. start 回来
    await node.start()
    await wait_ready(node)
    
    # 5. 验证: 装的包还在 (容器层保留)
    r = await node.exec("which htop || which cowsay")
    assert r.exit_code == 0, "stop 后包丢了 - v0.3 持久化失败"
    
    # 6. 验证: state.txt 还在
    r = await node.exec("cat /tmp/test-p2/state.txt")
    assert b"session data" in r.output
    
    # 7. rm
    await node.rm()
    assert node.container_state == "removed"
    
    # 8. host 上 workspace 文件**还在** (workspace 是 host bind,不在容器层)
    assert Path("/tmp/test-p2/state.txt").exists()
    assert Path("/tmp/test-p2/state.txt").read_text() == "session data\n"
```

### 11.2 凭证 env 验证 (v0.3 新增)

```python
async def test_credentials_env_mounted():
    """v0.3: 凭证走 docker run -e,sandbox 启动后 env 可见"""
    node = await spawn_node(
        workspace_host_path="/tmp/test-p3",
        env={
            "ANTHROPIC_API_KEY": "sk-test-123",
            "FLIGHT_API_KEY": "flight-test-456",
        },
    )
    await wait_ready(node)

    # 验证 1: 容器内 env 能看到注入的 key
    r = await node.exec("env | grep -E 'ANTHROPIC_API_KEY|FLIGHT_API_KEY'")
    assert b"sk-test-123" in r.output
    assert b"flight-test-456" in r.output


async def test_credentials_not_in_policy():
    """v0.3: policy.json 不含 key 值,只声明 key 名"""
    policy = json.loads(Path("/opt/sandbox/policy.json").read_text())
    assert "ANTHROPIC_API_KEY" not in policy
    assert "FLIGHT_API_KEY" not in policy


async def test_no_egress_proxy_running():
    """v0.3: 不该有 egress proxy 容器 / 进程"""
    r = await host_shell("docker ps --format '{{.Names}}'")
    assert b"egress-proxy" not in r.output
    r = await host_shell("ss -tlnp | grep ':3129' || true")
    assert b":3129" not in r.output
```

### 11.3 Clone Mode 验证 (v0.3 新增)

```python
async def test_clone_mode_isolation():
    """★ v0.3: 多 agent 并行改同一 repo, 互不冲突"""
    # 假设 /tmp/test-repo 是 git repo
    repo_path = "/tmp/test-repo"
    subprocess.run(["git", "init", repo_path], check=True)
    subprocess.run(["git", "-C", repo_path, "commit", "--allow-empty", "-m", "init"], check=True)
    
    # 起 2 个 clone mode sandboxes
    sb1 = await spawn_node(workspace={"host_path": repo_path, "mode": "clone"}, 
                            name="agent-a")
    sb2 = await spawn_node(workspace={"host_path": repo_path, "mode": "clone"}, 
                            name="agent-b")
    
    # agent A 改 file-a
    await sb1.exec("echo 'A change' > /home/opencode/clone/file-a.txt")
    await sb1.exec("cd /home/opencode/clone && git add . && git commit -m 'A change'")
    
    # agent B 改 file-b
    await sb2.exec("echo 'B change' > /home/opencode/clone/file-b.txt")
    await sb2.exec("cd /home/opencode/clone && git add . && git commit -m 'B change'")
    
    # 验证: 两个 agent 各自 commit,互不可见
    r1 = await sb1.exec("cd /home/opencode/clone && git log --oneline")
    assert b"A change" in r1.output
    assert b"B change" not in r1.output  # sb1 看不到 sb2 的 commit
    
    r2 = await sb2.exec("cd /home/opencode/clone && git log --oneline")
    assert b"B change" in r2.output
    assert b"A change" not in r2.output
    
    # 验证: host 上 fetch 各 sandbox remote
    # (git remote 由 Hub 自动注册到 host 的 .gitconfig)
    out = subprocess.run(["git", "-C", repo_path, "fetch", "sandbox-agent-a"], 
                         capture_output=True).stdout
    out = subprocess.run(["git", "-C", repo_path, "fetch", "sandbox-agent-b"], 
                         capture_output=True).stdout
    
    # 验证: host repo 本身**没**被 agent 改动 (direct mode 才改)
    assert not (Path(repo_path) / "file-a.txt").exists(), "clone mode 不应改 host repo"
    assert not (Path(repo_path) / "file-b.txt").exists(), "clone mode 不应改 host repo"
```

### 11.4 集群路由验证 (跟 v0.2 一样)

```python
async def test_sticky_session_routing():
    """同 session_id 永远路由到同一节点"""
    router = HubRouter(strategy="sticky_session", nodes=[n1, n2, n3])
    
    decision1 = await router.route(session_id=None, prompt="hi")
    node1_id = decision1.node.id
    
    for _ in range(10):
        decision = await router.route(session_id=decision1.session_id, prompt="x")
        assert decision.node.id == node1_id, "sticky 失效"


async def test_unhealthy_node_auto_restart():
    """v0.3 关键: 节点 unhealthy 后, Hub 自动 restart (不丢环境)"""
    router = HubRouter(...)
    n1 = await create_node(workspace="/tmp/p")
    
    # opencode 挂了 (容器层还在)
    n1.container_state = "running"
    n1.agent_state = "unhealthy"
    
    # Hub 检测 → restart
    await router.heartbeat_loop.__wrapped__()  # 强制跑一次
    await asyncio.sleep(2)
    
    # restart 成功,容器状态回到 running,环境保留
    assert n1.agent_state == "ready"
    # workspace 还在
    r = await n1.exec("ls /tmp/p/")
    assert r.exit_code == 0
```

### 11.5 Port Forwarding 验证 (v0.3 新增)

```python
async def test_port_forwarding():
    """sandbox 内 dev server 通过 host 端口访问"""
    sb = await spawn_node(workspace="/tmp/p")
    await wait_ready(sb)
    
    # sandbox 内起个 http server
    await sb.exec("python3 -m http.server 3000 --bind 0.0.0.0 &")
    await asyncio.sleep(2)
    
    # publish host 8080 → sandbox 3000
    mapping = await hub.publish_port(sb.id, sandbox_port=3000, host_port=8080)
    assert mapping.host_port == 8080
    
    # host 访问
    r = await http_client.get("http://localhost:8080/")
    assert r.status_code == 200
    
    # 注意: 0.0.0.0 必须,127.0.0.1 不行
    # (sandbox loopback 跟 host loopback 不同)


async def test_port_forwarding_127_blocked():
    """sandbox 内 bind 127.0.0.1 时 publish 应给明确错误"""
    sb = await spawn_node(workspace="/tmp/p")
    await sb.exec("python3 -m http.server 3000 --bind 127.0.0.1 &")
    await asyncio.sleep(2)
    
    with pytest.raises(PortPublishError, match="127.0.0.1"):
        await hub.publish_port(sb.id, sandbox_port=3000, host_port=8080)
```

### 11.6 资源限制验证 (跟 v0.2 一样)

```python
async def test_memory_limit():
    node = await spawn_node(workspace="/tmp/p", mem_limit="512m")
    r = await node.exec("python3 -c 'x=[]; [x.append(b\"x\"*10**7) for _ in range(10**4)]'")
    assert r.exit_code == 137  # OOM kill
```

### 11.7 部署验证

```bash
$ docker compose up -d
[+] Running 4/4
 ✔ Container opencode-1    Started
 ✔ Container opencode-2    Started
 ✔ Container opencode-3    Started
 ✔ Container openagent-hub  Started

$ curl http://localhost:8000/ready
{"ok": true, "nodes": [...]}
```

---

## 12. 决策记录 (v0.3 修订)

1. **集群规模默认 3 节点** — 用户指定 2~3,默认 3 (允许 1 个挂掉还能服务)
2. **路由策略默认 sticky_session** — 保留 opencode session 上下文,代价是负载可能不均
3. **Skill 分发时机: create 时挂** — docker 不支持运行时改 bind mount;运行中加 skill = rm + 重建
4. **节点数 vs session 数** — 集群算"opencode 进程数",不直接对应 session 数 (1 节点 25 session)
5. **节点内存默认 2G** — opencode serve idle ~200MB,满载 ~500MB;留 buffer 给工具调用
6. **Hub 状态持久化** — SessionTable 默认 in-memory,重启丢;Phase 4 加 Redis (可选)
7. **★ v0.3 凭证走 env 挂载** — **Phase 2 简化**:`docker run -e` 注入 `ANTHROPIC_API_KEY` / 业务 API key;**不引入 egress 代理**;**sandbox 攻破 = key 泄露,MVP 接受这个风险**,Phase 5 按需评估 egress 代理
8. **沙箱池 / 预热池** — **不在 MVP**;Phase 5 按需
9. **单容器 session 上限 50** (待压测验证,见 Phase 4)
10. **★ v0.3 idle 超时策略** — 节点 idle 后**不**自动 stop;只在资源压力时 evict
11. **★ v0.3 持久化策略** — 默认 `mode=persistent` (跟容器 stop 保留、rm 才清对齐),`mode=ephemeral` 是 opt-in
12. **★ v0.3 workspace 路径** — 默认 host 绝对路径 bind mount (v0.1 用的 `/workspace` 已弃)
13. **★ v0.3 clone mode** — Phase 3 实现,支持多 agent 并行
14. **★ v0.3 port forwarding** — Phase 3 实现,支持 dev server 暴露
15. **★ v0.3 凭证管理** — LLM key / 业务 API key 走 `docker run -e` 注入;**sandbox 进程内可见**(不是隔离),MVP 接受这个 trade-off;Phase 5 评估是否需要 egress 代理做隔离
16. **★ v0.3 opencode 不读 user-level config** — 用户级 `~/.claude/` 配置在 sandbox 内不存在;只走 project-level (cwd) + cfg.skills.paths

---

## 13. 关联文档

- `docs/design/agent-sandbox-plan.md` — 应用层权限策略 (tool_level/workspace_dirs/network)
- `docs/design/opencode-skill-and-workspace-constraint.md` — opencode 进程内 skill 发现机制
- `docs/design/integrated-orchestration-plan.md` — Hub 整体架构 (§4 资源目录, §12 接口契约)
- `docs/design/scenario-routing-proposal.md` — scenario 路由方案 (§3 schema, §6 注入机制)
- `src/openagent/providers/launcher.py` — 当前 L4 引擎 launcher (改造目标)
- `CLAUDE.md` — 全局约束 (HARD CONSTRAINT: 统一对话入口,本文不新增 chat 端点)

---

## 14. 设计历史 (v0.1 → v0.2 → v0.3)

本文档经过 3 个版本迭代,核心是把"沙箱池"演进到"容器集群 + 中心调度":

```
v0.1 (旧设计)          v0.2 (重构)                v0.3 (当前)
─────────────────     ──────────────────       ─────────────────────────
沙箱池 + 预热池    →   容器集群 + Router      →   同 v0.2 + 持久化优先
每次 session 启    →   sticky session 复用    →   同 v0.2 + 路径保持 host
销毁即清          →   销毁即清                →   stop 保留,rm 才清
/tmpfs 强制        →   /workspace 强制         →   host 绝对路径 (bind)
无 egress 代理    →   简单 sandbox-net        →   ★ 凭证走 env 挂载,不引入 egress
无端口转发        →   无                      →   ★ Hub API + socat
无 clone mode     →   无                      →   ★ git 隔离多 agent
第三方 sandbox    →   第三方 sandbox wrapper  →   ★ 原生 docker / compose CLI
```

### 14.1 v0.3 关键设计点 (不依赖任何外部 sandbox wrapper)

1. **原生 Docker CLI 启动** — `docker create` / `docker start` / `docker stop` / `docker rm`,跟生产环境运维工具链一致;不引入第三方 `sbx` 之类 wrapper
2. **持久化优先** — `stop` 保留容器层 + 镜像 layer,`rm` 才清;`mode=ephemeral` (opt-in) 是反向
3. **workspace 保持 host 绝对路径** — `bind mount` 到 host 路径,容器内不重映射,agent 错误信息直接是 host 路径
4. **凭证走 env 挂载 (不做 egress)** — LLM API key / 业务 API key 走 `docker run -e` 进 sandbox;简单,跟 docker 原生;**sandbox 攻破 = key 泄露,MVP 接受这个风险**,Phase 5 评估是否需要 egress
5. **clone mode** — 多 agent 并行改同一 repo 时用 git 隔离
6. **port forwarding** — `socat` 把 host 端口映射到 sandbox 端口 (agent 跑 dev server 时用)

### 14.2 v0.3 不引入的部分 (避免范围蔓延)

- ❌ TUI interactive dashboard (Web UI 替代)
- ❌ Organization governance (付费功能,自建用不到)
- ❌ Saved sandbox as template (Phase 5 评估)
- ❌ MicroVM (Phase 5 评估)
- ❌ Template + Kit 分层 (单 image + policy.json 已够)
- ❌ **Egress 代理 / 中心凭证注入 / 域白名单集中管理** — MVP 阶段用 env 挂载;sandbox 攻破风险由应用层 + docker network policy 兜底
