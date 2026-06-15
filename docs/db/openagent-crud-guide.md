# OpenAgent · 持久层 CRUD 初始化操作指南

> 版本: v1  ·  配套: v2 schema (`docs/db/openagent-schema.sql`)
> 范围: 6 个实体, Models / DTO / Repositories / Services 4 层完整落地

---

## 0. 层次总览

```
src/openagent/store/
├── __init__.py                  # 公开 API 入口
├── driver.py                    # ① 驱动层: MySQL 连接池 + 事务 + 启动 DDL
├── exceptions.py                # ② 异常体系 (StoreError / NotFoundError / ...)
│
├── models/                      # ③ Models 层 = Java DO/Entity
│   ├── _common.py               #    bool/dict/datetime 转换辅助
│   ├── scenario.py              #    6 个 @dataclass
│   ├── session.py
│   ├── chat_turn.py
│   ├── message.py
│   ├── part.py
│   └── audit_log.py
│
├── dto/                         # ④ DTO 层 = Java DTO/VO
│   ├── _common.py               #    pydantic 公共基类
│   ├── scenario.py              #    Create/Update/Response × 6
│   ├── session.py
│   ├── chat_turn.py
│   ├── message.py
│   ├── part.py
│   └── audit_log.py
│
├── repositories/                # ⑤ Repositories 层 = Java DAO/Mapper
│   ├── _base.py                 #    Repository ABC (通用 CRUD 抽象)
│   ├── scenario_repo.py         #    6 个实体 ABC
│   ├── session_repo.py
│   ├── chat_turn_repo.py
│   ├── message_repo.py
│   ├── part_repo.py
│   ├── audit_log_repo.py
│   ├── mysql/                   #    MySQL 实现 × 6
│   │   ├── scenario_repo_mysql.py
│   │   └── ...
│   └── memory/                  #    Memory 实现 × 6 (dev/test)
│       ├── _base.py
│       ├── scenario_repo_memory.py
│       └── ...
│
└── services/                    # ⑥ Services 层 = Java Service
    ├── scenario_service.py      #    6 个业务服务
    ├── session_service.py
    ├── chat_turn_service.py
    ├── message_service.py
    ├── part_service.py
    ├── audit_log_service.py
    └── container.py             #    工厂: 6 个 Service 装配成 ServiceContainer
```

---

## 1. 依赖 & 配置

### 1.1 装驱动

```bash
pip install asyncmy pymysql
```

`asyncmy` 是纯异步 MySQL 驱动, 与 Sanic 全异步栈友好. 备选 `aiomysql` (老牌但维护节奏慢).

### 1.2 环境变量

`.env`:
```ini
AGENT_SCHEDULER_STORAGE_BACKEND=mysql
AGENT_SCHEDULER_MYSQL_DSN=mysql://root:1014@127.0.0.1:13306/openagent
AGENT_SCHEDULER_MYSQL_POOL_MIN_SIZE=5
AGENT_SCHEDULER_MYSQL_POOL_MAX_SIZE=20
AGENT_SCHEDULER_MYSQL_ECHO=false
```

DSN 格式: `mysql://user:password@host:port/database?charset=utf8mb4`

---

## 2. Models 层 — 与 DB schema 1:1

### 设计原则

| 原则 | 体现 |
|------|------|
| 字段命名 = DB 列名 (snake_case) | `id` / `user_id` / `created_at` / `is_deleted` ... |
| 字段类型用 Python 原生 | `str` / `int` / `Decimal` / `datetime` / `dict \| None` / `bool` |
| 必填字段无默认值 | `code: str` 不给 default |
| 可选字段 `field(default=None)` | `description: str \| None = None` |
| 时间字段默认 `utcnow()` | `created_at: datetime = field(default_factory=utcnow)` |
| 每个 Model 提供 `to_db_dict()` + `from_db_dict(row)` | 互转, 处理 bool ↔ 0/1 / dict ↔ JSON 字符串 |

### 类型映射

| DB 类型 | Python 类型 | 转换说明 |
|---------|------------|---------|
| `VARCHAR / CHAR / TEXT` | `str` | asyncmy 自动 |
| `INT / INT UNSIGNED` | `int` | asyncmy 自动 |
| `DECIMAL(12,6)` | `Decimal` | asyncmy 自动 (重要: 别用 `float` 算钱) |
| `DATETIME(6)` | `datetime` (naive) | asyncmy 自动 |
| `TINYINT(1)` | `bool` | `to_db_bool()` / `from_db_bool()` 在 `_common.py` |
| `JSON` | `dict` / `list` | `to_db_json()` (dict → str) / `from_db_json()` (str → dict) |
| `NULL` | `None` | asyncmy 自动 |

### 示例: `Scenario` Model

