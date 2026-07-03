# 资产注册中心实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 hermetic-agent 升级为 LLM 资产控制面：MCP / skills / agents / prompts / commands 五类资产 DB 化注册、skill 文件 MinIO 存储、opencode 沙箱热注入（在不 `docker compose build` / `restart` 的前提下）。

**Architecture:** 严格按 spec 走；Phase 1 数据面（5 表 + Service + Controller）、Phase 2 MinIO 文件面（`store/object/` + skill_files controller）、Phase 3 chat 集成（`AssetRenderer` + `AgentResolver` + `SkillOverlayManager`），Phase 4 前端 stub + Docker compose。每张表 = `_Model` + `Repository` ABC + 双实现（memory + mysql）+ `Service` + DTO。MinIO 客户端封装在 `store/object/`。chat 时通过 `chat_inject/injector_adapter` 钩入既有 `chat_controller`，按需触发既有 `/admin/policy` + `/admin/reload` 实现 skill 热注入。

**Tech Stack:** Python 3.10+、Sanic 24+、Tortoise ORM（asyncmy）、Pydantic v2、structlog、minio-py 7+、pydantic-settings。Frontend: React 18 + TS 5 + Vite 5。

---

## 全局约束

> 所有任务必须遵守：

- **5 层架构（L1→L5 严格向下）**：L1 = `api/` controllers、L2 = `scenarios/`（本项目不新增 L2 文件）、L3 = `skill_runtime/` + `auip/` + `core/suspendable_scheduler.py` + `core/turn_store.py`、L4 = `providers/launcher.py`、L5 = `policy/` + `store/` + `audit/`。`chat_inject/` 落在 L3（资产渲染 + 解析）/L4（与 sandbox 的对接通过既有 admin API）边界。
- **文件大小硬上限**：L1/L4/L5 ≤ 200 行；L2/L3 ≤ 250 行；函数 ≤ 40 行；圈复杂度 ≤ 10。
- **零修改既有签名**：`core/scheduler.py`、`providers/*`、`skills/registry.py`、`mcp/registry.py` 等已有类的签名一律不改。允许**加字段、加新方法、新增文件**。
- **仅 2 个 chat 端点**：不允许新增 per-scenario chat 端点。`scripts/check_unified_chat_entry.py` CI 拦。
- **错误码 12 + 1**：用户可见错误必须用 `code` + `detail`。本项目 `OBJECT_STORE_UNAVAILABLE` 是新增的 1 个码。
- **pydantic-settings**：`AGENT_SCHEDULER_` 前缀，CWD 下 `.env` 自动加载。**模块顶层不写硬编码常量**，统一 `from hermetic_agent.config.settings import get_settings`。
- **同步 pyproject.toml 与 requirements.txt**（Dockerfile 用 requirements.txt；改了 deps 两边同步）。
- **pytest-asyncio auto mode** —— 无需 `@pytest.mark.asyncio`。
- **不修改 `tests/conftest.py`** —— 新 fixture 放 `tests/test_<feature>_conftest.py`。
- **测试命名**：`test_<module>_{init,happy_path,error}_*` 三类。
- **每模块 commit 前跑**：`ruff check src/hermetic_agent/<your_module>/` + `mypy src/hermetic_agent/<your_module>/` + `pytest tests/test_<your_module>_*.py -v`。
- **CI 全跑**：`python scripts/ci_check.py` + `python scripts/check_unified_chat_entry.py` 全过。
- **commit 由用户授权**，本计划每任务标 commit 步骤、不替用户提交。

---

## 文件结构总览

### L5（store / object / settings）
- 修改：`src/hermetic_agent/store/models/skill.py`（增 4 字段）
- 修改：`src/hermetic_agent/store/models/mcp_config.py`（增 2 字段）
- 新建：`src/hermetic_agent/store/models/{prompt,command,agent}.py`
- 修改：`src/hermetic_agent/store/models/__init__.py`
- 修改 + 新建：5 张表对应的 `repositories/{model}_repo.py` ABC + memory/mysql 实现
- 修改：`src/hermetic_agent/store/repositories/__init__.py`
- 新建：`src/hermetic_agent/store/dto/{prompt,command,agent}.py` + 修改 `dto/__init__.py`
- 修改：`src/hermetic_agent/store/services/{skill,mcp_config}_service.py`（加 visibility 方法）
- 新建：`src/hermetic_agent/store/services/{prompt,command,agent}_service.py`
- 修改：`src/hermetic_agent/store/services/container.py`（3 个新 service）+ `services/__init__.py`
- 新建：`src/hermetic_agent/store/object/{__init__,minio_client,skill_files,memory_skill_files,minio_skill_files,factory}.py`
- 修改：`src/hermetic_agent/config/settings.py`（加 §16/§17/§18）

