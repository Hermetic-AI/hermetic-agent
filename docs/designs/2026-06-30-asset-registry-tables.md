# 资产注册中心表结构完整设计

> 主文档: `2026-06-30-asset-registry-design.md`
>
> 本附录展开 §3 数据模型，提供完整的 Tortoise 模型定义、内存/数据库两侧 Repository 接口、以及 DDL 视角的等价 SQL。

---

## 1. 设计原则

1. **复用既有 Skill / McpConfig 模型，扩展字段**: `owner_user_id`, `visibility`。不重建表。
2. **新增 3 个模型**: `Prompt`、`Command`、`Agent`。
3. **统一软删除、审计字段**: 所有 5 张表带同一组列；索引 `(owner_user_id, visibility, is_deleted)` 覆盖常见的 `list_mine() ∪ list_public()` 查询。
4. **DB FK 不强制**: `Agent.*_codes` 用 `JSONField` 存引用列表（而不是外键），便于软删除/版本化时灵活降级，缺失引用只是被过滤，不级联崩溃。
5. **Memory 后端逐字段镜像**: `Memory*Repository` 内部用 dict 持有模型实例，对外接口与 `MySQL*Repository` 一一对应。

---

## 2. Tortoise 模型完整定义

### 2.1 既有 `Skill`（**只追加字段，不改签名**）

```python
# src/hermetic_agent/store/models/skill.py
from tortoise import fields
from tortoise.models import Model


class Skill(Model):
    id = fields.UUIDField(pk=True, binary=False)
    code = fields.CharField(max_length=128, unique=True)
    name = fields.CharField(max_length=255)
    version = fields.IntField(default=1)
    description = fields.TextField(null=True)
    triggers = fields.JSONField(null=True)
    input_schema = fields.JSONField(null=True)
    output_schema = fields.JSONField(null=True)
    prompt_template = fields.TextField(null=True)
    mcp_tools = fields.JSONField(null=True)
    required_envs = fields.JSONField(null=True)
    config = fields.JSONField(null=True)
    source = fields.CharField(max_length=32, default="db")
    status = fields.CharField(max_length=32, default="enabled")

    # === 新增字段（沿用既有命名风格） ===
    owner_user_id = fields.CharField(max_length=128, default="anonymous", index=True)
    visibility = fields.CharField(max_length=16, default="private", index=True)
    file_count = fields.IntField(default=0, description="MinIO 中文件总数")
    file_fingerprint = fields.CharField(
        max_length=64, default="",
        description="所有文件 etag 排序后 sha1，触发 fingerprint-based reload",
    )

    is_deleted = fields.BooleanField(default=False)
    deleted_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "skills"
        indexes = [
            ("status", "is_deleted"),
            ("owner_user_id", "visibility", "is_deleted"),  # 新增
            ("updated_at",),
        ]
        ordering = ["-updated_at"]
```

**变更性质**: 仅 `CREATE` 新列 + `CREATE INDEX`，不重命名、不删列、不改类型。可以安全 `ALTER TABLE` 在生产机滚动发布。

### 2.2 既有 `McpConfig`（同模式扩展）

```python
# src/hermetic_agent/store/models/mcp_config.py
from tortoise import fields
from tortoise.models import Model


class McpConfig(Model):
    id = fields.UUIDField(pk=True, binary=False)
    code = fields.CharField(max_length=128, unique=True)
    name = fields.CharField(max_length=255, default="")
    mcp_type = fields.CharField(max_length=32, default="http")
    url = fields.CharField(max_length=2048, null=True)
    command = fields.CharField(max_length=512, null=True)
    args = fields.JSONField(null=True)
    env = fields.JSONField(null=True)
    cwd = fields.CharField(max_length=1024, null=True)
    headers = fields.JSONField(null=True)
    allowed_tools = fields.JSONField(null=True)
    disabled = fields.BooleanField(default=False)
    config = fields.JSONField(null=True)
    source = fields.CharField(max_length=32, default="db")
    status = fields.CharField(max_length=32, default="enabled")

    # === 新增 ===
    owner_user_id = fields.CharField(max_length=128, default="anonymous", index=True)
    visibility = fields.CharField(max_length=16, default="private", index=True)

    is_deleted = fields.BooleanField(default=False)
    deleted_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "mcp_configs"
        indexes = [
            ("status", "is_deleted"),
            ("owner_user_id", "visibility", "is_deleted"),  # 新增
        ]
        ordering = ["code"]
```

