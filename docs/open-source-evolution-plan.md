# OpenAgent 开源化演进方案

> 把当前 `agent-scheduler-hub` 演进为通用 Agent 基座并对外开源的执行计划。
>
> 基于代码现状(5 层架构 + 双 SDK + 飞鹤业务污染 + P0-P6 豁免债)给出,所有条目对应仓库内具体文件。
>
> 状态: **草案 / 待评审**,实施前请勿改动代码。

---

## 1. 背景与目标

### 1.1 现状定位

当前项目实质是一个 **opencode/claude-agent 双 SDK 调度中枢**,核心能力:

- `core/agent_pool.py` + `core/scheduler.py` —— Agent 实例池 + 任务编排
- `providers/` —— 双 SDK 适配 (opencode-ai + claude-agent-sdk)
- `scenarios/` + `skill_runtime/` + `auip/` —— 场景路由 + Skill 注入 + HITL 卡片协议
- `policy/` —— L5 安全边界 (path / command / network)
- `sandbox/runtime.py` —— Docker 沙箱启动
- `store/` —— PostgreSQL / Memory 持久化

### 1.2 目标定位

把以上能力沉淀为通用基座,后续所有 Agent 项目按此模式接入:

```
具体业务 (飞鹤 / 客服 / 代码 review / ...)
        ↓ scenario + skill + MCP 配置
        ↓
   OpenAgent Hub (协议适配 + 编排 + 安全策略 + AUIP)
        ↓ HTTP
   opencode serve (Agent 核心)
```

### 1.3 关键约束

- **不动 1 行业务代码,先评审本方案**
- 演进路线必须**渐进可发布**(每个 milestone 都能独立交付 alpha/beta)
- 现有飞鹤业务必须**剥离但不下线**(独立包持续可用)

---

## 2. 当前阻碍开源的硬伤

按"开源后用户立刻会踩的坑"排序。每条都对应具体文件,可直接定位。

| # | 问题 | 现位置 | 开源后果 |
|---|---|---|---|
| H1 | **业务污染核心** | `api/http/controllers/auth_controller.py` (505 行飞鹤代理)<br>`config/settings.py` §13 段 `feihe_*` 字段<br>`auip/flight_card.py` / `flight_query_presenter.py` / `_flight_mapping.py`<br>`work/scenarios/*flight*` / `*fh-*`<br>`scripts/verify_opencode_config.py` 调 feihe MCP | 用户 fork 后第一件事是删飞鹤代码,删完发现 settings / 启动流 / 测试全崩 |
| H2 | **硬编码模型名** | `scripts/verify_opencode_config.py` 写死 `MiniMax-M2.7-highspeed`<br>`docker/render_config.py` 同上 | 任何非内部模型直接报 `ProviderModelNotFoundError` |
| H3 | **命名分裂** | `pyproject.toml` `name = "agent-scheduler-hub"`<br>包名 `openagent`<br>README 标题 "Agent Scheduler Hub"<br>CLI `agent-scheduler` | PyPI / Docker / 文档 / CLI 四套名字,SEO 找不到 |
| H4 | **P0-P6 豁免债** | `scripts/ci_check.py` L86-128 `KNOWN_VIOLATIONS`<br>21 个文件超行 + 3 个 import 方向违规 | contributor 看到一堆反面教材,PR 不知道学哪个;豁免列表本身就是"这块别碰"的负面信号 |
| H5 | **前端绑定单一场景** | `frontend/` 整套机票卡片 / 差旅 UI | 通用基座的前端应该是 chat shell + scenario-driven UI 插槽 |
| H6 | **中文 only** | 所有 docstring / 注释 / error message / README / CLAUDE.md / AGENTS.md | 海外贡献者看不懂 |
| H7 | **无扩展点契约** | scenario / skill / MCP 都靠 `work/` 目录约定<br>provider 在 `agent_bridge.py` 硬 `if/else` 选 | 用户加自己的场景必须改 repo 代码或塞 work 目录,无法 `pip install openagent-provider-xxx` |
| H8 | **settings 体量失控** | `config/settings.py` 14 段 100+ 字段 | 新用户读不完,放弃配置 |
| H9 | **根目录有未解释文件** | `2.0.0`(2111 字节,无后缀)<br>`typescript`(无后缀)<br>`bake/` / `relate_project/`(无 README) | 首个 GitHub issue 必然问 "这是什么" |
| H10 | **缺开源治理文件** | 无 `LICENSE` 实体文件(仅 pyproject 声明 MIT)<br>无 `CONTRIBUTING.md` / `CODE_OF_CONDUCT.md` / `SECURITY.md` | 法律风险 + 贡献门槛 |