### L1（api）
- 新建：`src/hermetic_agent/api/http/middleware/actor_context.py`
- 新建：`src/hermetic_agent/api/http/controllers/{prompts,commands,agents,skill_files}_controller.py`
- 修改：`src/hermetic_agent/api/app/blueprint_registry.py`
- 修改：`src/hermetic_agent/api/app/app.py`（注册 actor middleware）
- 修改：`src/hermetic_agent/api/lifecycle/lifecycle.py`（startup 构造 `asset_clients`）

### L3（chat_inject）
- 新建：`src/hermetic_agent/chat_inject/{__init__,asset_renderer,agent_resolver,injector_adapter,overlay_builder,skill_overlay_manager,reload_queue}.py`

### 容器 / 依赖
- 修改：`docker-compose.yml`（+ minio service + named volume）
- 新建：`docker/minio-init/Dockerfile`、`docker/minio-init/entrypoint.sh`
- 修改：`.env.example`、`pyproject.toml` + `requirements.txt`

### Tests（19 个测试文件）
每个模块含 `init / happy_path / error_*` 三类用例；fixture 不改 `tests/conftest.py`，各自 `tests/test_<feature>_conftest.py`。

### 前端（仅 stub，本轮不出 UI）
- 新建：`frontend/src/services/{agents,prompts,commands,skill_files}.ts`
- 新建：`frontend/src/types/assets.ts`
- 新建：`frontend/src/routes/admin/assets.tsx`
- 修改：`frontend/src/App.tsx`（nav 链接）
- 修改：`docs/api.md`（+ §6.4 curl 例子）

---

> **本计划分 3 个文件**：
> - 本文件（主计划）：**Phase 1 数据面**（Task 1–9）
> - `2026-06-30-asset-registry-plan-2.md`：**Phase 2 MinIO 文件面 + Phase 3 chat 集成**（Task 10–16）
> - `2026-06-30-asset-registry-plan-3.md`：**Phase 4 前端 stub + Docker compose + CI 收口**（Task 17–19）

---

## Task 1: 扩展 Skill 模型 + Repository（L5）

**Files:**
- 修改：`src/hermetic_agent/store/models/skill.py`
- 修改：`src/hermetic_agent/store/repositories/skill_repo.py`
- 修改：`src/hermetic_agent/store/repositories/memory/skill_repo_memory.py`
- 修改：`src/hermetic_agent/store/repositories/mysql/skill_repo_mysql.py`
- 新建：`tests/test_skill_repo_owner_visibility.py`

**Interfaces:**
- Consumes: 无（首任务）
- Produces:
  - `Skill.owner_user_id: str`、`Skill.visibility: str`、`Skill.file_count: int`、`Skill.file_fingerprint: str`
  - `SkillRepository.list_visible_to(*, actor_user_id, limit, offset, code, status) -> list[Skill]`
  - `SkillRepository.list_public(*, limit, offset, code) -> list[Skill]`
  - `SkillRepository.update_file_fingerprint(skill_id, *, file_count, file_fingerprint) -> Skill | None`
  - `SkillRepository.set_visibility(skill_id, *, visibility, actor_user_id) -> Skill | None`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_skill_repo_owner_visibility.py
import uuid
import pytest

from hermetic_agent.store.models.skill import Skill
from hermetic_agent.store.repositories.memory.skill_repo_memory import MemorySkillRepository


@pytest.mark.asyncio
async def test_list_visible_to_returns_owner_private_and_public():
    repo = MemorySkillRepository()
    own = Skill(id=uuid.uuid4(), code="my-skill", name="My", status="enabled",
                owner_user_id="alice", visibility="private")
    other_priv = Skill(id=uuid.uuid4(), code="hidden", name="H", status="enabled",
                       owner_user_id="bob", visibility="private")
    other_pub = Skill(id=uuid.uuid4(), code="public", name="P", status="enabled",
                      owner_user_id="bob", visibility="public")
    repo._store[own.id] = own
    repo._store[other_priv.id] = other_priv
    repo._store[other_pub.id] = other_pub

    items = await repo.list_visible_to(actor_user_id="alice", limit=50, offset=0)
    codes = {s.code for s in items}
    assert codes == {"my-skill", "public"}


