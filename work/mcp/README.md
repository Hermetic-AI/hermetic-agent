# work/mcp/ — MCP Server Registry

> **v3 起,本目录接管所有 MCP 服务器的 wire-level 配置**。
> Skill 只说"调哪个工具",**怎么说、连哪里、传什么 header** 全部在本目录声明。
> 跟 Skill 解耦 — 换 MCP 端点 = 改这里,不动 skill。

---

## 文件清单

| 文件 | 用途 | 读取方 |
|---|---|---|
| `servers.json` | opencode 格式的 MCP 服务器注册表 | opencode 启动时 |
| `mcporter.json` | mcporter 格式的 MCP 服务器注册表,用于 bridge 模式按 server/tool 过滤 | mcporter serve |
| `mcp.json` | **v2 遗留** — OpenAgent `MCPRegistry` 的工具 schema 元数据(空数组,因为 v2 不真接 MCP,LLM 自己 curl) | OpenAgent 后端 (settings.mcp_tools_config) |
| `README.md` (本文件) | 格式说明 / 怎么加新 server / 怎么改 endpoint | 人读 |

> **v3 起 `mcp.json` 不再使用**(它本是给 OpenAgent 自己 `MCPRegistry` 用的 schema 元数据,v3 改由 opencode 加载 `servers.json` 直接暴露原生工具)。
> 保留 `mcp.json` 作历史兼容,见末尾 §4。

---

## 1. `servers.json` 格式

严格遵循 opencode 自己的 `mcpServers` schema(参 `oh-my-opencode/dist/features/claude-code-mcp-loader/types.d.ts` 的 `ClaudeCodeMcpServer`)。

### 1.1 顶层结构

```jsonc
{
  "mcpServers": {
    "<server-name>": { /* server config */ }
  }
}
```

### 1.2 单个 server config

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `type` | `"http"` \| `"sse"` \| `"stdio"` | ❌(默认 `stdio`) | 传输类型 |
| `url` | string | http/sse 必填 | MCP 端点 |
| `command` | string | stdio 必填 | 启动命令(可执行文件名或绝对路径) |
| `args` | string[] | stdio 用 | 启动参数 |
| `env` | Record<string,string> | ❌ | 传给子进程的环境变量 |
| `cwd` | string | ❌ | stdio 子进程的 cwd(相对 opencode serve 的 --cwd) |
| `headers` | Record<string,string> | http/sse 用 | 自定义 HTTP header(**静态,不支持 per-request 覆盖**) |
| `disabled` | boolean | ❌ | true = opencode 不加载(但保留在 config 里方便切换) |

### 1.3 三个例子

**HTTP 远程 MCP(本目录默认就这一个)**:
```json
{
  "mcpServers": {
    "feihe-travel": {
      "type": "http",
      "url": "https://traveldev.feiheair.com/api/mcp",
      "headers": { "Accept": "application/json,text/event-stream" }
    }
  }
}
```

**stdio 本地 MCP(开发 mock / sandbox)**:
```json
{
  "mcpServers": {
    "flight-mock": {
      "type": "stdio",
      "command": "node",
      "args": ["work/mcp/mocks/flight-mock.mjs", "mcp"],
      "cwd": ".",
      "env": { "MOCK_PORT": "4100" }
    }
  }
}
```

**SSE(legacy)**:
```json
{
  "mcpServers": {
    "legacy-weather": {
      "type": "sse",
      "url": "https://weather.example.com/sse",
      "headers": { "X-Tenant": "feihe" }
    }
  }
}
```

---

## 1.4 MCPorter bridge 配置

`mcporter.json` 用于把 fh-travel MCP 先交给 MCPorter 管理,再由 OpenCode 加载一个本地 bridge MCP:

```jsonc
{
  "mcpServers": {
    "feihe-travel": {
      "baseUrl": "https://traveldev.feiheair.com/api/mcp",
      "headers": { "token": "$env:FLIGHT_API_KEY" },
      "allowedTools": ["queryFlightBasic", "filterFlightList"]
    }
  },
  "imports": []
}
```

启用方式:

```bash
MCPORTER_ENABLED=true
MCPORTER_CONFIG_PATH=/opt/sandbox/mcporter.json
MCPORTER_SERVERS=feihe-travel
```

启用后 `docker/render_config.py` 会注册本地 MCP server `mcporter`,命令为:

```bash
mcporter serve --stdio --config /opt/sandbox/mcporter.json --servers feihe-travel
```

OpenCode 中的工具名采用 MCPorter bridge 命名空间: `feihe-travel__queryFlightBasic`。
这对应场景 `work/scenarios/fh_domestic_flight_booking_mcporter.scenario.yaml`。

---

## 2. v3 数据流(Skill ↔ MCP 完全解耦)