```python
from openagent.store.models import Scenario

s = Scenario(
    code="flight-booking",
    name="机票订购",
    config={"routing": {"strategy": "default"}},
    version=1,
)
s.id  # auto-generated UUID
s.created_at  # utcnow()
db_dict = s.to_db_dict()    # -> dict ready for INSERT
```

---

## 3. DTO 层 — 跨层数据传递

### 命名规范

- `CreateXxxRequest` — 创建入参
- `UpdateXxxRequest` — 更新入参 (所有字段 Optional)
- `XxxResponse` — 出参 (含 `from_model(model)` 工厂)

### 示例

```python
from openagent.store import CreateScenarioRequest, ScenarioResponse, UpdateScenarioRequest
from openagent.store.dto._common import iso_or_none

# 入参
req = CreateScenarioRequest(
    code="flight-booking",
    name="机票订购",
    config={"routing": {}},
    version=1,
)

# 出参 (Service 层 from_model 转换)
resp = ScenarioResponse.from_model(scenario_model)
print(resp.code, resp.config)
```

### 公共基类

```python
class DTOMixin(BaseModel):
    model_config = ConfigDict(
        extra="forbid",            # 拒绝未知字段
        str_strip_whitespace=True, # 自动 strip 字符串
    )
```

---

## 4. Repositories 层 — DAO/Mapper

### 4.1 抽象基类 (Repository ABC)

```python
class Repository[M](ABC):
    @abstractmethod
    async def get_by_id(self, entity_id: str) -> M | None: ...
    @abstractmethod
    async def list(self, *, limit=50, offset=0, include_deleted=False, **filters) -> list[M]: ...
    @abstractmethod
    async def count(self, *, include_deleted=False, **filters) -> int: ...
    @abstractmethod
    async def create(self, model: M) -> M: ...
    @abstractmethod
    async def update(self, entity_id: str, **fields) -> M | None: ...
    @abstractmethod
    async def soft_delete(self, entity_id: str) -> bool: ...
    @abstractmethod
    async def hard_delete(self, entity_id: str) -> bool: ...
```

### 4.2 业务方法 (每个实体 ABC 自定义)

| 实体 | 业务方法 |
|------|---------|
| `ScenarioRepository` | `get_by_code_version`, `list_active`, `create_new_version` |
| `SessionRepository` | `list_by_user`, `list_by_scenario`, `update_aggregates` |
| `ChatTurnRepository` | `list_by_session`, `list_by_status`, `mark_started`, `mark_finished` |
| `MessageRepository` | `list_by_session`, `list_by_turn` |
| `PartRepository` | `list_by_message`, `list_by_session` (用 session_id 冗余), `batch_create` |
| `AuditLogRepository` | `list_by_resource`, `list_by_actor`, `next_seq` (append-only, update/delete 抛 NotImplementedError) |

### 4.3 两套实现

| 实现 | 用途 | 关键差异 |
|------|------|---------|
| `MySQLXxxRepository` | 生产 | asyncmy + 真 MySQL, 完整 SQL |
| `MemoryXxxRepository` | dev / test | dict 内存, 共享 `MemoryRepository` 基类 |

**使用建议**: Service 层只依赖 ABC (`ScenarioRepository` 等), **不要** import MySQL/Memory 具体类. 装配在 `container.py` 完成.

---

## 5. Services 层 — 业务编排

### 5.1 职责

1. **DTO 校验 + 业务规则** (pydantic DTO 之外的额外校验)
2. **跨 Repository 编排** (例: 创建 turn 时同时累加 session 聚合字段)
3. **写 audit_logs** (create / update / state_change / delete)
4. **异常包装** (`NotFoundError` 等)
5. **事务边界** (用 `MySQLPool.transaction()` 上下文管理器)

### 5.2 6 个 Service 一览

| Service | 主要业务方法 |
|---------|-------------|
| `ScenarioService` | `create` / `update` / `create_new_version` / `soft_delete` / `list_active` |
| `SessionService` | `create` / `update` / `close` / `accumulate_turn` / `set_message_count` |
| `ChatTurnService` | `create` / `start` / `complete` (累加聚合) / `fail` (写 error) / `cancel` |
| `MessageService` | `create` (含批量 parts) / `list_by_session_with_parts` (避免 N+1) |
| `PartService` | `create` / `batch_create` / `list_by_session` |
| `AuditLogService` | `record` (支持 use_seq 自动取下一序号) / `list_by_resource` |

### 5.3 典型调用: 完整 chat turn 生命周期