@pytest.mark.asyncio
async def test_list_public_only_returns_public():
    repo = MemorySkillRepository()
    pub = Skill(id=uuid.uuid4(), code="pub", name="P", status="enabled",
               owner_user_id="alice", visibility="public")
    priv = Skill(id=uuid.uuid4(), code="priv", name="P", status="enabled",
                owner_user_id="alice", visibility="private")
    repo._store[pub.id] = pub
    repo._store[priv.id] = priv

    items = await repo.list_public(limit=50, offset=0)
    assert [s.code for s in items] == ["pub"]


@pytest.mark.asyncio
async def test_set_visibility_owner_only():
    repo = MemorySkillRepository()
    s = Skill(id=uuid.uuid4(), code="x", name="X", status="enabled",
              owner_user_id="alice", visibility="private")
    repo._store[s.id] = s

    result = await repo.set_visibility(str(s.id), visibility="public", actor_user_id="alice")
    assert result is not None and result.visibility == "public"

    s.visibility = "private"  # 重置
    result = await repo.set_visibility(str(s.id), visibility="public", actor_user_id="bob")
    assert result is None
    assert (await repo.get_by_id(str(s.id))).visibility == "private"
```

- [ ] **Step 2: 跑测试验证失败**

Run: `pytest tests/test_skill_repo_owner_visibility.py -v`
Expected: FAIL with `AttributeError: 'MemorySkillRepository' object has no attribute 'list_visible_to'`

- [ ] **Step 3: 扩展 `Skill` 模型**

修改 `src/hermetic_agent/store/models/skill.py`，**只追加 4 个字段和 1 个索引**（不改既有字段名/类型/默认值）：

```python
# 在 status 字段后插入（保持既有字段不变）:
owner_user_id = fields.CharField(max_length=128, default="anonymous", index=True)
visibility = fields.CharField(max_length=16, default="private", index=True)
file_count = fields.IntField(default=0, description="MinIO 中文件总数")
file_fingerprint = fields.CharField(max_length=64, default="",
                                     description="所有 etag 排序 sha1")

# class Meta 的 indexes 列表追加:
indexes = [
    ("status", "is_deleted"),
    ("owner_user_id", "visibility", "is_deleted"),
    ("updated_at",),
]
ordering = ["-updated_at"]
```

- [ ] **Step 4: 扩展 `SkillRepository` ABC**

```python
# src/hermetic_agent/store/repositories/skill_repo.py
# 在末尾追加以下 4 个抽象方法（不要改既有）:
@abstractmethod
async def list_visible_to(self, *, actor_user_id: str, limit: int = 50,
                         offset: int = 0, code: str | None = None,
                         status: str | None = None) -> list[Skill]: ...

@abstractmethod
async def list_public(self, *, limit: int = 50, offset: int = 0,
                      code: str | None = None) -> list[Skill]: ...

@abstractmethod
async def update_file_fingerprint(self, skill_id: str, *,
                                  file_count: int,
                                  file_fingerprint: str) -> Skill | None: ...

@abstractmethod
async def set_visibility(self, skill_id: str, *,
                         visibility: str,
                         actor_user_id: str) -> Skill | None: ...
```

- [ ] **Step 5: 实现 `MemorySkillRepository` 新方法**

```python
# src/hermetic_agent/store/repositories/memory/skill_repo_memory.py 末尾追加（既有保留）:
async def list_visible_to(self, *, actor_user_id, limit=50, offset=0,
                         code=None, status=None):
    items = [s for s in self._store.values()
             if not s.is_deleted and (
                 s.owner_user_id == actor_user_id or s.visibility == "public"
             )]
    if code is not None:
        items = [s for s in items if s.code == code]
    if status is not None:
        items = [s for s in items if s.status == status]
    items.sort(key=lambda s: (s.updated_at, s.id), reverse=True)
    return items[offset:offset + limit]

async def list_public(self, *, limit=50, offset=0, code=None):
    items = [s for s in self._store.values()
             if not s.is_deleted and s.visibility == "public"]
    if code is not None:
        items = [s for s in items if s.code == code]
    items.sort(key=lambda s: (s.updated_at, s.id), reverse=True)
    return items[offset:offset + limit]