### 2.3 新增 `Prompt`

```python
# src/hermetic_agent/store/models/prompt.py
from tortoise import fields
from tortoise.models import Model


class Prompt(Model):
    id = fields.UUIDField(pk=True, binary=False)
    code = fields.CharField(max_length=128, unique=True)
    name = fields.CharField(max_length=255)
    version = fields.IntField(default=1)
    description = fields.TextField(null=True)
    content = fields.TextField()                                  # ← prompt 模板正文
    owner_user_id = fields.CharField(max_length=128, default="anonymous", index=True)
    visibility = fields.CharField(max_length=16, default="private", index=True)
    status = fields.CharField(max_length=32, default="enabled")
    is_deleted = fields.BooleanField(default=False)
    deleted_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "prompts"
        indexes = [
            ("status", "is_deleted"),
            ("owner_user_id", "visibility", "is_deleted"),
            ("updated_at",),
        ]
        ordering = ["-updated_at"]
```

### 2.4 新增 `Command`

```python
# src/hermetic_agent/store/models/command.py
from tortoise import fields
from tortoise.models import Model


class Command(Model):
    id = fields.UUIDField(pk=True, binary=False)
    code = fields.CharField(max_length=128, description="业务短码")
    name = fields.CharField(max_length=255)
    version = fields.IntField(default=1)
    description = fields.TextField(null=True)
    slash_command = fields.CharField(
        max_length=64,
        description="用户输入的命令，如 /summarize；带 / 前缀",
    )
    system_prompt_addendum = fields.TextField(
        description="拼到 chat system_prompt 后面的说明文字，LLM 据此识别该 slash 的作用",
    )
    enabled = fields.BooleanField(default=True)
    owner_user_id = fields.CharField(max_length=128, default="anonymous", index=True)
    visibility = fields.CharField(max_length=16, default="private", index=True)
    status = fields.CharField(max_length=32, default="enabled")
    is_deleted = fields.BooleanField(default=False)
    deleted_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "commands"
        unique_together = [("code", "slash_command")]            # 同一 code 下 slash 唯一
        indexes = [
            ("status", "is_deleted"),
            ("owner_user_id", "visibility", "is_deleted"),
            ("slash_command",),                                   # 按 slash 检索
            ("updated_at",),
        ]
        ordering = ["-updated_at"]
```

### 2.5 新增 `Agent`（复合体）

```python
# src/hermetic_agent/store/models/agent.py
from tortoise import fields
from tortoise.models import Model


class Agent(Model):
    id = fields.UUIDField(pk=True, binary=False)
    code = fields.CharField(max_length=128, unique=True)
    name = fields.CharField(max_length=255)
    version = fields.IntField(default=1)
    description = fields.TextField(null=True)

    # === Agent 自身配置 ===
    system_prompt = fields.TextField(default="")
    model = fields.CharField(max_length=128, default="openai/gpt-4o-mini")
    tool_level = fields.CharField(max_length=16, default="standard")  # safe/standard/full
    network = fields.CharField(max_length=16, default="local")         # off/local/any

    # === 引用（不强制 FK，软删除不级联）===
    skill_codes = fields.JSONField(
        default=list,
        description="引用的 Skill.code 列表，例如 ['flight-query', 'booking-helper']",
    )
    mcp_server_codes = fields.JSONField(
        default=list,
        description="引用的 McpConfig.code 列表，例如 ['default_mcp', 'company-crm']",
    )
    prompt_codes = fields.JSONField(
        default=list,
        description="引用的 Prompt.code 列表，顺序即拼到 system_prompt 后的顺序",
    )
    command_codes = fields.JSONField(
        default=list,
        description="引用的 Command.code 列表，顺序即渲染 system_prompt_addendum 的顺序",
    )

    # === 通用字段 ===
    owner_user_id = fields.CharField(max_length=128, default="anonymous", index=True)
    visibility = fields.CharField(max_length=16, default="private", index=True)
    status = fields.CharField(max_length=32, default="enabled")
    is_deleted = fields.BooleanField(default=False)
    deleted_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "agents"
        indexes = [
            ("status", "is_deleted"),
            ("owner_user_id", "visibility", "is_deleted"),
            ("model",),
            ("updated_at",),
        ]
        ordering = ["-updated_at"]
```

