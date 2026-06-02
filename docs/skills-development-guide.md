# OpenCode Skill 开发与注入方案

## 1. Skill 目录结构

```
.opencode/skills/<skill-name>/SKILL.md
~/.config/opencode/skills/<skill-name>/SKILL.md
~/.claude/skills/<skill-name>/SKILL.md
```

## 2. Skill 文件格式

```markdown
---
name: <skill-name>
description: 简短描述 + 触发关键词（必填，描述要说明何时触发）
---

# Skill 标题

## 触发条件
（可选）

## 使用说明
（可选）

## 示例
（可选）
```

## 3. 注册到 opencode.json

在 `opencode.json` 中配置 skill 路径：

```json
{
  "skills": {
    "paths": [
      ".opencode/skills",
      "自定义路径"
    ],
    "urls": [
      "https://example.com/skills/"
    ]
  }
}
```

## 4. 不同场景的 Skill 设计

| 场景 | 设计要点 |
|------|----------|
| **代码审查** | 描述中包含 `review`、`PR`、`代码审查` 等关键词 |
| **API 开发** | 描述中包含 `API`、`endpoint`、`REST`、`GraphQL` |
| **数据库** | 描述中包含 `SQL`、`database`、`migration` |
| **测试** | 描述中包含 `test`、`测试`、`pytest`、`jest` |
| **部署** | 描述中包含 `deploy`、`部署`、`CI/CD` |
| **文档** | 描述中包含 `docs`、`文档`、`README` |
| **重构** | 描述中包含 `refactor`、`重构`、`代码优化` |

### 示例：API 开发 Skill

```markdown
---
name: api-dev
description: API 设计与实现。触发词：API、endpoint、REST、GraphQL、接口开发
---

# API 开发技能

## 职责
- 设计 RESTful API
- 编写 FastAPI/Sanic/Flask 路由
- 生成 OpenAPI/Swagger 文档

## 规范
- 路由文件不超过 500 行
- 使用依赖注入
- 统一错误响应格式
```

## 5. 通过 SDK 动态注入 Skill

在项目代码中动态注册 skill：

```python
from opencode import OpenCode

client = OpenCode()

# 方式一：直接注册 skill 路径
client.register_skill(
    name="my-skill",
    path="./skills/my-skill/SKILL.md"
)

# 方式二：传入 skill 内容
client.register_skill_content(
    name="api-dev",
    description="API 开发技能",
    content="# API 开发技能\n\n..."
)

# 方式三：场景化批量注册
SCENE_SKILLS = {
    "api": ["api-dev", "database", "docs"],
    "frontend": ["react", "css", "testing"],
}

def inject_scene(client: OpenCode, scene: str):
    for skill_name in SCENE_SKILLS.get(scene, []):
        client.register_skill(name=skill_name)
```

## 6. 使用方式

对话时，opencode 会根据 skill 的 `description` 关键词自动匹配适合的 skill。

```bash
# 用户说 "帮我设计一个用户登录的 API"
# opencode 自动匹配 api-dev skill
```

## 7. 最佳实践

1. **description 关键词要靠前**：`description: API 开发。触发词：REST、GraphQL`
2. **单职责任**：一个 skill 只做一件事
3. **文件命名**：文件夹名与 `name` 一致
4. **分层注册**：
   - 全局通用 skill → `~/.config/opencode/skills/`
   - 项目专用 skill → `.opencode/skills/`
5. **禁用不需要的 skill**：在 `opencode.json` 中排除或禁用

## 8. 动态注入示例

```python
from opencode import OpenCode
from pathlib import Path

def load_project_skills(project_path: str):
    """加载项目下的所有 skill"""
    skill_dir = Path(project_path) / ".opencode" / "skills"
    skills = {}
    for skill_path in skill_dir.rglob("SKILL.md"):
        name = skill_path.parent.name
        skills[name] = skill_path.read_text(encoding="utf-8")
    return skills

def inject_skills_by_context(client: OpenCode, context: dict):
    """根据上下文注入相关 skill"""
    scene = context.get("scene", "general")

    skill_map = {
        "api": ["api-dev", "database-migration"],
        "web": ["frontend", "css", "testing"],
        "data": ["data-pipeline", "sql", "visualization"],
    }

    for skill in skill_map.get(scene, []):
        client.register_skill(name=skill)

# 使用
client = OpenCode()
inject_skills_by_context(client, {"scene": "api"})
```

---

## 9. MCP 场景化加载方案

MCP（Model Context Protocol）用于连接外部工具服务器。opencode 通过 `opencode.json` 中的 `mcp` 字段配置。