---

## 3. 演进路线:4 个 Milestone

### M1 — 内核剥离 (alpha 可发,预估 2-3 周)

**目标**: 把通用平台和飞鹤业务物理隔离。

#### 3.1.1 拆包结构

```
当前:  src/openagent/                  目标(双仓库):
├── api/        (含 auth_controller)   openagent-core/         <- PyPI 主包
├── config/     (含 feihe_*)           ├── core/scheduler
├── scenarios/  (通用)                  ├── providers/
├── policy/     (通用)                  ├── scenarios/   (registry+loader,
├── providers/  (双 SDK)                │                 不带任何具体 scenario)
├── auip/       (含 flight_*)          ├── skill_runtime/
└── store/                              ├── auip/        (cards 协议,
                                        │                 不含 flight_card)
                                        ├── store/
                                        └── api/         (chat/session/skills/pool
                                                          通用端点)

                                       openagent-feihe/        <- 独立 repo / 私有
                                       ├── controllers/auth_controller.py
                                       ├── scenarios/flight-booking/
                                       ├── auip/flight_card.py
                                       ├── auip/flight_query_presenter.py
                                       └── settings_ext.py
                                                  (feihe_base_url 等)
```

#### 3.1.2 插件加载机制

`openagent-core` 在 `api/app.py` 通过 entry_points 加载插件:

```python
# pyproject.toml of openagent-feihe
[project.entry-points."openagent.plugins"]
feihe_auth = "openagent_feihe.plugin:register"
```

`register(app, settings)` 函数职责:挂蓝图、追加 settings 字段、注册 scenario / skill / card。

#### 3.1.3 settings 可插拔

核心 settings 通过 `pydantic.BaseSettings` 继承允许插件追加字段。插件包自己定义 `FeiheSettings(BaseSettings)`,启动时合并。

#### 3.1.4 必须同步消化 `KNOWN_VIOLATIONS`

M1 拆完后,`scripts/ci_check.py` L86-128 的 21 个豁免应清零。具体目标:

| 文件 | 行数 | 处理方式 |
|---|---|---|
| `api/http/controllers/auth_controller.py` | 505 | 整体搬到 `openagent-feihe` |
| `api/http/controllers/chat_controller.py` | 超 200 | 拆 handler / formatter / streaming 子文件 |
| `providers/opencode/chat.py` | 1286 | **最大债**,按事件流 / 工具调用 / 状态机拆 3-4 文件 |
| `providers/opencode/lifecycle.py` | 328 | 拆 create / delete / abort 三块 |
| `core/suspendable_scheduler.py` | 超 250 | 拆 turn lifecycle / event emission |
| `store/base.py` / `store/postgres.py` | 超 200 | Schema 拆 DDL / models / queries |

#### 3.1.5 M1 完成定义 (DoD)

- [ ] `openagent-feihe` 独立 repo + 独立 pyproject + 独立 CI
- [ ] `openagent-core` 卸载所有 `feihe_*` 字段,启动不依赖飞鹤
- [ ] `scripts/ci_check.py` `KNOWN_VIOLATIONS` 为空
- [ ] `pip install openagent-core` + `pip install openagent-feihe` 行为等价于现状
- [ ] 现有所有 tests 通过

---

### M2 — 扩展协议化 (beta,预估 3-4 周)

**目标**: 用户不 fork 就能用。

#### 3.2.1 Provider SPI

当前 `providers/agent_bridge.py` 是硬 `if sdk_type == "opencode" else ...`,改成 registry:

```python
from openagent.providers import register_provider, AgentProvider

@register_provider("vllm")
class VLLMProvider(AgentProvider): ...
```

用户 `pip install openagent-provider-vllm` 即可接自建 LLM。

#### 3.2.2 三层协议标准化

| 层 | 当前 | 改造 |
|---|---|---|
| Scenario | `work/scenarios/*.scenario.yaml` 目录约定 | 增加 `entry_points = "openagent.scenarios"`,允许 pip 包贡献 scenario;`work/scenarios/` 退化为"用户级覆盖" |
| Skill | `SkillRegistry.load_from_paths()` 多目录扫 | 同上加 entry_points;`SKILL.md` frontmatter 用 JSON Schema 校验,`triggers` 字段强制 |
| MCP | `mcp_tools_config` inline JSON 或文件 | 加 `mcp.json` 标准文件格式(对齐 Anthropic MCP spec);允许 `mcps/*.mcp.yaml` 目录扫描 |