async def update_file_fingerprint(self, skill_id, *, file_count, file_fingerprint):
    s = self._store.get(skill_id)
    if s is None or s.is_deleted:
        return None
    s.file_count = file_count
    s.file_fingerprint = file_fingerprint
    return s

async def set_visibility(self, skill_id, *, visibility, actor_user_id):
    if visibility not in ("private", "public"):
        raise ValueError("invalid visibility")
    s = self._store.get(skill_id)
    if s is None or s.is_deleted:
        return None
    if s.owner_user_id != actor_user_id:
        return None
    s.visibility = visibility
    return s
```

- [ ] **Step 6: 实现 `MySQLSkillRepository` 新方法**

```python
# src/hermetic_agent/store/repositories/mysql/skill_repo_mysql.py 末尾追加:
from tortoise.expressions import Q

async def list_visible_to(self, *, actor_user_id, limit=50, offset=0,
                         code=None, status=None):
    qs = Skill.filter(is_deleted=False).filter(
        Q(owner_user_id=actor_user_id) | Q(visibility="public")
    )
    if code is not None:
        qs = qs.filter(code=code)
    if status is not None:
        qs = qs.filter(status=status)
    return await qs.order_by("-updated_at", "-id").offset(offset).limit(limit)

async def list_public(self, *, limit=50, offset=0, code=None):
    qs = Skill.filter(is_deleted=False, visibility="public")
    if code is not None:
        qs = qs.filter(code=code)
    return await qs.order_by("-updated_at", "-id").offset(offset).limit(limit)

async def update_file_fingerprint(self, skill_id, *, file_count, file_fingerprint):
    rc = await Skill.filter(id=skill_id, is_deleted=False).update(
        file_count=file_count, file_fingerprint=file_fingerprint,
    )
    if rc == 0:
        return None
    return await self.get_by_id(skill_id)

async def set_visibility(self, skill_id, *, visibility, actor_user_id):
    if visibility not in ("private", "public"):
        raise ValueError("invalid visibility")
    rc = await Skill.filter(
        id=skill_id, is_deleted=False, owner_user_id=actor_user_id
    ).update(visibility=visibility)
    if rc == 0:
        return None
    return await self.get_by_id(skill_id)
```

- [ ] **Step 7: 跑测试验证通过**

Run: `pytest tests/test_skill_repo_owner_visibility.py -v`
Expected: 3 passed

- [ ] **Step 8: 提交**

```bash
git add src/hermetic_agent/store/models/skill.py \
        src/hermetic_agent/store/repositories/skill_repo.py \
        src/hermetic_agent/store/repositories/memory/skill_repo_memory.py \
        src/hermetic_agent/store/repositories/mysql/skill_repo_mysql.py \
        tests/test_skill_repo_owner_visibility.py
git commit -m "feat(store): extend Skill model + repo with owner/visibility/file_fingerprint"
```

---

## Task 2: 扩展 McpConfig 模型 + Repository（L5）

**Files:**
- 修改：`src/hermetic_agent/store/models/mcp_config.py`
- 修改：`src/hermetic_agent/store/repositories/mcp_config_repo.py`
- 修改：`src/hermetic_agent/store/repositories/memory/mcp_config_repo_memory.py`
- 修改：`src/hermetic_agent/store/repositories/mysql/mcp_config_repo_mysql.py`
- 新建：`tests/test_mcp_config_repo_owner_visibility.py`

**Interfaces:** 与 Task 1 同形态，model 字段名换为 `McpConfig`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_mcp_config_repo_owner_visibility.py
import uuid
import pytest

from hermetic_agent.store.models.mcp_config import McpConfig
from hermetic_agent.store.repositories.memory.mcp_config_repo_memory import MemoryMcpConfigRepository


@pytest.mark.asyncio
async def test_list_visible_to_excludes_other_users_private():
    repo = MemoryMcpConfigRepository()
    own = McpConfig(id=uuid.uuid4(), code="c1", owner_user_id="alice", visibility="private")
    other_priv = McpConfig(id=uuid.uuid4(), code="c2", owner_user_id="bob", visibility="private")
    other_pub = McpConfig(id=uuid.uuid4(), code="c3", owner_user_id="bob", visibility="public")
    repo._store[own.id] = own
    repo._store[other_priv.id] = other_priv
    repo._store[other_pub.id] = other_pub

    items = await repo.list_visible_to(actor_user_id="alice", limit=50, offset=0)
    assert {c.code for c in items} == {"c1", "c3"}


@pytest.mark.asyncio
async def test_set_visibility_blocks_non_owner():
    repo = MemoryMcpConfigRepository()
    c = McpConfig(id=uuid.uuid4(), code="x", owner_user_id="alice", visibility="private")
    repo._store[c.id] = c
    result = await repo.set_visibility(str(c.id), visibility="public", actor_user_id="bob")
    assert result is None
```