**JSONField 里列表的长度建议** ≤ 64，引用总数建议 ≤ 256。如有强一致需要，再升级为外键表 `agent_asset_refs(asset_id, code, kind)`。

---

## 3. 既有表的迁移 DDL（等价 SQL 视角）

> Tortoise `generate_schemas=True` 会自动建新表 + 索引。已有表需要手动迁移。

```sql
-- 1) skills 表加列 + 加索引
ALTER TABLE skills
    ADD COLUMN owner_user_id VARCHAR(128) NOT NULL DEFAULT 'anonymous',
    ADD COLUMN visibility    VARCHAR(16)  NOT NULL DEFAULT 'private',
    ADD COLUMN file_count    INT          NOT NULL DEFAULT 0,
    ADD COLUMN file_fingerprint VARCHAR(64) NOT NULL DEFAULT '';

ALTER TABLE skills
    ADD INDEX ix_skills_owner_vis_del (owner_user_id, visibility, is_deleted),
    ADD INDEX ix_skills_updated_at (updated_at);

-- 2) mcp_configs 表加列 + 加索引
ALTER TABLE mcp_configs
    ADD COLUMN owner_user_id VARCHAR(128) NOT NULL DEFAULT 'anonymous',
    ADD COLUMN visibility    VARCHAR(16)  NOT NULL DEFAULT 'private';

ALTER TABLE mcp_configs
    ADD INDEX ix_mcp_owner_vis_del (owner_user_id, visibility, is_deleted);

-- 3) 新建 3 张表（Tortoise 自动建）
-- 略，等价于上面 2.3 / 2.4 / 2.5 的字段。
```

**回退**: 所有变更都是 additive 的（仅 `ADD COLUMN` / `ADD INDEX` / `CREATE TABLE`），回退只需要 `DROP COLUMN` / `DROP INDEX` / `DROP TABLE`，无数据迁移风险。

---

## 4. Repository ABC 接口（每张表）

### 4.1 `SkillRepository`（既有，**扩展 2 个方法**）

```python
# src/hermetic_agent/store/repositories/skill_repo.py  (append-only)
class SkillRepository(Repository[Skill]):

    # ... 既有抽象方法保留: get_by_id / get_by_code / list / list_active / ...

    async def list_visible_to(
        self, *, actor_user_id: str, limit: int = 50, offset: int = 0,
        code: str | None = None, status: str | None = None,
    ) -> list[Skill]: ...

    async def list_public(
        self, *, limit: int = 50, offset: int = 0,
        code: str | None = None,
    ) -> list[Skill]: ...

    async def update_file_fingerprint(
        self, skill_id: str, *, file_count: int, file_fingerprint: str,
    ) -> Skill | None: ...

    async def set_visibility(
        self, skill_id: str, *, visibility: str, actor_user_id: str,
    ) -> Skill | None: ...
```

**变更性质**: 既有方法不删、不重命名；新加 4 个抽象方法。**`class abstractmethod` 集合扩展**——这会让所有现有 concrete 实现（`MemorySkillRepository` / `MySQLSkillRepository`）缺方法而抛 `TypeError`，所以需要同步在两个 concrete impl 中实现。属于 additive change 但需要同步配套修改。

### 4.2 `McpConfigRepository`（同样扩展 4 个方法）

```python
class McpConfigRepository(Repository[McpConfig]):

    # ... 既有 ...

    async def list_visible_to(self, *, actor_user_id, limit, offset, code=None, status=None) -> list[McpConfig]: ...
    async def list_public(self, *, limit, offset, code=None) -> list[McpConfig]: ...
    async def set_visibility(self, config_id, *, visibility, actor_user_id) -> McpConfig | None: ...
```

### 4.3 新 `PromptRepository` ABC