#### 3.2.3 AUIP Card 协议独立子包

`auip/cards.py` 的 Card 事件协议是项目最具差异化价值的资产(HITL 卡片化)。M2 抽成:

- `openagent-auip` —— 协议定义 + Python schema (Pydantic)
- `@openagent/auip-types` —— TypeScript 类型定义(npm)
- `docs/spec/auip-v1.md` —— 协议规范文档(独立版本号)

#### 3.2.4 前端拆 Shell + Slot

```
当前: frontend/                       目标:
├── 机票卡片                           @openagent/chat-shell    (npm 通用 chat + SSE
├── 飞鹤登录                                                     + AUIP card 渲染框架)
└── 通用 chat                          @openagent/card-flight    (机票卡片 slot)
                                       @openagent/feihe-auth     (业务侧组件)
```

shell 用 `<CardSlot type="flight" />` 注册机制,用户自己写 Card 组件 npm publish。

#### 3.2.5 M2 完成定义 (DoD)

- [ ] `openagent-core` 的 `agent_bridge.py` 无 if/else 硬判 sdk_type
- [ ] 至少 1 个外部 provider 包验证可用 (建议 vllm 或 ollama)
- [ ] AUIP 协议有独立版本号和 spec 文档
- [ ] frontend chat-shell 独立可 npm 发布,飞鹤 UI 作为消费方接入

---

### M3 — 工程化收口 (RC,预估 2-3 周)

#### 3.3.1 配置门面

拆 `config/settings.py` 14 段为多文件:

```
config/
├── settings/
│   ├── __init__.py      (聚合 + 兼容入口)
│   ├── server.py
│   ├── opencode.py
│   ├── storage.py
│   ├── skill.py
│   ├── mcp.py
│   ├── policy.py
│   ├── sandbox.py
│   ├── launcher.py
│   └── sse.py
```

每段 <= 100 行。环境变量前缀不变 (`AGENT_SCHEDULER_*`),保持向后兼容(M4 再考虑更名为 `OPENAGENT_*`)。

提供 `openagent init` CLI 交互式生成 `.env`(只问 5-6 个核心问题:LLM provider / API key / port / storage / 是否启用 sandbox)。

#### 3.3.2 文档双语 + 三层结构

```
docs/
├── en/                  Getting Started / Concepts / API Reference (英文)
├── zh/                  同上中文
├── adr/                 Architecture Decision Records (双语 OK)
│   ├── ADR-001-unified-chat-entry.md     <- 现 CLAUDE.md 那条 HARD CONSTRAINT
│   ├── ADR-002-5-layer-architecture.md
│   ├── ADR-003-auip-card-protocol.md
│   └── ...
├── spec/                协议规范
│   └── auip-v1.md
└── recipes/             "How to add a custom scenario" 等 cookbook
```

现有 `docs/design/*.md`(17 份)合并入 `adr/`,按时间编号 ADR-001 起。

#### 3.3.3 CI 重做

当前 `scripts/ci_check.py` 只本地跑。M3 要做:

- `.github/workflows/ci.yml`:lint → typecheck → unit → integration (mock opencode serve) → docker build smoke
- `.github/workflows/release.yml`:tag 触发 PyPI + GHCR 发布
- `.pre-commit-config.yaml`:ruff + mypy + ci_check.py
- **删豁免列表**:M1 已完成的前提下,`KNOWN_VIOLATIONS` 必须为空

#### 3.3.4 Sandbox 模式可选

当前 `sandbox/runtime.py` 绑死 Docker。改成 strategy:

| 模式 | settings 值 | 用途 |
|---|---|---|
| local | `AGENT_SCHEDULER_RUNTIME=local` | 单机进程,开发 / 小用户 |
| docker | `AGENT_SCHEDULER_RUNTIME=docker` | 当前默认 |
| k8s | `AGENT_SCHEDULER_RUNTIME=k8s` | 后续,大规模部署 |

抽 `SandboxRuntime` ABC,各模式独立实现。

#### 3.3.5 M3 完成定义 (DoD)

- [ ] `settings/` 拆分完成,每文件 <= 100 行
- [ ] `openagent init` 可用
- [ ] GitHub Actions CI 跑通,豁免列表为空
- [ ] 双语文档骨架建好(至少 Getting Started 双语)
- [ ] sandbox local 模式可用 (M4 前可选)

---

### M4 — 生态与发布 (持续运营)

