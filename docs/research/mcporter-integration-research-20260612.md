# mcporter 调研报告 — 渐进式 MCP 工具加载

> 日期: 2026-06-12
> 目的: 评估 `mcporter` 是否能接入 OpenAgent,作为按 skill 渐进式披露 MCP 工具的能力
> 结论先行: **不必直接接入 mcporter**,但它的设计思想值得借鉴。本项目**已有 60% 的基建**,缺的 40% 是"工具 schema 懒加载 + MCP server 懒连接",这一段用纯 Python 加 200 行代码就能搞定,引入 mcporter 反而会增加 Node 侧运维成本。

---

## 1. mcporter 是什么

`mcporter` (steipete/mcporter, npm 0.11.0, MIT) 是一个 TypeScript 写的 MCP 工具链,定位是"让 agent 通过代码执行(Code Execution with MCP)来调 MCP,而不是把所有工具都喂给 LLM"。核心能力:

| 能力 | 价值 | 是否解决我们的问题 |
|---|---|---|
| **零配置发现** — `~/.mcporter/mcporter.json` 合并 Cursor/Claude/Codex/Windsurf/OpenCode/VSCode 全部 MCP 配置 | 不用手写 MCP server 注册 | 部分:我们有自己的 `MCPRegistry`,不需要外部发现 |
| **Bridge 模式** — `mcporter serve` 把多个 daemon 化的 MCP server 聚合成**单个 MCP 端点**,工具名加 `server__tool` 命名空间 | 多个 MCP 合并成一个下游 | 不解决"少喂工具给 LLM"的问题,只是合并端点 |
| **`allowedTools` / `blockedTools` 服务端过滤** | MCP server 只暴露部分工具 | **直接相关**:这就是我们要的"按需" |
| **Ad-hoc 连接** — `npx mcporter call --http-url ...` 不写配置直接调 | 临时连一个 MCP server | 部分:符合"按需连接" |
| **Record / Replay** — `mcporter record` 抓 MCP 流量 NDJSON,`mcporter replay` 离线回放 | 离线调试 / 测试 | 跟我们场景无关 |
| **OAuth 缓存 / 自动刷新** | 无头部署 | 我们已有 env 注入 token,无关 |
| **TypeScript 运行时 API** — `createRuntime()` / `callOnce()` / `createServerProxy()` | 写 TS agent 调 MCP | 跟我们 Python 栈无关 |

**关键判断**: mcporter 的**强项**是"在 Node/TS 项目里,把多个 MCP server 当库用",**弱项**是"减少 LLM 看到的工具数"。后者它只通过 `allowedTools` 提供,且要改 MCP server 端的 schema 暴露范围,**不是它主打场景**。

---

## 2. 项目现状 — 60% 基建已经在了

读了 `src/openagent/mcp/registry.py`、`src/openagent/skills/registry.py`、`src/openagent/skill_runtime/fragments.py`、`src/openagent/scenarios/injector.py`、`src/openagent/providers/opencode/chat.py:582-622` 后,现状如下:

### ✅ 已有的渐进式披露基建

| 能力 | 位置 | 说明 |
|---|---|---|
| `Skill.mcp_tools: list[str]` | `src/openagent/skills/registry.py:70` | 每个 skill 声明它要用哪些 MCP 工具,frontmatter 解析 `mcp_tools: [...]` (`frontmatter.py:70`) |
| L1 元数据列表 | `SkillRegistry.metadata_list()` (`registry.py:264-305`) | Anthropic Skills 协议 L1:在 system_prompt 顶部放 `name + desc` 列表,LLM 看到关键词后**主动**调 `read_skill` 加载完整内容 |
| L2 片段加载 | `FragmentLoader` (`skills/runtime/fragments.py`) | `none / all / on_demand / explicit` 4 种策略 + token budget 强制 |
| `PromptBuilder` | `skills/runtime/prompt_builder.py` | 走 scenario 路由,按 `current_state` 渲染 skill 段 |
| 工具白名单 | `ScenarioInjector.inject()` (`scenarios/injector.py:69-148`) | caller 传的 tools 跟 scenario `execution.tools` 取交集,`rejected_tools` 审计 |
| 工具过滤输出 | `MCPRegistry.to_opencode_format(names)` (`mcp/registry.py:284-308`) | 按名字子集导出,**不传** names 时导全部 |

### ❌ 还差的 40%