- [ ] **Step 2: 跑测试验证失败**

Run: `pytest tests/test_mcp_config_repo_owner_visibility.py -v` — FAIL（`list_visible_to` 不存在）

- [ ] **Step 3: 扩展 `McpConfig` 模型**

```python
# src/hermetic_agent/store/models/mcp_config.py 增字段（不改既有）:
owner_user_id = fields.CharField(max_length=128, default="anonymous", index=True)
visibility = fields.CharField(max_length=16, default="private", index=True)

# class Meta.indexes 追加:
("owner_user_id", "visibility", "is_deleted"),
```

- [ ] **Step 4: 扩展 `McpConfigRepository` ABC**

```python
# src/hermetic_agent/store/repositories/mcp_config_repo.py 末尾追加:
@abstractmethod
async def list_visible_to(self, *, actor_user_id, limit=50, offset=0,
                         code=None, status=None): ...

@abstractmethod
async def list_public(self, *, limit=50, offset=0, code=None): ...

@abstractmethod
async def set_visibility(self, config_id, *, visibility, actor_user_id): ...
```

- [ ] **Step 5: 实现 `MemoryMcpConfigRepository`**

```python
# src/hermetic_agent/store/repositories/memory/mcp_config_repo_memory.py 末尾追加:
async def list_visible_to(self, *, actor_user_id, limit=50, offset=0, code=None, status=None):
    items = [c for c in self._store.values()
             if not c.is_deleted and (
                 c.owner_user_id == actor_user_id or c.visibility == "public"
             )]
    if code is not None:
        items = [c for c in items if c.code == code]
    if status is not None:
        items = [c for c in items if c.status == status]
    return items[offset:offset + limit]

async def list_public(self, *, limit=50, offset=0, code=None):
    items = [c for c in self._store.values()
             if not c.is_deleted and c.visibility == "public"]
    if code is not None:
        items = [c for c in items if c.code == code]
    return items[offset:offset + limit]

async def set_visibility(self, config_id, *, visibility, actor_user_id):
    if visibility not in ("private", "public"):
        raise ValueError("invalid visibility")
    c = self._store.get(config_id)
    if c is None or c.is_deleted:
        return None
    if c.owner_user_id != actor_user_id:
        return None
    c.visibility = visibility
    return c
```

- [ ] **Step 6: 实现 `MySQLMcpConfigRepository`**

```python
# src/hermetic_agent/store/repositories/mysql/mcp_config_repo_mysql.py 末尾追加:
from tortoise.expressions import Q

async def list_visible_to(self, *, actor_user_id, limit=50, offset=0, code=None, status=None):
    qs = McpConfig.filter(is_deleted=False).filter(
        Q(owner_user_id=actor_user_id) | Q(visibility="public")
    )
    if code is not None:
        qs = qs.filter(code=code)
    if status is not None:
        qs = qs.filter(status=status)
    return await qs.order_by("code").offset(offset).limit(limit)

async def list_public(self, *, limit=50, offset=0, code=None):
    qs = McpConfig.filter(is_deleted=False, visibility="public")
    if code is not None:
        qs = qs.filter(code=code)
    return await qs.order_by("code").offset(offset).limit(limit)

async def set_visibility(self, config_id, *, visibility, actor_user_id):
    if visibility not in ("private", "public"):
        raise ValueError("invalid visibility")
    rc = await McpConfig.filter(
        id=config_id, is_deleted=False, owner_user_id=actor_user_id
    ).update(visibility=visibility)
    return (await self.get_by_id(config_id)) if rc else None
```

- [ ] **Step 7: 跑测试验证**

Run: `pytest tests/test_mcp_config_repo_owner_visibility.py -v` — 2 passed

- [ ] **Step 8: 提交**

```bash
git add src/hermetic_agent/store/models/mcp_config.py \
        src/hermetic_agent/store/repositories/mcp_config_repo.py \
        src/hermetic_agent/store/repositories/memory/mcp_config_repo_memory.py \
        src/hermetic_agent/store/repositories/mysql/mcp_config_repo_mysql.py \
        tests/test_mcp_config_repo_owner_visibility.py
git commit -m "feat(store): extend McpConfig model + repo with owner/visibility"
```