### 9.1 MCP 配置格式

```json
{
  "mcp": {
    "<server-name>": {
      "type": "local" | "remote",
      "command": ["npx", "-y", "@playwright/mcp"],
      "url": "https://...",
      "headers": {},
      "env": {},
      "enabled": true
    }
  }
}
```

### 9.2 不同场景的 MCP 设计

| 场景 | MCP 服务器 | 用途 |
|------|-----------|------|
| **前端开发** | `playwright` | 浏览器自动化、UI 测试 |
| **后端开发** | `postgresql` | 数据库操作 |
| **API 开发** | `swagger` | API 文档与测试 |
| **云服务** | `aws`, `azure`, `gcp` | 云资源管理 |
| **Git** | `github`, `gitlab` | 代码仓库操作 |
| **容器** | `docker`, `kubernetes` | 容器编排 |

### 9.3 场景化 MCP 配置示例

```json
{
  "mcp": {
    "playwright": {
      "type": "local",
      "command": ["npx", "-y", "@playwright/mcp"],
      "enabled": true
    },
    "github": {
      "type": "remote",
      "url": "https://github-mcp-server.example.com",
      "headers": { "Authorization": "Bearer ${GITHUB_TOKEN}" },
      "enabled": false
    },
    "postgresql": {
      "type": "local",
      "command": ["npx", "-y", "@modelcontextprotocol/server-postgres"],
      "env": { "DATABASE_URL": "postgresql://localhost:5432/mydb" },
      "enabled": false
    }
  }
}
```

### 9.4 通过 SDK 动态切换 MCP

```python
from opencode import OpenCode

client = OpenCode()

SCENE_MCP = {
    "frontend": ["playwright"],
    "backend": ["postgresql", "redis"],
    "devops": ["docker", "kubernetes", "aws"],
    "api": ["swagger", "postman"],
}

def switch_mcp_scene(client: OpenCode, scene: str):
    """切换 MCP 场景"""
    for mcp_name, config in SCENE_MCP.items():
        client.set_mcp_enabled(mcp_name, mcp_name in config)

def enable_mcp(client: OpenCode, mcp_name: str):
    """启用指定的 MCP"""
    client.set_mcp_enabled(mcp_name, True)

def disable_mcp(client: OpenCode, mcp_name: str):
    """禁用指定的 MCP"""
    client.set_mcp_enabled(mcp_name, False)

# 使用
client = OpenCode()
switch_mcp_scene(client, "frontend")  # 只启用 playwright
switch_mcp_scene(client, "backend")    # 切换到 postgresql + redis
```

### 9.5 动态注册新的 MCP 服务器

```python
from opencode import OpenCode

client = OpenCode()

client.register_mcp(
    name="custom-mcp",
    mcp_type="local",
    command=["npx", "-y", "@custom/mcp-server"],
    env={"CUSTOM_VAR": "value"}
)

client.register_mcp(
    name="remote-mcp",
    mcp_type="remote",
    url="https://mcp-server.example.com",
    headers={"Authorization": "Bearer ${API_TOKEN}"}
)
```

### 9.6 场景化 MCP + Skill 联动

```python
from opencode import OpenCode

SCENE_CONFIG = {
    "frontend": {
        "skills": ["react-dev", "css-expert", "playwright-testing"],
        "mcps": ["playwright"]
    },
    "backend": {
        "skills": ["api-dev", "database-migration", "auth-implementation"],
        "mcps": ["postgresql", "redis"]
    },
    "devops": {
        "skills": ["docker-compose", "kubernetes-deploy", "ci-cd"],
        "mcps": ["docker", "kubernetes", "aws"]
    },
}

def inject_full_scene(client: OpenCode, scene: str):
    """同时注入 skill 和 MCP"""
    config = SCENE_CONFIG.get(scene, {})
    
    for skill_name in config.get("skills", []):
        client.register_skill(name=skill_name)
    
    for mcp_name in config.get("mcps", []):
        client.set_mcp_enabled(mcp_name, True)

# 使用
client = OpenCode()
inject_full_scene(client, "frontend")
```

### 9.7 最佳实践

1. **按需启用**：生产环境只启用必要的 MCP，禁用不相关的
2. **环境隔离**：敏感 MCP（如 `aws`、`github`）使用环境变量存储密钥
3. **命名规范**：MCP 名称使用小写字母和连字符
4. **超时控制**：`experimental.mcp_timeout` 设置全局 MCP 超时时间
5. **权限控制**：配合 `permission` 字段限制 MCP 工具的执行权限