```python
# src/hermetic_agent/store/repositories/prompt_repo.py  (全新)
class PromptRepository(Repository[Prompt]):

    async def get_by_id(self, prompt_id: str) -> Prompt | None: ...
    async def get_by_code(self, code: str) -> Prompt | None: ...
    async def list(
        self, *, limit: int = 50, offset: int = 0, include_deleted: bool = False,
        **filters: Any,
    ) -> list[Prompt]: ...
    async def count(self, *, include_deleted: bool = False, **filters: Any) -> int: ...
    async def create(self, prompt: Prompt) -> Prompt: ...
    async def update(self, prompt_id: str, **fields: Any) -> Prompt | None: ...
    async def soft_delete(self, prompt_id: str) -> bool: ...
    async def hard_delete(self, prompt_id: str) -> bool: ...
    async def list_visible_to(
        self, *, actor_user_id: str, limit: int = 50, offset: int = 0,
        code: str | None = None, status: str | None = None,
    ) -> list[Prompt]: ...
    async def list_public(
        self, *, limit: int = 50, offset: int = 0, code: str | None = None,
    ) -> list[Prompt]: ...
    async def set_visibility(
        self, prompt_id: str, *, visibility: str, actor_user_id: str,
    ) -> Prompt | None: ...
```

### 4.4 新 `CommandRepository` ABC

同 4.3 形态，模型替换为 `Command`。

### 4.5 新 `AgentRepository` ABC

```python
class AgentRepository(Repository[Agent]):

    # 上面那 8 个通用方法 ...
    async def list_visible_to(
        self, *, actor_user_id, limit, offset, code=None, status=None,
    ) -> list[Agent]: ...
    async def list_public(
        self, *, limit, offset, code=None,
    ) -> list[Agent]: ...
    async def set_visibility(
        self, agent_id, *, visibility, actor_user_id,
    ) -> Agent | None: ...
    # 没有 find_by_model: 不常用，避免过深 API。
```

---

## 5. Memory Repository 形态（以 `MemoryPromptRepository` 为例）

```python
# src/hermetic_agent/store/repositories/memory/prompt_repo_memory.py
from __future__ import annotations
from typing import Any

from hermetic_agent.store.models.prompt import Prompt
from hermetic_agent.store.repositories.memory._base import MemoryRepository
from hermetic_agent.store.repositories.prompt_repo import PromptRepository


class MemoryPromptRepository(MemoryRepository[Prompt], PromptRepository):
    """内存版 Prompt 仓储 —— 测试 + dev 用。"""

    def __init__(self) -> None:
        super().__init__()

    # --- 既有基类方法 ---
    async def get_by_id(self, entity_id: str) -> Prompt | None:
        p = self._store.get(entity_id)
        if p is None or p.is_deleted:
            return None
        return p

    async def get_by_code(self, code: str) -> Prompt | None:
        for p in self._store.values():
            if p.code == code and not p.is_deleted:
                return p
        return None

    async def list(
        self, *, limit=50, offset=0, include_deleted=False, **filters: Any,
    ) -> list[Prompt]:
        items = list(self._store.values())
        if not include_deleted:
            items = [p for p in items if not p.is_deleted]
        for k in ("code", "status"):
            if filters.get(k) is not None:
                items = [p for p in items if getattr(p, k) == filters[k]]
        items.sort(key=lambda p: (p.updated_at, p.id), reverse=True)
        return items[offset : offset + limit]

    async def count(self, *, include_deleted=False, **filters: Any) -> int:
        items = list(self._store.values())
        if not include_deleted:
            items = [p for p in items if not p.is_deleted]
        for k in ("code", "status"):
            if filters.get(k) is not None:
                items = [p for p in items if getattr(p, k) == filters[k]]
        return len(items)

    async def create(self, model: Prompt) -> Prompt:
        # Tortoise 默认在内存模型上不需要 save 落盘；MemoryRepository 基类在 put() 里挂
        self._store[model.id] = model
        return model

    async def update(self, entity_id: str, **fields: Any) -> Prompt | None:
        p = self._store.get(entity_id)
        if p is None or p.is_deleted:
            return None
        for k, v in fields.items():
            setattr(p, k, v)
        p.updated_at = _utcnow()
        return p

    async def soft_delete(self, entity_id: str) -> bool:
        from hermetic_agent.store.models._common import utcnow
        p = self._store.get(entity_id)
        if p is None or p.is_deleted:
            return False
        p.is_deleted = True
        p.deleted_at = utcnow()
        return True

    async def hard_delete(self, entity_id: str) -> bool:
        return self._store.pop(entity_id, None) is not None

    # --- 新增方法 ---
    async def list_visible_to(
        self, *, actor_user_id: str, limit=50, offset=0,
        code=None, status=None,
    ) -> list[Prompt]:
        items = list(self._store.values())
        items = [
            p for p in items
            if not p.is_deleted and (
                p.owner_user_id == actor_user_id or p.visibility == "public"
            )
        ]
        if code is not None:
            items = [p for p in items if p.code == code]
        if status is not None:
            items = [p for p in items if p.status == status]
        items.sort(key=lambda p: (p.updated_at, p.id), reverse=True)
        return items[offset : offset + limit]

    async def list_public(
        self, *, limit=50, offset=0, code=None,
    ) -> list[Prompt]:
        items = [
            p for p in self._store.values()
            if not p.is_deleted and p.visibility == "public"
        ]
        if code is not None:
            items = [p for p in items if p.code == code]
        items.sort(key=lambda p: (p.updated_at, p.id), reverse=True)
        return items[offset : offset + limit]

    async def set_visibility(
        self, prompt_id: str, *, visibility: str, actor_user_id: str,
    ) -> Prompt | None:
        if visibility not in ("private", "public"):
            raise ValueError(f"invalid visibility: {visibility!r}")
        p = self._store.get(prompt_id)
        if p is None or p.is_deleted:
            return None
        if p.owner_user_id != actor_user_id:
            return None   # 非 owner 一律返 None（不抛 → 让 service 翻译成 FORBIDDEN）
        p.visibility = visibility
        p.updated_at = _utcnow()
        return p


def _utcnow():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


__all__ = ["MemoryPromptRepository"]
```