---

## Task 3: 新增 Prompt 模型 + 双 Repository（L5）

**Files:**
- 新建：`src/hermetic_agent/store/models/prompt.py`
- 新建：`src/hermetic_agent/store/repositories/prompt_repo.py`
- 新建：`src/hermetic_agent/store/repositories/memory/prompt_repo_memory.py`
- 新建：`src/hermetic_agent/store/repositories/mysql/prompt_repo_mysql.py`
- 修改：`src/hermetic_agent/store/models/__init__.py`、`store/repositories/__init__.py`
- 新建：`tests/test_prompt_repo_crud.py`

**Interfaces:** 与 Task 1 同形态，模型替换为 `Prompt`，新增 `content: TextField`（必填）。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_prompt_repo_crud.py
import uuid
import pytest

from hermetic_agent.store.models.prompt import Prompt
from hermetic_agent.store.repositories.memory.prompt_repo_memory import MemoryPromptRepository


@pytest.mark.asyncio
async def test_create_and_get_by_code():
    repo = MemoryPromptRepository()
    p = Prompt(id=uuid.uuid4(), code="hello", name="Hello",
               description="greeting prompt", content="say hi",
               owner_user_id="alice", visibility="private", status="enabled")
    await repo.create(p)
    got = await repo.get_by_code("hello")
    assert got is not None and got.content == "say hi"


@pytest.mark.asyncio
async def test_soft_delete_and_get_by_code_returns_none():
    repo = MemoryPromptRepository()
    p = Prompt(id=uuid.uuid4(), code="bye", name="B",
               content="say bye", owner_user_id="alice", status="enabled")
    await repo.create(p)
    assert await repo.soft_delete(str(p.id)) is True
    assert await repo.get_by_code("bye") is None
    assert await repo.soft_delete(str(p.id)) is False  # 幂等


@pytest.mark.asyncio
async def test_set_visibility_owner_only():
    repo = MemoryPromptRepository()
    p = Prompt(id=uuid.uuid4(), code="x", name="X",
               content="c", owner_user_id="alice", status="enabled")
    await repo.create(p)
    r = await repo.set_visibility(str(p.id), visibility="public", actor_user_id="bob")
    assert r is None
    r = await repo.set_visibility(str(p.id), visibility="public", actor_user_id="alice")
    assert r.visibility == "public"
```

- [ ] **Step 2: 跑测试验证失败**

Run: `pytest tests/test_prompt_repo_crud.py -v` — FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 写 `Prompt` 模型**

```python
# src/hermetic_agent/store/models/prompt.py
from __future__ import annotations
from tortoise import fields
from tortoise.models import Model


class Prompt(Model):
    id = fields.UUIDField(pk=True, binary=False)
    code = fields.CharField(max_length=128, unique=True)
    name = fields.CharField(max_length=255)
    version = fields.IntField(default=1)
    description = fields.TextField(null=True)
    content = fields.TextField()
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

    def __str__(self) -> str:
        return f"Prompt({self.code})"


__all__ = ["Prompt"]
```

- [ ] **Step 4: 导出模型**

```python
# src/hermetic_agent/store/models/__init__.py 末尾追加（保留既有）:
from hermetic_agent.store.models.prompt import Prompt  # re-export
# 如果有 __all__ 列表，追加 "Prompt"
```

- [ ] **Step 5: 写 `PromptRepository` ABC**

```python
# src/hermetic_agent/store/repositories/prompt_repo.py
from __future__ import annotations
from abc import abstractmethod
from typing import Any

from hermetic_agent.store.models.prompt import Prompt
from hermetic_agent.store.repositories._base import Repository


