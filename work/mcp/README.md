# work/mcp/ — MCP Server Registry

> MCP 服务器的 wire-level 配置。Skill 只说"调哪个工具",**怎么说、连哪里、传什么 header** 全部在本目录声明。跟 Skill 解耦 — 换 MCP 端点 = 改这里,不动 skill。

---

## 文件清单

| 文件 | 用途 | 读取方 |
|---|---|---|
| `servers.json` | opencode 格式的 MCP 服务器注册表 | opencode 启动时 |
| `mcporter.json` | mcporter 格式的 MCP 服务器注册表,用于 bridge 模式 | mcporter serve |
| `mcp.json` | **v2 遗留** — hermetic_agent `MCPRegistry` 工具 schema 元数据(空数组) | hermetic_agent 后端 (settings.mcp_tools_config) |
| `README.md` (本文件) | 格式说明 / 怎么加新 server | 人读 |

---

## 1. `servers.json` 格式

严格遵循 opencode 自己的 `mcpServers` schema。

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

**HTTP 远程 MCP**:
```json
{
  "mcpServers": {
    "my-mcp": {
      "type": "http",
      "url": "https://my-mcp.example.com/api/mcp",
      "headers": { "Accept": "application/json,text/event-stream" }
    }
  }
}
```

**stdio 本地 MCP(开发 mock / sandbox)**:
```json
{
  "mcpServers": {
    "local-mock": {
      "type": "stdio",
      "command": "node",
      "args": ["work/mcp/mocks/local-mock.mjs", "mcp"],
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
      "headers": { "X-Tenant": "mycompany" }
    }
  }
}
```

---

## 2. v3 数据流(Skill ↔ MCP 完全解耦)

```
                      ┌──────────────────────────────┐
                      │  work/shared/skills/         │
                      │  my-skill/SKILL.md           │
                      │                              │
                      │  教 LLM:                     │
                      │  • 什么时候调 my_tool_a      │
                      │  • 怎么解析 tool output      │
                      │  • 怎么发业务卡片            │
                      │                              │
                      │  ❌ 不教: endpoint/header/    │
                      │           JSON-RPC/curl       │
                      └──────────────┬───────────────┘
                                     │ LLM 读到 → 决定调
                                     ▼
                      ┌──────────────────────────────┐
                      │  LLM (在 opencode runtime)    │
                      │  直接调原生工具               │
                      └──────────────┬───────────────┘
                                     │ opencode 拦截 → MCP 协议
                                     ▼
                      ┌──────────────────────────────┐
                      │  work/mcp/servers.json       │
                      │  opencode 启动时读            │
                      │  → 注册 MCP server            │
                      │  → 暴露工具给 LLM            │
                      └──────────────┬───────────────┘
                                     │ http / stdio / sse
                                     ▼
                          ┌────────────────────┐
                          │  业务 MCP 端点      │
                          │  (远端 / 本地进程)   │
                          └────────────────────┘
```

**关键不变量**:
- Skill 文件里**搜不到** `https://`、`Authorization`、`curl`、`Bash`、`JSON-RPC` 这些字眼
- Skill 只说工具**做什么**,不说工具**怎么连**
- 换 MCP 端点 URL → 只改 `servers.json` → Skill 一字不动

---

## 3. Per-request Token:已知限制与建议

opencode 的 `mcpServers.headers` 是**静态 header**,不支持 per-request 覆盖。

**当前方案**:
- `servers.json` 不带 token header
- 业务方用 `Authorization: Bearer <token>` 走 OAuth 形式(若 MCP 端支持)
- 生产 per-request token 需要**额外一层代理**

### 3.1 OAuth 兜底(若 MCP 服务端支持)

MCP 规范允许 server 端在 401 时返回 `WWW-Authenticate: Bearer ...`,
opencode 会自动用 `oauth` 字段配置的 client credentials 走 OAuth flow。

### 3.2 推荐的 per-request token 方案(本仓库未实现,留作 TODO)

```
[hermetic_agent 前端 / 浏览器]
      │ X-MCP-Token: <user-token>
      ▼
[hermetic_agent Hub]
      │ 1. 读 header 拿 token
      │ 2. 启动 opencode serve 时,在 --config 里塞一份 per-session MCP config
      │    (mcpServers.<server>.headers.Authorization = "Bearer <user-token>")
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
- 实现位置:`src/hermetic_agent/providers/launcher.py` 的 `_render_opencode_config` 增加 MCP servers 段

---

## 4. `mcp.json` 兼容说明

`work/mcp/mcp.json`(空 `{"tools": []}`)是 **v2 时代**给 `MCPRegistry.from_config` 用的元数据列表 — 跟 opencode 无关。
当前:
- opencode 读 `servers.json`(本目录)
- `MCPRegistry` 主要用于**合成工具**(如 `ask_user`),不再列 MCP 工具

若你的 `settings.mcp_tools_config` 仍指向 `work/mcp/mcp.json`,可以保持不动(空 tools 不影响),也可以改成指向 `servers.json` 的 `"mcpServers"` 键(需要自定义 `MCPRegistry.from_config` 解析器)。

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

**关联**:`work/shared/skills/` / `work/scenarios/` (基座 / 业务 SKILL 都在这两个目录)