`MemoryCommandRepository` / `MemoryAgentRepository` 形态相同，字段对应替换。`MySQL<...>Repository` 通过 Tortoise 实现，列名 == 属性名。

---

## 6. Service 层签名（每表 5 个 CRUD 方法 + 2 个 visibility 方法）

```python
# 以 PromptService 为例
class PromptService:

    def __init__(self, repo: PromptRepository, audit: AuditLogService) -> None:
        self._repo = repo
        self._audit = audit

    async def get_by_code(self, code: str) -> Prompt: ...
    async def get_by_id(self, prompt_id: str) -> Prompt: ...

    async def list(
        self, *, actor: ActorContext, limit=50, offset=0, include_public=True,
        code=None, status=None,
    ) -> list[Prompt]:
        """返回 actor 私有 ∪ public."""
        ...

    async def list_public(self, *, limit=50, offset=0, code=None) -> list[Prompt]: ...

    async def create(
        self, req: CreatePromptRequest, *, actor: ActorContext,
    ) -> Prompt:
        ...
        # 调 repo.create; audit.record(action="create", actor=actor, ...)

    async def update(
        self, prompt_id: str, req: UpdatePromptRequest, *, actor: ActorContext,
    ) -> Prompt:
        # 非 owner → 抛 PolicyError('FORBIDDEN')
        ...

    async def set_visibility(
        self, prompt_id: str, visibility: str, *, actor: ActorContext,
    ) -> Prompt: ...

    async def soft_delete(
        self, prompt_id: str, *, actor: ActorContext,
    ) -> None: ...
```

`CommandService` / `AgentService` / `SkillService` / `McpConfigService` 形态相同；附加规则:
- `AgentService.resolve_for_chat(actor, agent_code) -> ResolvedAgent` —— 走引用解析，过滤缺失的 code，记录 warnings。
- `SkillService.list_active_for_chat(actor, codes) -> list[Skill]` —— 过滤 owner / public 可见性 + status=enabled + is_deleted=false。

---

## 7. DTO（Pydantic 请求/响应）