1. **`MCPRegistry.from_config()` 启动时全量加载** (`api/lifecycle/lifecycle.py:184`):从 `settings.mcp_tools_config` 一次性把**所有** MCP server 端点注册进内存,不管哪个 scenario 命中,registry 里都有。
2. **OpenCode 端 `tools: Dict[str, bool]` 透传** (`providers/opencode/chat.py:582-622`):注释明确说 *"tool schema 走 opencode config (provider 段), chat 请求只声明'启用哪些'"*。即:opencode 的 MCP config 里**仍然有所有工具的 schema**,OpenAgent 只是发开关。LLM 端实际看到的工具列表 = `opencode config 里的全部 ∩ {True}`。
3. **没有 `read_mcp_tool` 类合成工具**:LLM 不知道"哪些工具可被按需加载",也没法主动声明"我要看这个工具的 schema"。
4. **跨 skill 的 MCP 依赖去重 / 冲突**没处理:两个 skill 都用 `playwright`,目前是全量注册,改成按需时需要"先到先得 / 并发共享连接"。
5. **测试 fixture** 里没有"按需连接 MCP"的 mock,改起来要先建 mock 框架。

### 关键架构事实(影响选型)

| 事实 | 含义 |
|---|---|
| OpenCode adapter 走 `tools: dict[str, bool]` 开关模式 | 即使 OpenAgent 端只挑 3 个工具下发,opencode config 里**其它工具的 schema 仍会进 LLM 上下文**。要从根本上"少喂",必须改 opencode config 段 |
| Provider 有两个:opencode / claude_code | claude_code 走 `to_claude_code_format` 给完整 tool spec(`providers/claude_code/chat.py:232`),opencode 走开关。两条路 schema 暴露面不同,改造时要分别处理 |
| Skill 已经有 L1/L2 渐进式 | 工具的渐进式应该**复用同样的 fragment / budget 框架**,不是另起炉灶 |
| Docker 镜像基于 `node:24-slim` 装 `opencode-ai@latest` | Node 已在运行时栈,加 mcporter 不引入新 runtime,但增加 1 个 sidecar 进程要管 |

---

## 3. 三种集成方案对比

### 方案 A: 直接引入 mcporter 作 sidecar 桥接

```
[OpenAgent] ─HTTP/SDK─> [opencode serve] ─stdio/HTTP─> [mcporter serve] ─stdio/HTTP─> [N 个 MCP server]
                                                          │
                                                          └─ 1 个 MCP 端点对外,工具加 server__tool 命名空间
```

- OpenAgent 在 `mcp_tools_config` 加一项 `mcporter://...` HTTP MCP
- opencode config 同步加这个 MCP server
- 写一个**配置热重载器**:scenario 切换 / skill 激活时,改 `~/.mcporter/mcporter.json` 的 `allowedTools` 或启停 server

**优点**: 开箱即用,零代码写 MCP client
**缺点**:
- 跨 **3 个进程** (openagent / opencode / mcporter) 的配置同步,故障面大 1 倍
- mcporter 自身又是 Node 进程,版本/锁文件/漏洞扫描要纳入 CI
- `allowedTools` 是 MCP server 启动时读,**改完要 reload daemon**(`mcporter daemon restart`),做不到 per-request 切换
- 跟我们 Python 栈的 `MCPRegistry` / `ScenarioInjector` 强耦合逻辑无法复用,只能在最外层包一层

**评分**: ❌ **不推荐** — 引入 Node 侧运维成本,获得的"按需"能力是粗粒度的(server 级,不是 tool 级),跟现有 `MCPRegistry` 体系脱节

### 方案 B: 借鉴 mcporter 思想,纯 Python 实现"工具 schema 懒加载" ⭐ 推荐

不动 mcporter,在我们自己的 `MCPRegistry` 上加两层:

1. **L1 工具索引层**(常驻内存,小)
   - 每个 tool 只存 `{name, server_name, description(一句话), input_schema_hash, tags}`
   - 占空间约 1-2 KB/tool,1000 个 tool 也就 1-2 MB
   - 这个层**永远**在 system_prompt 顶部(类似 L1 skill 列表),给 LLM 看"哪些工具家族可用 + 何时该调 `read_mcp_tool`"
2. **L2 schema 懒加载层**(按需)
   - 调 `read_mcp_tool(name=...)` → 框架拦截,返完整 input_schema
   - 走 framework 自带的 tool_use 拦截,跟现有 `ask_user` 卡片拦截同一套机制(`mcp/registry.py:120-148` 的 `register_synthetic_tool`)

并把 Skill 端补齐:
- `Skill.mcp_servers: list[str]` 新字段(跟现有 `mcp_tools` 并存)
- 触发 skill 时,只把 `mcp_servers` 列出的 server **实际**建立连接(opencode config 段),其它 server 不在 opencode config 里出现
- 复用 `FragmentLoader` 的 budget 机制,限制单次 chat 暴露的工具 schema 总 token 数