```python
from openagent.store import (
    ServiceContainer,
    CreateSessionRequest,
    CreateChatTurnRequest,
    CreateMessageRequest,
)

container: ServiceContainer = ...  # 工厂装配得到

# 1. 建 session
sess = await container.session.create(
    CreateSessionRequest(user_id="u-1", title="hello", agent_name="default"),
    actor_id="u-1",
)

# 2. 建 turn (status=pending)
turn = await container.chat_turn.create(
    CreateChatTurnRequest(session_id=sess.id, agent_name="default"),
)

# 3. 启动 (status=running, started_at=now)
await container.chat_turn.start(turn.id)

# 4. 发 user 消息 (含 parts)
await container.message.create(
    CreateMessageRequest(
        session_id=sess.id, turn_id=turn.id, role="user",
        content="帮我订机票",
        parts=[...],  # 一起创建
    ),
)

# 5. 发 assistant 消息
await container.message.create(
    CreateMessageRequest(
        session_id=sess.id, turn_id=turn.id, role="assistant", content="好的",
    ),
)

# 6. 完成 turn (status=success, 累加 session 聚合)
await container.chat_turn.complete(
    turn.id,
    cost=0.003, tokens_input=150, tokens_output=80,
)

# 7. 校验: session.message_count=2, tokens_input=150
sess_after = await container.session.get_by_id(sess.id)
assert sess_after.message_count == 2
```

---

## 6. 工厂装配

### 6.1 从 settings 自动装配

```python
from openagent.store import build_container_from_settings
from openagent.config.settings import get_settings

settings = get_settings()
container = build_container_from_settings(settings)  # 根据 storage_backend 自动选
```

`build_container_from_settings` 根据 `settings.storage_backend` 选 backend:
- `"memory"` → `MemoryXxxRepository` 装配
- `"mysql"` → `MySQLXxxRepository` 装配, 内部创建 `MySQLPool`

### 6.2 手动注入 (测试友好)

```python
from openagent.store import build_container, MySQLPool, MySQLConfig

pool = MySQLPool(MySQLConfig.from_dsn("mysql://root:1014@127.0.0.1:13306/openagent"))
await pool.connect()
await pool.init_schema(DDL_SQL)

container = build_container(
    scenario_repo=MySQLScenarioRepository(pool),
    session_repo=MySQLSessionRepository(pool),
    ...
)
```

### 6.3 内存版 (无 MySQL)

```python
from openagent.store import build_container
from openagent.store.repositories.memory import (
    MemoryScenarioRepository, MemorySessionRepository, ...
)

container = build_container(
    scenario_repo=MemoryScenarioRepository(),
    session_repo=MemorySessionRepository(),
    ...
)
```

---

## 7. 异常体系

```python
class StoreError(Exception): ...
class NotFoundError(StoreError):    # 实体不存在
class DuplicateError(StoreError):   # 唯一约束冲突
class ValidationError(StoreError):  # 入参校验失败
class TransactionError(StoreError): # 事务回滚 / 死锁
class DriverError(StoreError):      # 底层驱动异常
```

约定:
- **Repository** 层 `get_by_id` 找不到返回 `None`, **不抛** `NotFoundError` (让业务决定)
- **Service** 层 `get_by_id` 找不到抛 `NotFoundError("scenario", id)`
- API 层捕获 `StoreError` 转 4xx/5xx HTTP

---

## 8. 测试

### 8.1 跑测试

```bash
# 全部 store 测试 (含 MySQL 集成)
pytest tests/store/ -v

# 仅 memory 单元测试 (无 MySQL 依赖, 跑得快)
pytest tests/store/test_memory_repo.py -v

# 自定义 DSN
OPENAGENT_TEST_MYSQL_DSN=mysql://user:pass@host:3306/db pytest tests/store/
```

### 8.2 测试覆盖 (17 个, 全部通过)

| 文件 | 覆盖 |
|------|------|
| `test_memory_repo.py` | 4 个 memory 单元测试 (CRUD / list / soft_delete / seq) |
| `test_session_repo_mysql.py` | 5 个 MySQL Session 测试 (CRUD / list / JSON 往返 / 不存在 / hard_delete) |
| `test_scenario_service.py` | 5 个 Scenario Service 测试 (create / audit / dup / update / 404) |
| `test_e2e_lifecycle.py` | 3 个端到端测试 (完整 chat turn / fail / close) |

### 8.3 测试 fixture

`tests/store/conftest.py` 提供:
- `mysql_pool` — 真实 MySQL 池, 启动期 `init_schema` 加载 DDL
- `memory_container` — 纯内存 ServiceContainer
- `service_container` — MySQL 装配的 ServiceContainer
- 6 个 repo fixtures

---

## 9. 后续 TODO

- [ ] 把 `lifecycle.py` 老 `SessionRepositoryFactory` 调用替换为新 `build_container_from_settings`
- [ ] 修老 `tests/conftest.py` 的 `MemoryStorage` 引用 (或保留兼容, 当前已兼容)
- [ ] 接入 Sanic app startup: `pool.connect() + init_schema()`
- [ ] 加 Prometheus 指标: 每个 Repository 操作的耗时 / 错误率
- [ ] 加 Alembic 风格的 migration 文件管理 (目前用 DDL 幂等执行, 够用)