| 项 | 内容 |
|---|---|
| **License** | 添加根目录 `LICENSE` 文件(MIT);每个源文件头加 `SPDX-License-Identifier: MIT` |
| **CONTRIBUTING.md** | 现 `.ai/AGENTS.md` 那套 5 层 + 行数硬上限是内部约束,要重写成 contributor 友好版本 |
| **CODE_OF_CONDUCT.md** | 标准 Contributor Covenant 2.1 |
| **SECURITY.md** | 漏洞报告流程,尤其 `policy/` 边界 case |
| **PyPI 发布** | `agent-scheduler-hub` 改为 `openagent` 或 `openagent-core`;首发 `0.1.0a1` |
| **Docker Hub / GHCR** | 现 `docker-compose.yml` 用 local 镜像,改成 `ghcr.io/<org>/openagent-hub:0.x` 拉取 |
| **CLI 扩展** | `agent-scheduler` 当前只启动 server,扩展为 `openagent {init, run, scenarios list, skill validate, mcp test, doctor}` |
| **Examples 仓库** | 创建 `openagent-examples` repo:travel-booking / code-review-bot / customer-support 三个开箱即用样例 |
| **Plugin 模板** | `cookiecutter-openagent-plugin` — 用户 1 分钟生成自己的 scenario / provider / skill 包 |

---

## 4. 立即可做的快速行动(本周,Quick Wins)

不用等 Milestone,这 3 步收益最大、成本最低,可立刻启动:

### Q1. 拆 auth_controller.py (505 行)

把飞鹤代理移到 `src/openagent_feihe/auth_controller.py`,在 `api/app.py` 用条件挂载:

```python
if settings.feihe_enabled:
    app.blueprint(feihe_auth_bp)
```

settings 里 `feihe_*` 字段同步搬走。`KNOWN_VIOLATIONS` 立刻少一条最大的债。

**预估**: 1 天。**风险**: 现有飞鹤集成测试需同步迁移。

### Q2. 改名收口

- `pyproject.toml`: `name = "agent-scheduler-hub"` -> `"openagent"`(若 PyPI 已占用则 `"openagent-hub"`)
- `README.md` 标题统一
- `[project.scripts]` 增加 `openagent = "openagent.main:main"`,保留 `agent-scheduler` 兼容别名

**预估**: 0.5 天。**风险**: docker / CI 引用名需同步。

### Q3. 写 EXTENSION_POINTS.md

列清当前**事实上**的扩展接口(协议未正式化前先文档化):

- `providers/base.py::AgentProvider` ABC
- `skills/registry.py::SkillRegistry.register`
- `mcp/registry.py::MCPRegistry.register_handler` / `register_remote`
- `scenarios/registry.py::ScenarioRegistry.register`
- `auip/cards.py` 的 Card 类型扩展
- 前端 CardRenderer 注册(待 M2 形式化)

**预估**: 0.5 天。**风险**: 无。

---

## 5. 风险点与公开讨论预案

| 风险 | 说明 | 预案 |
|---|---|---|
| R1 | **统一 chat 入口 (CLAUDE.md HARD CONSTRAINT)** 开源后会变讨论热点,贡献者会反复尝试加 per-scenario endpoint | `ADR-001` 明确写清"为什么不做",列历史教训(2026-06-03 P6 阶段加过被立刻删) |
| R2 | **HITL Card / SuspendableScheduler 文档散** 这块是项目最难懂也最值钱的部分,文档散在 `docs/design/book-flight-hitl-design.md` 等多处 | M2 必须出独立 "AUIP Card Protocol Specification" |
| R3 | **`_vendor/` 目录未审** 不确定是否 vendored 第三方代码 | 开源前完整 license 审计,若有不兼容代码立即清除 |
| R4 | **根目录散件**(`2.0.0` / `typescript` / `bake/` / `relate_project/`)未解释 | Q3 一并清理,要么 README 说明要么删除 |
| R5 | **work/ 与 tenant 数据** `work/tenant-A/` 可能含真实租户数据 | `.gitignore` 校验 + 开源前 git history 扫敏感数据 (`git-filter-repo` / `BFG`) |
| R6 | **opencode 上游不稳定** opencode-ai 当前 `>=0.1.0a0` 预发布版,接口可能 breaking | 在 README 标明对齐的 opencode 版本范围;CI 锁定一个稳定 tag 跑集成 |
| R7 | **AGENTS.md / CLAUDE.md 内部口吻** 现内容含"P0-P6 阶段"、"不要碰 P0-P6 代码"等内部上下文 | M4 重写,内部细节移到 `docs/internal/`(不开源)或 ADR |