class PromptRepository(Repository[Prompt]):
    @abstractmethod
    async def get_by_id(self, prompt_id: str) -> Prompt | None: ...

    @abstractmethod
    async def get_by_code(self, code: str) -> Prompt | None: ...

    @abstractmethod
    async def list(self, *, limit: int = 50, offset: int = 0,
                  include_deleted: bool = False, **filters: Any) -> list[Prompt]: ...

    @abstractmethod
    async def count(self, *, include_deleted: bool = False,
                    **filters: Any) -> int: ...

    @abstractmethod
    async def create(self, prompt: Prompt) -> Prompt: ...

    @abstractmethod
    async def update(self, prompt_id: str, **fields: Any) -> Prompt | None: ...

    @abstractmethod
    async def soft_delete(self, prompt_id: str) -> bool: ...

    @abstractmethod
    async def hard_delete(self, prompt_id: str) -> bool: ...

    @abstractmethod
    async def list_visible_to(self, *, actor_user_id: str, limit: int = 50,
                             offset: int = 0, code: str | None = None,
                             status: str | None = None) -> list[Prompt]: ...

    @abstractmethod
    async def list_public(self, *, limit: int = 50, offset: int = 0,
                          code: str | None = None) -> list[Prompt]: ...

    @abstractmethod
    async def set_visibility(self, prompt_id: str, *,
                             visibility: str,
                             actor_user_id: str) -> Prompt | None: ...


__all__ = ["PromptRepository"]
```

- [ ] **Step 6: 实现 `MemoryPromptRepository`**

```python
# src/hermetic_agent/store/repositories/memory/prompt_repo_memory.py
from __future__ import annotations
from typing import Any

from hermetic_agent.store.models._common import utcnow
from hermetic_agent.store.models.prompt import Prompt
from hermetic_agent.store.repositories.memory._base import MemoryRepository
from hermetic_agent.store.repositories.prompt_repo import PromptRepository


class MemoryPromptRepository(MemoryRepository[Prompt], PromptRepository):
    async def get_by_id(self, entity_id):
        p = self._store.get(entity_id)
        return None if (p is None or p.is_deleted) else p

    async def get_by_code(self, code):
        for p in self._store.values():
            if p.code == code and not p.is_deleted:
                return p
        return None

    async def list(self, *, limit=50, offset=0, include_deleted=False, **filters):
        items = list(self._store.values())
        if not include_deleted:
            items = [p for p in items if not p.is_deleted]
        for k in ("code", "status"):
            if filters.get(k) is not None:
                items = [p for p in items if getattr(p, k) == filters[k]]
        items.sort(key=lambda p: (p.updated_at, p.id), reverse=True)
        return items[offset:offset + limit]

    async def count(self, *, include_deleted=False, **filters):
        items = list(self._store.values())
        if not include_deleted:
            items = [p for p in items if not p.is_deleted]
        for k in ("code", "status"):
            if filters.get(k) is not None:
                items = [p for p in items if getattr(p, k) == filters[k]]
        return len(items)

    async def create(self, model):
        self._store[model.id] = model
        return model

    async def update(self, entity_id, **fields):
        p = self._store.get(entity_id)
        if p is None or p.is_deleted:
            return None
        for k, v in fields.items():
            setattr(p, k, v)
        p.updated_at = utcnow()
        return p

    async def soft_delete(self, entity_id):
        p = self._store.get(entity_id)
        if p is None or p.is_deleted:
            return False
        p.is_deleted = True
        p.deleted_at = utcnow()
        return True

    async def hard_delete(self, entity_id):
        return self._store.pop(entity_id, None) is not None

    async def list_visible_to(self, *, actor_user_id, limit=50, offset=0, code=None, status=None):
        items = [p for p in self._store.values()
                 if not p.is_deleted and (
                     p.owner_user_id == actor_user_id or p.visibility == "public"
                 )]
        if code is not None:
            items = [p for p in items if p.code == code]
        if status is not None:
            items = [p for p in items if p.status == status]
        items.sort(key=lambda p: (p.updated_at, p.id), reverse=True)
        return items[offset:offset + limit]

    async def list_public(self, *, limit=50, offset=0, code=None):
        items = [p for p in self._store.values()
                 if not p.is_deleted and p.visibility == "public"]
        if code is not None:
            items = [p for p in items if p.code == code]
        items.sort(key=lambda p: (p.updated_at, p.id), reverse=True)
        return items[offset:offset + limit]

    async def set_visibility(self, prompt_id, *, visibility, actor_user_id):
        if visibility not in ("private", "public"):
            raise ValueError("invalid visibility")
        p = self._store.get(prompt_id)
        if p is None or p.is_deleted:
            return None
        if p.owner_user_id != actor_user_id:
            return None
        p.visibility = visibility
        return p


__all__ = ["MemoryPromptRepository"]
```

- [ ] **Step 7: 实现 `MySQLPromptRepository`**

```python
# src/hermetic_agent/store/repositories/mysql/prompt_repo_mysql.py
from __future__ import annotations
from typing import Any

from tortoise.expressions import Q