**伪代码示意**:
```python
# scenarios/injector.py 改造
def inject(self, scenario, user_message, ...):
    # 1. 决定这个 scenario 要用的 MCP server 集合 (skill.mcp_servers ∪ scenario.tools 引用的 server)
    active_servers = collect_active_servers(scenario, skills)
    # 2. 把 opencode config 切成 "active 段 + 注释掉的 inactive 段"
    render_opencode_config(active_servers)
    # 3. 在 system_prompt 顶部 prepend L1 工具索引 (类似 metadata_list)
    tool_index = self._mcp_registry.render_l1_index(active_servers)
    # 4. 注册 read_mcp_tool 合成工具
    self._mcp_registry.register_synthetic_tool(
        name="read_mcp_tool",
        description="按需加载 MCP 工具的完整 schema,只在 LLM 拿到名字但不知道参数时调",
        input_schema={...},
    )
```

**优点**:
- 全 Python,跟现有 `MCPRegistry` / `ScenarioInjector` / `FragmentLoader` / `PromptBuilder` 体系无缝衔接
- 改动面小:`mcp/registry.py` 加 L1 索引 + 懒连接 manager,`scenarios/injector.py` 加 active-server 收集,`providers/opencode/chat.py` 加 `read_mcp_tool` 拦截
- 不引入 Node 侧依赖
- 跟现有 skill 渐进式策略(`none/all/on_demand/explicit`)复用同一套 budget / 审计 / 日志

**缺点**:
- opencode config 段的热重载要小心 — opencode serve 启动时读 config,**运行时改 config 不会立即生效**,需要走 `opencode admin` 端点(项目里已有 `OPENCODE_ADMIN_PORT` 兜底,见 `providers/opencode/chat.py:159`)或 reload 进程
- 第一次需要写 ~200-300 行 Python

**评分**: ✅ **强烈推荐**

### 方案 C: 双轨 — mcporter 负责"发现 + 临时连接",Python 负责"持久白名单"

仅用 mcporter 的**库 API**(`createRuntime` / `callOnce`)跑在 OpenAgent 进程内(通过子进程调 `npx mcporter call ...`),不用它的 bridge。

- 临时 / Ad-hoc MCP 工具 → 走 `subprocess.run("npx mcporter call ...")`
- 持久 / 已经在白名单的 MCP 工具 → 走现有 `MCPRegistry`

**优点**: 不引入 sidecar 进程
**缺点**: 每次调都起 Node 进程,启动开销 ~500ms,**完全抵消**按需加载节省的 token
**评分**: ❌ **不推荐**

---

## 4. 推荐实施路径(方案 B)

按风险从小到大 4 步走,每步独立可回滚:

### Step 1: L1 工具索引 — 1 天
- `MCPRegistry.render_l1_index(server_filter=None)` — 输出 `(server, tool, desc) 列表`
- `SkillRegistry.metadata_list` 已经实现了同样模式,**直接照抄**,扩展到 tool 维度
- 验证: scenario chat 时 system_prompt 顶部有工具索引,LLM 能正确识别

### Step 2: `read_mcp_tool` 合成工具 — 2 天
- `register_synthetic_tool("read_mcp_tool", ...)` — 复用 `mcp/registry.py:120-148` 的 no-op 套路
- 在 `providers/opencode/chat.py` 的 streaming_fn 加拦截,跟 `ask_user` 卡片拦截同位
- 调 `read_mcp_tool(name="playwright.navigate")` → 返 `input_schema + 1 个 example payload`
- 验证:LLM 看到工具名不知道参数,主动调 `read_mcp_tool`,拿到 schema 后再调真实工具

### Step 3: 按 skill 激活 MCP server 集合 — 3 天 ⚠️ 需要小心
- `Skill` 加 `mcp_servers: list[str]` 字段(跟 `mcp_tools` 并存,后者是 tool 名粒度,前者是 server 名粒度)
- `ScenarioInjector` 改写:先收集 `active_mcp_servers = ∪ skill.mcp_servers ∪ scenario.tools 引用的 server`,再决定 opencode config
- opencode config 改写:走 `opencode admin` HTTP 端点(项目已有 `OPENCODE_ADMIN_PORT`)**热重载**,而不是重启 serve
- 验证:scenario 切换前后,opencode config 段里 MCP server 数从 30 → 5,LLM 实际看到的工具数对应减少

### Step 4: Budget + 审计 — 1 天
- 复用 `FragmentLoader` 的 `budget` 概念,加 `MCPFragmentLoader`(`mcp/registry.py` 同级)
- 单次 chat 暴露的工具 schema 总 token 数超 `mcp_tool_budget` 时,按 `policy`(error/warn/truncate)处置
- `rejected_tools` 走现有审计(`scenarios/injector.py:128-138`)

