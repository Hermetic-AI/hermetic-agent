# CHANGELOG — flight-query-v3 vs flight-query (v2)

> **本目录是 v3**,根目录 `work/shared/skills/flight-query/` 是 v2 legacy backup。
> 本文档记录**所有** v2 → v3 的变更及原因,供熟悉 v2 的人快速对照。

---

## 0. TL;DR(30 秒读懂)

v2 的核心做法:**让 LLM 自己用 `Bash` 工具跑 `curl` 调 MCP 端点**。
v3 的核心做法:**MCP 端点直接配进 opencode,opencode 启动时把工具加载成原生 LLM 工具,LLM 直接调**。

```diff
- [Skill 教 LLM 用 curl]
- [LLM 写 curl, 自己处理 token / header / error]
- [Bash 实际执行]
+ [Skill 只说业务规则, 不教协议]
+ [work/mcp/servers.json 配 MCP server]
+ [opencode 启动时加载工具]
+ [LLM 调原生工具, opencode 拦截]
```

---

## 1. 详细差异表

### 1.1 协议层(Skill 全部不教)

| 项 | v2 | v3 |
|---|---|---|
| Skill 里出现 `https://` | ✅(§1.3 端点表) | ❌ |
| Skill 里出现 `Authorization` / `Bearer` / `token` | ✅(§1.4, 还要 LLM 从 system 取) | ❌ |
| Skill 里出现 `curl` | ✅(§1, §2 例子, examples/*.sh) | ❌ |
| Skill 里出现 `JSON-RPC` / `envelope` | ✅(§1.1 数据流) | ❌ |
| Skill 里出现 `Bash` | ✅(`allowed-tools: [Bash, Read]`) | ❌(`allowed-tools: [Read, Grep, Glob]`) |
| `examples/*.sh` 5 个 curl 模板 | ✅ | ❌(删除整个目录) |
| 协议层配置在哪 | LLM 脑子 + skill 文档 | `work/mcp/servers.json` |
| 换 MCP 端点 | 改 skill + 重启 | 改 `servers.json` + 重启(skill 一字不动) |

### 1.2 工具 schema 来源

| 项 | v2 | v3 |
|---|---|---|
| Skill 内嵌 `tools/flight-mcp.json` (tools/list 真实响应) | ✅(~32KB) | ❌(整个 `tools/` 目录删除) |
| Skill 内嵌 `tools/samples/*.json` 4 份真实响应 | ✅(~330KB) | ❌ |
| 子 skill `flight-query.query_flight_basic/SKILL.md` 完整 schema | ✅(~487 行) | ❌(整个子目录删除) |
| LLM 调工具时 schema 从哪来 | LLM 用 Read 工具读 `tools/*.json` | opencode 加载 MCP server 时自动注入 LLM context |
| 入参/出参 1:1 字段映射表 | ✅(在子 skill §3) | ✅(在主 skill §5.2,内容一致) |

### 1.3 错误处理

| 项 | v2 | v3 |
|---|---|---|
| 401 / token invalid | LLM 自己看 curl exit code + HTTP code | opencode 拦截,LLM 看到结构化错误 |
| `-32099 频率过高` | LLM 自己看 JSON-RPC `error.code` | opencode 拦截 |
| 业务级 `errorMsg` | LLM 自己从 `result.content[0].text` 二次 JSON.parse | 工具直接返结构化 `isError=true` + `text` |
| 错误处置写在 skill 哪 | §4 整节 | §3 精简(协议层错误由 opencode 兜底) |

### 1.4 工具调用

| 项 | v2 | v3 |
|---|---|---|
| LLM 怎么调 `queryFlightBasic` | `Bash` 工具跑 curl | opencode 原生工具调用 |
| LLM 写 JSON-RPC envelope | ✅ | ❌ |
| LLM 拼 `Authorization: Bearer ${MCP_TOKEN}` | ✅(从 system 块取) | ❌(opencode 自己处理) |
| LLM 二次 JSON.parse `result.content[0].text` | ✅ | ❌(工具直接返结构化对象) |
| `Bash` 工具是否在白名单 | ✅ `tool_level: safe` 仍要给 | ❌(不再需要) |
| 安全边界 | Bash 是"万能钥匙" | 只暴露 MCP 工具,精确白名单 |

### 1.5 输出卡片

| 项 | v2 | v3 |
|---|---|---|
| 调 `ask_user` 推 `FLIGHT_RESULT` | ✅ §5.1 | ✅ §5 |
| 字段映射表(MCP → AUIP) | ✅ §5.1.2 | ✅ §5.2 |
| 方案分组规则 | ✅ §5.1.3 | ✅ §5.3 |
| 错误 / 空结果 推 `CANNOT_ORDER` | ✅ §5.1.4 | ✅ §5.4 |
| `chat text` 事件 | 只一句简短总结 | 只一句简短总结(同) |

> 输出卡片**完全一致**。v3 没改这块,因为这部分本来就是业务规则(Skill 该教的)。

### 1.6 Token 透传

| 项 | v2 | v3 |
|---|---|---|
| Token 来源 | `X-MCP-Token` header per-request | **静态**(从 `servers.json` 的 `headers`) |
| 怎么注入 system | `opencode_chat.py:_build_runtime_context` 拼 `<runtime-context>` 块 | **不**注入 system(opencode 读 `servers.json` 即可) |
| Per-session 隔离 | 自动(每请求拼自己的 token) | 需 `launcher.py` 额外工作(未实现,见 README §3.2) |
| Demo 现状 | ✅ 完整 | ⚠️ 静态(测试时用占位 token) |

---

## 2. 文件清单对比

### v2(根目录,legacy backup)

```
work/shared/skills/flight-query/
├── SKILL.md                       # ~373 行(含 token 透传、curl 模板、铁律、卡片)
├── SKILL-INDEX.md                 # ~136 行
├── LEGACY-README.md               # 新加:标记为 v2 backup
├── tools/
│   ├── README.md                  # 工具接口刷新流程
│   ├── flight-mcp.json            # ~32KB tools/list 响应
│   ├── flight-mcp.live.json       # 同上备份
│   └── samples/                   # 4 份真实样本 + 4 份 req 样本(~340KB)
├── examples/                      # 5 个 curl 模板
│   ├── README.md
│   ├── 01-oneway-full.sh
│   ├── 02-oneway-cheapest.sh
│   ├── 03-oneway-filtered.sh
│   ├── 04-roundtrip-recommended.sh
│   └── 05-filter-on-loaded.sh
├── flight-query.query_flight_basic/  # 子 skill:~487 行完整 schema
│   └── SKILL.md
└── flight-query.iata_icao_codes/     # 子 skill:~146 行 IATA 翻译
    └── SKILL.md
```

**总计 ~1500 行文档 / ~370KB 资源**

### v3(新)

```
work/shared/skills/flight-query-v3/
├── SKILL.md                          # ~280 行(纯业务规则 + 卡片规范)
├── SKILL-INDEX.md                    # ~150 行(导航)
├── CHANGELOG.md                      # 本文件(v2 vs v3 差异)
└── flight-query-v3.iata_icao_codes/  # 子 skill:继承 v2 的 IATA 表
    └── SKILL.md                      # ~146 行(原样照搬,改名)
```

**总计 ~600 行文档 / 0KB 协议资源(协议在 `work/mcp/servers.json`)**

> **文档量减少 60%,零协议资源**,但**业务能力不变**。

---

## 3. 不变的事项(无论 v2 / v3 都该教)

- 铁律(改 OD/日期 → 重调,filterFlightList 仅 planeSize/maxDuration)
- 城市用中文,不支持 IATA 码
- 日期 yyyy-MM-dd 月日补零
- 输出走 `FLIGHT_RESULT` / `CANNOT_ORDER` 卡片
- 与 `flight-booking` 的边界

> **v3 的所有内容 = v2 的"业务子集"**。v3 把协议层完全剥离出去,留下的全是 LLM 该学的。

---

## 4. 已知限制(v3 demo)

| 限制 | 说明 | 计划 |
|---|---|---|
| **Per-request token** | opencode `mcpServers.headers` 是静态的,不支持 per-request 覆盖 | v3 demo 静态;生产用 `launcher.py` 给每次 session 写 per-session config(本仓库未实现,见 `work/mcp/README.md` §3.2) |
| **`launcher.py` 还没读 `servers.json`** | 当前 `_render_opencode_config` 不输出 `mcpServers` 段 | 需要在 launcher 加 method / 新建 module,**不动签名** |
| **AUIP 卡片实现** | 前端 `FlightResultCard` 已有,跟 v2 一样 | 无需改 |

---

**最后更新**:2026-06-05
**对比基线**:`work/shared/skills/flight-query/` (v2)
**对应 scenario**:`work/scenarios/flight_query_v3.scenario.yaml`