```python
# src/hermetic_agent/store/dto/prompt.py
from __future__ import annotations
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class CreatePromptRequest(BaseModel):
    code: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_\-]+$")
    name: str = Field(min_length=1, max_length=255)
    version: int = Field(default=1, ge=1)
    description: str | None = Field(default=None, max_length=2048)
    content: str = Field(min_length=1)


class UpdatePromptRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2048)
    content: str | None = Field(default=None, min_length=1)
    status: str | None = Field(default=None, pattern=r"^(enabled|disabled|draft)$")


class PromptResponse(BaseModel):
    id: str
    code: str
    name: str
    version: int
    description: str | None
    content: str
    owner_user_id: str
    visibility: str
    status: str
    file_count: int = 0                  # 仅 SkillResponse 用；其余默认 0
    file_fingerprint: str = ""           # 同上
    created_at: datetime
    updated_at: datetime


class PromptListResponse(BaseModel):
    total: int
    items: list[PromptResponse]
```

`Command` DTO 多一个 `slash_command: str = Field(pattern=r"^/[A-Za-z0-9_\-]+$")`。
`Agent` DTO 多 4 个 `list[str]` 字段，每个元素长度限制 ≤ 32、字符集 `[A-Za-z0-9_\-.]+`。

---

## 8. ServiceContainer / 装配

修改 `src/hermetic_agent/store/services/container.py`:

```python
@dataclass
class ServiceContainer:
    audit_log: AuditLogService
    scenario: ScenarioService
    session: SessionService
    chat_turn: ChatTurnService
    message: MessageService
    part: PartService
    skill: SkillService
    mcp_config: McpConfigService
    # === 新增 ===
    prompt: PromptService
    command: CommandService
    agent: AgentService
```

`build_container_from_settings` 在 `memory` 和 `mysql` 两条分支都对应构造 3 个新 repo、3 个新 service。

---

## 9. 索引 / 查询性能

| 查询 | 触发的索引 |
|---|---|
| `list_visible_to(actor)` 带 `code / status` | `(owner_user_id, visibility, is_deleted)` 可前缀匹配；`code` / `status` 由后续 filter |
| `list_public()` | `(owner_user_id, visibility, is_deleted)` 上 `(visibility='public')` 过滤 |
| 按 `code` 单查 | `code` 是 `unique`，直接 B+ 树 |
| `slash_command` 检索 | `commands.slash_command` 索引（建议加，否则全表扫） |
| 按 `model` 筛 agent | `agents.model` 索引 |

性能目标：单表 1 万行时 `list_visible_to(limit=50)` 在 MySQL 上 ≤ 50 ms，在内存后端 < 5 ms。

---

## 10. 软删除 + 审计 + 权限交叉模型

```
actor = "user-X"    visibility = private/public
owner_user_id      == actor  →  可读 + 可写 + 可发布 + 可删
owner_user_id      != actor  AND  visibility = private  →  不可见；读端返 NOT_FOUND 不是 FORBIDDEN（防探测）
owner_user_id      != actor  AND  visibility = public   →  可读；不可写 / 不可发布 / 不可删
匿名访问                                         →  仅可见 visibility=public
```

审计: 所有 `create / update / set_visibility / soft_delete` 都通过 `AuditLogService.record(...)` 写一条 `audit_logs` 行。

---

## 11. 不变量 & 校验

| 不变量 | 实现位置 |
|---|---|
| `code` 全表唯一 | `Field(unique=True)` |
| `commands.slash_command` 在同一 `code` 下唯一 | `unique_together = [("code", "slash_command")]` |
| `visibility ∈ {"private", "public"}` | DTO `pattern` + service `assert` |
| `status ∈ {"enabled", "disabled", "draft"}` | DTO `pattern` |
| 软删除幂等 | `repo.soft_delete` 找不到返 `False` |
| agent 引用列表里任意 code 缺失 → 警告而非抛错 | `AgentResolver.resolve` |

---

## 12. 未来扩展位（保留字段，不在本轮）

| 字段 / 表 | 暂空 | 用途（未来） |
|---|---|---|
| `Skill.tenant_id` | 未加 | 多租户时按租户隔离 |
| `Agent.tags JSONField` | 未加 | 检索 / 分类 |
| `Prompt.variables JSONField` | 未加 | 模板变量声明 |
| `Command.allowed_models JSONField` | 未加 | 限定 model |
| 全表审计视图 | 未加 | 合规导出 |