from hermetic_agent.store.models._common import utcnow
from hermetic_agent.store.models.prompt import Prompt
from hermetic_agent.store.repositories.prompt_repo import PromptRepository


class MySQLPromptRepository(PromptRepository):
    async def get_by_id(self, entity_id):
        return await Prompt.get_or_none(id=entity_id, is_deleted=False)

    async def get_by_code(self, code):
        return await Prompt.get_or_none(code=code, is_deleted=False)

    async def list(self, *, limit=50, offset=0, include_deleted=False, **filters):
        qs = Prompt.all()
        if not include_deleted:
            qs = qs.filter(is_deleted=False)
        for k in ("code", "status"):
            if filters.get(k) is not None:
                qs = qs.filter(**{k: filters[k]})
        return await qs.order_by("-updated_at", "-id").offset(offset).limit(limit)

    async def count(self, *, include_deleted=False, **filters):
        qs = Prompt.all()
        if not include_deleted:
            qs = qs.filter(is_deleted=False)
        for k in ("code", "status"):
            if filters.get(k) is not None:
                qs = qs.filter(**{k: filters[k]})
        return await qs.count()

    async def create(self, model):
        await model.save()
        return model

    async def update(self, entity_id, **fields):
        if not fields:
            return await self.get_by_id(entity_id)
        await Prompt.filter(id=entity_id).update(**fields, updated_at=utcnow())
        return await self.get_by_id(entity_id)

    async def soft_delete(self, entity_id):
        rc = await Prompt.filter(id=entity_id, is_deleted=False).update(
            is_deleted=True, deleted_at=utcnow())
        return rc > 0

    async def hard_delete(self, entity_id):
        rc = await Prompt.filter(id=entity_id).delete()
        return rc > 0

    async def list_visible_to(self, *, actor_user_id, limit=50, offset=0, code=None, status=None):
        qs = Prompt.filter(is_deleted=False).filter(
            Q(owner_user_id=actor_user_id) | Q(visibility="public"))
        if code is not None:
            qs = qs.filter(code=code)
        if status is not None:
            qs = qs.filter(status=status)
        return await qs.order_by("-updated_at", "-id").offset(offset).limit(limit)

    async def list_public(self, *, limit=50, offset=0, code=None):
        qs = Prompt.filter(is_deleted=False, visibility="public")
        if code is not None:
            qs = qs.filter(code=code)
        return await qs.order_by("-updated_at", "-id").offset(offset).limit(limit)

    async def set_visibility(self, prompt_id, *, visibility, actor_user_id):
        if visibility not in ("private", "public"):
            raise ValueError("invalid visibility")
        rc = await Prompt.filter(
            id=prompt_id, is_deleted=False, owner_user_id=actor_user_id
        ).update(visibility=visibility)
        return (await self.get_by_id(prompt_id)) if rc else None


__all__ = ["MySQLPromptRepository"]
```

- [ ] **Step 8: 导出新 repo**

```python
# src/hermetic_agent/store/repositories/__init__.py 末尾追加:
from hermetic_agent.store.repositories.prompt_repo import PromptRepository as PromptRepository

from hermetic_agent.store.repositories.memory.prompt_repo_memory import (
    MemoryPromptRepository as MemoryPromptRepository,
)
from hermetic_agent.store.repositories.mysql.prompt_repo_mysql import (
    MySQLPromptRepository as MySQLPromptRepository,
)
# 如果有 __all__ 列表，追加 "PromptRepository", "MemoryPromptRepository", "MySQLPromptRepository"
```

- [ ] **Step 9: 跑测试验证通过**

Run: `pytest tests/test_prompt_repo_crud.py -v` — 3 passed

- [ ] **Step 10: 提交**

```bash
git add src/hermetic_agent/store/models/prompt.py \
        src/hermetic_agent/store/models/__init__.py \
        src/hermetic_agent/store/repositories/prompt_repo.py \
        src/hermetic_agent/store/repositories/memory/prompt_repo_memory.py \
        src/hermetic_agent/store/repositories/mysql/prompt_repo_mysql.py \
        src/hermetic_agent/store/repositories/__init__.py \
        tests/test_prompt_repo_crud.py
git commit -m "feat(store): add Prompt model + dual repos (memory + mysql)"
```

---

> **继续阅读 `2026-06-30-asset-registry-plan-2.md`（Phase 2 + Phase 3）以及 `2026-06-30-asset-registry-plan-3.md`（Phase 4 收口）**。