```
                      ┌──────────────────────────────┐
                      │  work/shared/skills/         │
                      │  flight-query-v3/SKILL.md    │
                      │                              │
                      │  教 LLM:                     │
                      │  • 什么时候调 queryFlightBasic │
                      │  • 怎么解析 flightList        │
                      │  • 怎么发 FLIGHT_RESULT 卡片  │
                      │                              │
                      │  ❌ 不教: endpoint/header/    │
                      │           JSON-RPC/curl       │
                      └──────────────┬───────────────┘
                                     │ LLM 读到 → 决定调
                                     ▼
                      ┌──────────────────────────────┐
                      │  LLM (在 opencode runtime)    │
                      │  直接调原生工具 queryFlightBasic │
                      └──────────────┬───────────────┘
                                     │ opencode 拦截 → MCP 协议
                                     ▼
                      ┌──────────────────────────────┐
                      │  work/mcp/servers.json       │
                      │  opencode 启动时读            │
                      │  → 注册 feihe-travel server  │
                      │  → 暴露 15 个工具给 LLM      │
                      └──────────────┬───────────────┘
                                     │ http
                                     ▼
                          ┌────────────────────┐
                          │  飞鹤差旅 MCP 端点   │
                          │  (远端)             │
                          └────────────────────┘
```

**关键不变量**:
- Skill 文件里**搜不到** `https://`、`Authorization`、`curl`、`Bash`、`JSON-RPC` 这些字眼
- Skill 只说工具**做什么**,不说工具**怎么连**
- 换 MCP 端点 URL → 只改 `servers.json` → Skill 一字不动

---

## 3. Per-request Token:已知限制与建议

opencode 的 `mcpServers.headers` 是**静态 header**,不支持 per-request 覆盖。
但飞鹤差旅 MCP 是 per-user 鉴权(每个用户在 `X-MCP-Token` header 带自己的 token)。

**v3 当前 demo 的取舍**:
- `servers.json` 不带 token header
- 测试时用 `Authorization: Bearer <token>` 走 OAuth 形式(若 MCP 端支持,见 §3.1)
- 生产 per-request token 需要**额外一层代理**(见 §3.2)

### 3.1 OAuth 兜底(若 MCP 服务端支持)

MCP 规范允许 server 端在 401 时返回 `WWW-Authenticate: Bearer ...`,
opencode 会自动用 `oauth` 字段配置的 client credentials 走 OAuth flow。
v3 demo 未配置,留作生产接入时再补。

### 3.2 推荐的 per-request token 方案(本仓库未实现,留作 TODO)

```
[OpenAgent 前端 / 浏览器]
      │ X-MCP-Token: <user-token>
      ▼
[OpenAgent Hub]
      │ 1. 读 header 拿 token
      │ 2. 启动 opencode serve 时,在 --config 里塞一份 per-session MCP config
      │    (mcpServers.feihe-travel.headers.token = "<user-token>")
      │    (临时写到 work/cache/opencode-configs/<agent>-<session>.json)
      │ 3. opencode 启动后,token 就在那次会话的 MCP server config 里
      ▼
[opencode serve (per session)]
      │ 用那份 per-session config 启 MCP client
      ▼
[MCP 端点]
```

要点:
- per-session MCP config 文件由 Hub 在 `opencode_chat.py:launch` 路径上生成
- 配置里的 token 是**那一个用户**的,不会跨 session 泄露
- 实现位置:`src/openagent/providers/launcher.py` 的 `_render_opencode_config` 增加 MCP servers 段
- **当前 v3 demo 不实现这一段**(避免改 launcher.py 签名),只把架构留清楚

---

## 4. `mcp.json` 兼容说明

`work/mcp/mcp.json`(空 `{"tools": []}`)是 **v2 时代**给 `MCPRegistry.from_config` 用的元数据列表 — 跟 opencode 无关。
v3 起:
- opencode 读 `servers.json`(本目录)
- `MCPRegistry` 主要用于**合成工具**(如 `ask_user`),不再列 MCP 工具

若你的 `settings.mcp_tools_config` 仍指向 `work/mcp/mcp.json`,可以保持不动(空 tools 不影响),也可以改成指向 `servers.json` 的 `"mcpServers"` 键(需要自定义 `MCPRegistry.from_config` 解析器,本仓库没动)。

---

## 5. 校验

```bash
# 1) JSON 合法
python -c "import json; print(json.load(open('work/mcp/servers.json', encoding='utf-8')))"

# 2) 必填字段都在
python -c "
import json
d = json.load(open('work/mcp/servers.json', encoding='utf-8'))
for name, s in d.get('mcpServers', {}).items():
    if s.get('disabled'): continue
    t = s.get('type', 'stdio')
    assert t in ('http', 'sse', 'stdio'), f'{name}: bad type {t}'
    if t in ('http', 'sse'):
        assert s.get('url'), f'{name}: url required for {t}'
    else:
        assert s.get('command'), f'{name}: command required for stdio'
print('OK', list(d.get('mcpServers', {}).keys()))
"
```

---

**最后更新**:2026-06-05
**关联**:`work/shared/skills/flight-query-v3/` (新 skill) / `work/scenarios/flight_query_v3.scenario.yaml` (新场景)
