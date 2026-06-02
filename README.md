# OpenCode Agent Scheduler Hub

> 私有化智能体调度中枢 - 基于 OpenCode 引擎的企业级 AI Agent 调度平台

## 核心架构

```
┌─────────────────────────────────────────────────────────────┐
│                      调度中枢 (Python)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │AgentPoolManager│  │SessionManager│  │  Scheduler   │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
│         │                 │                  │              │
│         └─────────────────┴──────────────────┘              │
│                           │                                  │
│              ┌────────────┴────────────┐                    │
│              │      opencode-ai       │                    │
│              └────────────┬────────────┘                    │
└───────────────────────────┼─────────────────────────────────┘
                            │ HTTP REST
                     ┌──────┴──────┐
                     │opencode serve│
                     │  :4091/4092  │
                     └─────────────┘
```

## 快速开始

### 前置要求

- Python >= 3.10
- opencode CLI (`opencode serve` 命令)
- opencode-ai Python SDK

### 安装

#### 使用 pip

```bash
# 1. 克隆项目
git clone https://github.com/your-org/agent-scheduler-hub.git
cd agent-scheduler-hub

# 2. 创建虚拟环境（推荐）
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# 或
.venv\Scripts\activate  # Windows

# 3. 安装核心依赖
pip install -e .

# 4. 安装 opencode Python SDK（当前为预发布包）
pip install --pre opencode-ai

# 5. 安装开发依赖（可选）
pip install -e ".[dev]"
```

#### 使用 uv

```bash
# 1. 克隆项目
git clone https://github.com/your-org/agent-scheduler-hub.git
cd agent-scheduler-hub

# 2. 使用 uv 创建虚拟环境并安装
uv venv
uv pip install -e .

# 3. 安装 opencode Python SDK（当前为预发布包）
uv pip install --pre opencode-ai

# 4. 安装开发依赖（可选）
uv pip install -e ".[dev]"
```

### 配置

复制环境变量示例文件并修改：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```bash
# OpenCode 连接配置
OPENCODE_BASE_URL=http://localhost:4096
OPENCODE_USERNAME=
OPENCODE_PASSWORD=

# 服务器配置
AGENT_SCHEDULER_HOST=0.0.0.0
AGENT_SCHEDULER_PORT=18000

# 日志配置
AGENT_SCHEDULER_LOG_LEVEL=INFO
AGENT_SCHEDULER_LOG_FORMAT=json
```

### 启动 OpenCode 服务

在一个终端启动 opencode serve：

```bash
# 本地开发模式
opencode serve --port 4096 --hostname 127.0.0.1

# 生产模式（开启认证）
OPENCODE_SERVER_PASSWORD=your-secret-pass opencode serve --port 4096 --hostname 0.0.0.0
```

### 启动调度中枢

```bash
# 方式一：使用 CLI 命令（需 pip install -e .）
agent-scheduler

# 方式二：使用 python -m 模块运行
python -m openagent.main

# 方式三：使用 uv 运行
uv run python -m openagent.main
```

服务启动后，API 文档地址：`http://localhost:8000/docs`

### 验证安装

```bash
# 健康检查
curl http://localhost:8000/health

# 查看实例池状态
curl http://localhost:8000/agent/pool/stats

# 注册 Agent 实例
curl -X POST http://localhost:8000/agent/pool/register \
  -H "Content-Type: application/json" \
  -d '{"name": "default", "base_url": "http://localhost:4096"}'

# 发送测试消息
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你好，测试一下"}'
```

### 运行测试

```bash
# 使用 pip
pip install -e ".[dev]"
pytest -v

# 使用 uv
uv pip install -e ".[dev]"
uv run pytest -v
```

## 核心模块

### AgentPoolManager

管理和调度多个 opencode serve 实例。

```python
from openagent.core import AgentPoolManager

pool = AgentPoolManager()
pool.register("agent-shanghai", "http://192.168.1.101:4096")
pool.register("agent-beijing", "http://192.168.1.102:4096")

instance = await pool.acquire_idle_instance()
pool.release("agent-shanghai")
```

### SessionManager

封装 opencode serve 的 Session API，负责会话生命周期管理。

```python
from openagent.core import SessionManager

sessions = SessionManager(pool)
session_id = await sessions.create("agent-shanghai", model="claude-sonnet")
response = await sessions.chat(session_id, "帮我分析这份代码")
history = await sessions.get_messages(session_id)
await sessions.delete(session_id)
```

### Scheduler

编排任务与 Agent 实例的映射关系。

```python
from openagent.core import Scheduler

scheduler = Scheduler(pool, sessions)

# 单任务
result = await scheduler.run("帮我写一个快速排序算法")

# 多任务并行
results = await scheduler.run_parallel([
    "任务1：分析代码结构",
    "任务2：生成单元测试",
    "任务3：编写 API 文档"
])
```

## REST API

### 会话相关

| 方法 | 端点 | 描述 |
|------|------|------|
| `POST` | `/agent/chat` | 发送消息并获取回复（自动创建会话） |
| `POST` | `/agent/session` | 创建新会话 |
| `GET` | `/agent/session/{session_id}` | 获取会话信息 |
| `GET` | `/agent/session/{session_id}/messages` | 获取会话历史消息 |
| `DELETE` | `/agent/session/{session_id}` | 删除会话 |
| `POST` | `/agent/session/{session_id}/abort` | 中止运行中的会话 |
| `POST` | `/agent/session/{session_id}/revert` | 回退会话到上一状态 |

### 实例池相关

| 方法 | 端点 | 描述 |
|------|------|------|
| `POST` | `/agent/pool/register` | 注册新 Agent 实例 |
| `DELETE` | `/agent/pool/{name}` | 注销 Agent 实例 |
| `GET` | `/agent/pool/stats` | 获取实例池统计信息 |

### 系统相关

| 方法 | 端点 | 描述 |
|------|------|------|
| `GET` | `/health` | 健康检查 |
| `GET` | `/ready` | 就绪检查（含实例池状态） |
| `GET` | `/docs` | Swagger API 文档（Sanic 自动提供） |

## 许可证

MIT
