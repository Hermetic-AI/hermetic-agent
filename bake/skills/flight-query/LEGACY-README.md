# ⚠️ LEGACY — v2 Skill (Bash + curl 自行调用 MCP)

> **本文档所在 skill (`work/shared/skills/flight-query/`) 是 v2 版本**,已废弃作 backup 保留。
> **新版本 v3** 见 `work/shared/skills/flight-query-v3/` — 走 opencode 原生 MCP 工具调用,无需 LLM 写 curl。

---

## 为什么 v2 被废弃

v2 的核心做法: **让 LLM 自己用 `Bash` 工具跑 `curl` 调 MCP 端点**。

```
┌─────────────────────┐
│ Skill 教 LLM:       │
│  "用 curl 调 MCP,   │
│   token 从 system   │
│   块里取"           │
└──────────┬──────────┘
           │ LLM 读到
           ▼
┌─────────────────────┐
│ LLM 写 curl,        │  ← LLM 自己拼 header / JSON-RPC envelope / 处理 isError
│  Bash 执行,         │
│  解析 response      │
└──────────┬──────────┘
           │ curl
           ▼
┌─────────────────────┐
│ MCP 端点            │
└─────────────────────┘
```

### 4 个根本问题

| # | 问题 | 后果 |
|---|---|---|
| 1 | **LLM 承担协议** — JSON-RPC envelope / header / error 解析全在 prompt | prompt 膨胀 250+ 行,token 浪费 |
| 2 | **Token 透传靠 system_prompt 注入** — 拼 `<runtime-context>` 块 | 安全边界模糊,token 进上下文 |
| 3 | **Skill 与 MCP 紧耦合** — Skill 必须知道 endpoint/header/协议 | 换 MCP 端点 → 改 Skill |
| 4 | **Bash 工具是 LLM 的"万能钥匙"** — 一旦启用,LLM 能跑任意命令 | `tool_level: safe` 仍要给 Bash,矛盾 |

## v3 怎么改的 (摘要)

```
┌─────────────────────┐
│ Skill 教 LLM:       │
│  "调 queryFlight    │
│   Basic 工具"       │  ← 只说"做什么",不说"怎么做"
└──────────┬──────────┘
           │ LLM 读到
           ▼
┌─────────────────────┐         ┌──────────────────┐
│ LLM 调原生工具       │ ──────► │ opencode runtime │ ───┐
└─────────────────────┘         └──────────────────┘    │ MCP 协议
                                                     ▼
                                            ┌──────────────────┐
                                            │ MCP 端点          │
                                            └──────────────────┘
         ▲
         │ opencode 启动时读
         │
┌─────────────────────┐
│ work/mcp/servers.json │  ← 协议 / endpoint / header 全在这
└─────────────────────┘
```

详细对比见 `work/shared/skills/flight-query-v3/CHANGELOG.md`。

## v2 文件清单(全保留,作教学/对照用)

```
work/shared/skills/flight-query/
├── SKILL.md                       # v2 核心(包含 §1 token 透传契约 + §2 Bash+curl 流程)
├── SKILL-INDEX.md                 # v2 导航
├── tools/
│   ├── flight-mcp.json            # MCP tools/list 真实响应
│   ├── flight-mcp.live.json       # 同上(备份)
│   └── samples/                   # 4 份真实响应样本
├── examples/                      # 5 个 curl 模板
│   ├── 01-oneway-full.sh
│   ├── 02-oneway-cheapest.sh
│   ├── 03-oneway-filtered.sh
│   ├── 04-roundtrip-recommended.sh
│   └── 05-filter-on-loaded.sh
└── README.md (本文)
```

## v2 对应 scenario

- `work/scenarios/flight_query.scenario.yaml` — v2 配置,`execution.tools: [queryFlightBasic, filterFlightList]`,但 `work/mcp/mcp.json` 为空(没真接 MCP)
- v3 scenario: `work/scenarios/flight_query_v3.scenario.yaml` — 配套 `work/mcp/servers.json`

## 是否还能用

**能用,但不推荐新接入**。
- 已部署的实例可以继续用 v2(LLM 自己 curl,功能 OK)
- 新接入 / 新场景 / 想用 AUIP 卡片完整链路 → 直接上 v3

---

**最后更新**:2026-06-05
**状态**:⚠️ LEGACY,新需求请用 v3