---

## 6. 时间线与里程碑总览

```
W1-W3   M1  内核剥离      -> alpha
W4-W7   M2  扩展协议化    -> beta
W8-W10  M3  工程化收口    -> RC
W11+    M4  生态与发布    -> 公开 + 持续运营

并行: W1 启动 Quick Wins (Q1/Q2/Q3),不阻塞 M1
```

---

## 7. 决策待确认项

实施前需用户拍板:

| # | 问题 | 候选 |
|---|---|---|
| D1 | 主仓库命名 | `openagent` / `openagent-core` / `openagent-hub` |
| D2 | License | MIT(当前) / Apache-2.0(更利于企业采用) |
| D3 | 飞鹤包是否开源 | 独立私有 repo / 同组织独立公开 repo / 作为 examples 提供 |
| D4 | opencode 上游策略 | pin 版本 / 跟随 latest / fork 维护 |
| D5 | 双语优先级 | 中文优先 + 英文补齐 / 英文为主 + 中文翻译 |
| D6 | 治理模式 | BDFL / 核心维护者组 / 基金会托管 |
| D7 | Plugin 协议 timing | M1 就引入 / M2 引入 / 跟着用例长 |

---

## 8. 附录: 涉及的现存文件清单

实施时按以下文件清单逐一检视,避免遗漏。

### 8.1 待拆 / 待迁移文件

```
src/openagent/api/http/controllers/auth_controller.py    505  -> openagent-feihe
src/openagent/auip/flight_card.py                              -> openagent-feihe
src/openagent/auip/flight_query_presenter.py                   -> openagent-feihe
src/openagent/auip/_flight_mapping.py                          -> openagent-feihe
src/openagent/config/settings.py  §13 feihe_*                  -> openagent-feihe
work/scenarios/fh-*                                            -> openagent-feihe
work/scenarios/*flight*                                        -> openagent-feihe (或 examples)
```

### 8.2 待拆 / 待瘦身文件 (KNOWN_VIOLATIONS)

```
src/openagent/api/http/controllers/chat_controller.py
src/openagent/api/http/controllers/scenario_controller.py
src/openagent/api/http/controllers/session_controller.py
src/openagent/api/http/controllers/registry_controller.py
src/openagent/api/http/turn_routes.py
src/openagent/api/lifecycle/lifecycle.py
src/openagent/api/app/app.py
src/openagent/core/suspendable_scheduler.py
src/openagent/skills/runtime/fragments.py
src/openagent/scenarios/config.py
src/openagent/providers/base.py
src/openagent/providers/agent_bridge.py
src/openagent/providers/claude_code/chat.py            422
src/openagent/providers/claude_code/lifecycle.py       224
src/openagent/providers/opencode/chat.py              1286  <- 最大债
src/openagent/providers/opencode/lifecycle.py          328
src/openagent/providers/opencode/adapter.py            204
src/openagent/providers/opencode/event_hub.py          252
src/openagent/providers/streaming.py                   514
src/openagent/providers/launcher.py                    238
src/openagent/store/base.py
src/openagent/store/postgres.py
```

### 8.3 待重写文件

```
README.md                  <- 双语 + 突出通用基座定位
.ai/AGENTS.md              <- 内部 agent 守则 -> CONTRIBUTING.md
.ai/CLAUDE.md              <- 内部上下文 -> docs/internal/ + ADR
pyproject.toml             <- 改名 + scripts + classifiers + urls
docker-compose.yml         <- 镜像源改 GHCR
scripts/ci_check.py        <- 删 KNOWN_VIOLATIONS 后简化
scripts/verify_opencode_config.py  <- 解除硬编码模型名
```

### 8.4 待新增文件

```
LICENSE
CONTRIBUTING.md
CODE_OF_CONDUCT.md
SECURITY.md
EXTENSION_POINTS.md          (Quick Win Q3)
.pre-commit-config.yaml
.github/workflows/ci.yml
.github/workflows/release.yml
docs/spec/auip-v1.md
docs/adr/ADR-001-*.md ... ADR-NNN
docs/recipes/*.md
docs/en/* + docs/zh/*
```

### 8.5 待清理 / 解释的根目录散件

```
2.0.0          (无后缀, 2111 字节, 未知)
typescript     (无后缀, 未知)
bake/          (无 README)
relate_project/ (无 README)
.omo/          (run-continuation, 是 opencode session 缓存?)
```

---

**文档结束**。所有改动待评审通过后再实施。
