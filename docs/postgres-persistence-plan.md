# OpenCode + OpenCode SDK PostgreSQL 对话持久化方案

## 1. 背景与目标

当前 `SessionManager` 使用内存存储，依赖远程 `opencode serve` 持久化。重启后数据丢失。

**目标**：通过 PostgreSQL 实现本地持久化存储，支持多实例共享会话状态。

## 2. 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                     API Layer                             │
│                  (src/openagent/api/)                     │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────┐
│               SessionManager                             │
│           (src/openagent/core/session.py)                │
│                                                          │
│  ┌─────────────────┐    ┌─────────────────────────────┐  │
│  │  Memory Cache   │    │    StorageBackend           │  │
│  │  (_sessions)    │◄──►│    (Interface)              │  │
│  └─────────────────┘    └──────────────┬──────────────┘  │
│                                         │                 │
│                         ┌───────────────┼───────────────┐│
│                         ▼               ▼               ▼│
│              ┌──────────────┐  ┌──────────────┐  ┌──────┐│
│              │MemoryStorage │  │PostgresStorage│ │Redis ││
│              └──────────────┘  └──────────────┘  └──────┘│
└─────────────────────────────────────────────────────────┘
```

## 3. 数据库表设计

### 3.1 会话表 (sessions)

```sql
CREATE TABLE sessions (
    id VARCHAR(64) PRIMARY KEY,
    title VARCHAR(255) NOT NULL DEFAULT 'New Session',
    model VARCHAR(128),
    parent_id VARCHAR(64),
    version VARCHAR(32),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_sessions_updated_at ON sessions(updated_at DESC);
```

### 3.2 消息表 (messages)

```sql
CREATE TABLE messages (
    id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant')),
    model_id VARCHAR(128),
    cost DECIMAL(12, 4) DEFAULT 0,
    tokens INT DEFAULT 0,
    error TEXT,
    summary BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_messages_session_id ON messages(session_id);
CREATE INDEX idx_messages_created_at ON messages(created_at);
```

### 3.3 消息内容表 (message_parts)

```sql
CREATE TABLE message_parts (
    id VARCHAR(64) PRIMARY KEY,
    message_id VARCHAR(64) NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    part_type VARCHAR(32) NOT NULL,
    content JSONB NOT NULL,
    part_index INT NOT NULL
);

CREATE INDEX idx_message_parts_message_id ON message_parts(message_id);
```

## 4. 数据模型映射

| SDK 类型 | 数据库表 | 说明 |
|---------|---------|------|
| `Session` | `sessions` | 会话基本信息 |
| `UserMessage` / `AssistantMessage` | `messages` | 消息主体 |
| `TextPart` / `FilePart` / `ToolPart` 等 | `message_parts` | 消息内容片段 |

### Part Type 映射

| part_type | content 结构 |
|-----------|-------------|
| `text` | `{"text": "..."}` |
| `file` | `{"path": "...", "content": "..."}` |
| `tool` | `{"tool_call_id": "...", "tool_name": "...", "input": {...}}` |
| `step_start` | `{"step": 1}` |
| `step_finish` | `{"step": 1, "duration_ms": 123}` |
| `snapshot` | `{"content": "..."}` |
| `patch` | `{"operations": [...]}` |

## 5. 存储接口定义

```python
# src/openagent/storage/base.py
from abc import ABC, abstractmethod
from typing import List, Optional, AsyncIterator
from ..types import Session, Message, Part

class StorageBackend(ABC):

    @abstractmethod
    async def create_session(self, session: Session) -> Session:
        """创建新会话"""
        pass

    @abstractmethod
    async def get_session(self, session_id: str) -> Optional[Session]:
        """获取会话"""
        pass

    @abstractmethod
    async def update_session(self, session: Session) -> Session:
        """更新会话"""
        pass

    @abstractmethod
    async def list_sessions(self, limit: int = 50, offset: int = 0) -> List[Session]:
        """列出所有会话"""
        pass

    @abstractmethod
    async def delete_session(self, session_id: str) -> None:
        """删除会话及其所有消息"""
        pass

    @abstractmethod
    async def create_message(self, message: Message) -> Message:
        """创建消息"""
        pass

    @abstractmethod
    async def get_messages(self, session_id: str) -> List[Message]:
        """获取会话的所有消息"""
        pass

    @abstractmethod
    async def create_part(self, message_id: str, part_index: int, part: Part) -> Part:
        """创建消息片段"""
        pass

    @abstractmethod
    async def get_parts(self, message_id: str) -> List[Part]:
        """获取消息的所有片段"""
        pass
```

## 6. PostgreSQL 存储实现

### 6.1 依赖

```toml
# pyproject.toml
[project]
dependencies = [
    "asyncpg>=0.29.0",
    "pydantic>=2.0",
]
```

### 6.2 实现类

```python
# src/openagent/storage/postgres.py
import json
import asyncpg
from typing import List, Optional
from .base import StorageBackend
from ..types import Session, Message, Part, UserMessage, AssistantMessage
from ..types.parts import TextPart, FilePart, ToolPart

class PostgresStorage(StorageBackend):
    DSN: str

    def __init__(self, dsn: str):
        self.pool: asyncpg.Pool = None
        self.DSN = dsn

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(
            self.DSN,
            min_size=5,
            max_size=20,
        )

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()

    async def init_schema(self) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id VARCHAR(64) PRIMARY KEY,
                    title VARCHAR(255) NOT NULL DEFAULT 'New Session',
                    model VARCHAR(128),
                    parent_id VARCHAR(64),
                    version VARCHAR(32),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id VARCHAR(64) PRIMARY KEY,
                    session_id VARCHAR(64) NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant')),
                    model_id VARCHAR(128),
                    cost DECIMAL(12, 4) DEFAULT 0,
                    tokens INT DEFAULT 0,
                    error TEXT,
                    summary BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS message_parts (
                    id VARCHAR(64) PRIMARY KEY,
                    message_id VARCHAR(64) NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
                    part_type VARCHAR(32) NOT NULL,
                    content JSONB NOT NULL,
                    part_index INT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
                CREATE INDEX IF NOT EXISTS idx_message_parts_message_id ON message_parts(message_id);
            """)

    async def create_session(self, session: Session) -> Session:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO sessions(id, title, model, parent_id, version)
                   VALUES($1, $2, $3, $4, $5)""",
                session.id, session.title, session.model,
                session.parent_id, session.version
            )
        return session

    async def get_session(self, session_id: str) -> Optional[Session]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM sessions WHERE id = $1", session_id
            )
        if not row:
            return None
        return self._row_to_session(row)

    async def update_session(self, session: Session) -> Session:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """UPDATE sessions SET title=$2, model=$3, updated_at=NOW()
                   WHERE id=$1""",
                session.id, session.title, session.model
            )
        return session

    async def list_sessions(self, limit: int = 50, offset: int = 0) -> List[Session]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT * FROM sessions ORDER BY updated_at DESC
                   LIMIT $1 OFFSET $2""",
                limit, offset
            )
        return [self._row_to_session(r) for r in rows]

    async def delete_session(self, session_id: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM sessions WHERE id = $1", session_id)

    async def create_message(self, message: Message) -> Message:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO messages(id, session_id, role, model_id, cost, tokens, error, summary)
                   VALUES($1, $2, $3, $4, $5, $6, $7, $8)""",
                message.id, message.session_id, message.role,
                getattr(message, 'modelID', None),
                getattr(message, 'cost', 0),
                getattr(message, 'tokens', 0),
                getattr(message, 'error', None),
                getattr(message, 'summary', False)
            )
        return message

    async def get_messages(self, session_id: str) -> List[Message]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT * FROM messages WHERE session_id = $1 ORDER BY created_at""",
                session_id
            )
        return [self._row_to_message(r) for r in rows]

    async def create_part(self, message_id: str, part_index: int, part: Part) -> Part:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO message_parts(id, message_id, part_type, content, part_index)
                   VALUES($1, $2, $3, $4, $5)""",
                part.id, message_id, part.type, json.dumps(part.model_dump()), part_index
            )
        return part

    async def get_parts(self, message_id: str) -> List[Part]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT * FROM message_parts
                   WHERE message_id = $1 ORDER BY part_index""",
                message_id
            )
        return [self._row_to_part(r) for r in rows]

    def _row_to_session(self, row) -> Session:
        return Session(
            id=row['id'],
            title=row['title'],
            model=row['model'],
            parent_id=row['parent_id'],
            version=row['version'],
            time=row['created_at'],
        )

    def _row_to_message(self, row) -> Message:
        if row['role'] == 'user':
            return UserMessage(
                id=row['id'],
                session_id=row['session_id'],
                role='user',
                time=row['created_at'],
            )
        else:
            return AssistantMessage(
                id=row['id'],
                session_id=row['session_id'],
                role='assistant',
                modelID=row['model_id'],
                cost=row['cost'],
                tokens=row['tokens'],
                error=row['error'],
                summary=row['summary'],
                time=row['created_at'],
            )

    def _row_to_part(self, row) -> Part:
        content = json.loads(row['content'])
        part_type = row['part_type']
        if part_type == 'text':
            return TextPart(**content)
        elif part_type == 'file':
            return FilePart(**content)
        elif part_type == 'tool':
            return ToolPart(**content)
        # ... 其他类型
        raise ValueError(f"Unknown part type: {part_type}")
```

## 7. 配置修改

### 7.1 新增配置项

```python
# src/openagent/config/settings.py
from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # ... 现有配置 ...

    storage_backend: str = Field(
        default="memory",
        description="存储后端: memory | postgres"
    )
    postgres_dsn: str = Field(
        default="postgresql://localhost:5432/opencode",
        description="PostgreSQL 连接字符串"
    )
    postgres_pool_min_size: int = Field(default=5, ge=1)
    postgres_pool_max_size: int = Field(default=20, ge=1)
```

### 7.2 环境变量

```bash
# .env
STORAGE_BACKEND=postgres
POSTGRES_DSN=postgresql://user:password@localhost:5432/opencode
POSTGRES_POOL_MIN_SIZE=5
POSTGRES_POOL_MAX_SIZE=20
```

## 8. SessionManager 改造

```python
# src/openagent/core/session.py
from typing import Optional
from ..storage.base import StorageBackend
from ..storage.memory import MemoryStorage
from ..storage.postgres import PostgresStorage
from ..types import Session, Message

class SessionManager:
    _sessions: dict[str, SessionInfo]
    _clients: dict[str, AsyncOpencode]
    _storage: StorageBackend

    def __init__(self, settings: Settings):
        self._settings = settings
        self._storage = self._create_storage()
        self._sessions = {}
        self._clients = {}

    def _create_storage(self) -> StorageBackend:
        backend = self._settings.storage_backend
        if backend == "postgres":
            storage = PostgresStorage(self._settings.postgres_dsn)
            if self._settings.postgres_pool_min_size:
                # 自定义 pool size
                pass
            return storage
        return MemoryStorage()

    async def initialize(self) -> None:
        """初始化存储连接"""
        await self._storage.connect()
        if hasattr(self._storage, 'init_schema'):
            await self._storage.init_schema()

    async def create(
        self,
        agent_name: str,
        model: Optional[str] = None,
        **kwargs
    ) -> SessionInfo:
        client = self._clients.get(agent_name)
        if not client:
            raise ValueError(f"Agent not found: {agent_name}")

        session = await client.session.create(model=model, **kwargs)
        await self._storage.create_session(session)

        info = SessionInfo(session_id=session.id, agent_name=agent_name, ...)
        self._sessions[session.id] = info
        return info

    async def get_messages(self, session_id: str) -> List[Message]:
        # 优先从存储读取
        messages = await self._storage.get_messages(session_id)
        if messages:
            return messages
        # Fallback: 远程获取
        ...
```

## 9. 应用启动改造

```python
# src/openagent/api/app.py
async def create_app() -> Sanic:
    app = Sanic("opencode-agent-hub")

    settings = Settings()
    session_manager = SessionManager(settings)
    await session_manager.initialize()

    @app.before_server_stop
    async def cleanup(app, loop):
        await session_manager._storage.close()

    return app
```

## 10. 迁移现有数据 (可选)

```python
# src/openagent/scripts/migrate_to_postgres.py
"""
从远程 opencode serve 拉取所有会话并写入本地 PostgreSQL
"""
import asyncio
from opencode_ai import AsyncOpencode

async def migrate():
    client = AsyncOpencode(base_url="http://localhost:8080")
    sessions = await client.session.list()

    storage = PostgresStorage("postgresql://localhost:5432/opencode")
    await storage.connect()
    await storage.init_schema()

    for session in sessions:
        await storage.create_session(session)
        messages = await client.session.messages(session.id)
        for msg in messages:
            await storage.create_message(msg.info)
            for i, part in enumerate(msg.parts):
                await storage.create_part(msg.info.id, i, part)

    await storage.close()
```

## 11. 方案优势

| 特性 | 说明 |
|-----|------|
| **本地持久化** | 重启不丢失数据 |
| **多实例共享** | 多个 openagent 实例可共享同一数据库 |
| **解耦远程依赖** | 不强依赖 opencode serve 的持久化能力 |
| **可扩展** | 易于切换到 MySQL/Redis 等其他存储 |
| **性能** | asyncpg 异步驱动，连接池复用 |

## 12. 潜在问题与解决

| 问题 | 解决方案 |
|-----|---------|
| 远程/本地数据不一致 | 优先写本地存储，远程仅作缓存 |
| Part 类型扩展 | 使用 JSONB 存储，运行时解析 |
| 大会话查询性能 | 按时间分页，避免一次性加载全量 |