**总计**: ~1 人周。引入 mcporter 改造周期按"加 sidecar + 跨进程调试"估算至少 2-3 人周,且长期 Node 侧维护成本更高。

---

## 5. mcporter 真正有用的部分(选择性借鉴)

如果将来想加**临时 MCP 工具**(用户运行时说"帮我连这个 MCP URL"),可以**只**用 mcporter 的:
- `mcporter call --http-url https://example.com/mcp --persist ./mcp.local.json` — 加配置
- `mcporter auth <url>` — 跑 OAuth

这两条都是给开发者手动操作的 CLI,**不放在 chat 路径上**,跟我们 Python 栈不冲突。`work/mcp/README.md` 已经有类似的 MCP server 注册流程,可以参考。

---

## 6. 待确认的设计问题

在动手前需要你定一下:

1. **"按需"粒度**: 是想按 **MCP server** 粒度按需(连不连 server)?还是想按 **tool** 粒度按需(server 永远连,只控制哪些 tool 暴露给 LLM)?方案 B 的 Step 3 是 server 粒度,Step 2 是 tool 粒度(通过 `read_mcp_tool`)。
2. **opencode config 热重载**: opencode serve 启动后改 config 不会立即生效。要么走 admin 端点 reload(快但有风险),要么接受"切 scenario 时短暂 reload serve"(稳但有 ~1s 延迟)。项目已经有 `OPENCODE_ADMIN_PORT=7778` 走 admin,倾向**接受 reload**。
3. **`read_mcp_tool` 是不是要默认开启**: 开了 LLM 就要学"看到一个工具名 → 调 read_mcp_tool 拿 schema",增加 prompt 复杂度。如果工具总数其实没那么多(比如 < 50),可能**直接全量 schema 暴露**就够了。
4. **预算值**: 现有 skill 的 `FragmentLoader(budget=4000)` 是 4000 token。工具 schema 平均 200-500 token,建议 MCP 工具预算初始值 8000 token,**后面按场景调**。
5. **要不要去重 / 缓存 schema**: 同一个 `read_mcp_tool(name=X)` 多次调要不要缓存?opencode 自己有 connection pool,框架层可以加 LRU(`maxsize=128`)。

---

## 7. 结论

| 维度 | 引入 mcporter(sidecar) | 纯 Python 方案 B |
|---|---|---|
| 渐进式粒度 | Server 级(`allowedTools` 改完要 daemon reload) | Server + Tool 两级(per-request) |
| 新增 Node 依赖 | +1 sidecar 进程,1 个 npm 包 | 0 |
| 与现有体系融合 | 弱(脱节) | 强(复用 FragmentLoader / ScenarioInjector) |
| 实施周期 | 2-3 人周(含跨进程调试) | ~1 人周 |
| 长期维护成本 | 高(Node 升级 / 漏洞扫描 / lockfile 同步) | 低(纯 Python,跟着项目一起走) |
| mcporter 独有能力(零配置发现 / record-replay) | 0 价值(我们有自己的 Registry) | 0 价值 |
| **推荐** | ❌ | ✅ |

**下一步**: 等你确认第 6 节的 5 个问题(尤其是问题 1 粒度和问题 3 是否要 `read_mcp_tool`),就可以出 Step 1 的 PR 了。

---

## 附:相关源码定位

- `src/openagent/mcp/registry.py:58-401` — `MCPRegistry` 主类,Step 1/2 改这里
- `src/openagent/mcp/registry.py:120-148` — `register_synthetic_tool` no-op 套路,`read_mcp_tool` 沿用
- `src/openagent/skills/registry.py:264-305` — `metadata_list` L1 实现,工具索引照抄
- `src/openagent/skill_runtime/fragments.py` — `FragmentLoader` 4 策略 + budget,Step 4 复用
- `src/openagent/scenarios/injector.py:69-148` — `ScenarioInjector`,Step 3 改写
- `src/openagent/providers/opencode/chat.py:582-622` — `_resolve_tool_names` 工具开关逻辑
- `src/openagent/providers/opencode/chat.py:159` — `OPENCODE_ADMIN_PORT`,Step 3 热重载用
- `src/openagent/api/lifecycle/lifecycle.py:184` — `MCPRegistry.from_config` 启动入口
- `docs/skills-development-guide.md:169-323` — 已有"场景化 MCP + Skill 联动"的设计雏形,可参考
- `docs/design/opencode-skill-and-workspace-constraint.md` — opencode config 透传机制
