# 资产注册中心实现计划 — Part 2 / 3

> 配套主计划：`2026-06-30-asset-registry-plan.md`（Phase 1 数据面前 3 个任务）。
> 本文件覆盖 **Phase 1 后段**（Task 4–9）：Command + Agent + DTO + 3 Service + ServiceContainer + ActorContext + 3 Controller + Skill/McpConfig service visibility。

---

## Task 4: 新增 Command 模型 + 双 Repository（L5）

**Files:**
- 新建：`src/hermetic_agent/store/models/command.py`
- 新建：`src/hermetic_agent/store/repositories/command_repo.py`
- 新建：`src/hermetic_agent/store/repositories/memory/command_repo_memory.py`
- 新建：`src/hermetic_agent/store/repositories/mysql/command_repo_mysql.py`
- 修改：`src/hermetic_agent/store/models/__init__.py`、`store/repositories/__init__.py`
- 新建：`tests/test_command_repo_crud.py`

**Interfaces:** 与 Task 3 同形态，model = `Command`，多 2 字段 `slash_command` / `system_prompt_addendum` + `enabled` + `unique_together = [("code", "slash_command")]`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_command_repo_crud.py
import uuid
import pytest

from hermetic_agent.store.models.command import Command
from hermetic_agent.store.repositories.memory.command_repo_memory import MemoryCommandRepository


@pytest.mark.asyncio
async def test_create_command_stores_slash_and_prompt():
    repo = MemoryCommandRepository()
    c = Command(
        id=uuid.uuid4(), code="summarizer", name="Summarizer",
        slash_command="/summarize",
        system_prompt_addendum="When user types /summarize, output 3 bullet points.",
        owner_user_id="alice", visibility="private", status="enabled",
    )
    await repo.create(c)
    got = await repo.get_by_code("summarizer")
    assert got.slash_command == "/summarize"
    assert got.system_prompt_addendum.startswith("When user types")


@pytest.mark.asyncio
async def test_get_by_slash_returns_command():
    repo = MemoryCommandRepository()
    c = Command(id=uuid.uuid4(), code="x", name="X",
                slash_command="/x", system_prompt_addendum="...",
                owner_user_id="alice", status="enabled")
    await repo.create(c)
    got = await repo.get_by_slash("/x")
    assert got is not None and got.code == "x"


@pytest.mark.asyncio
async def test_set_visibility_owner_only():
    repo = MemoryCommandRepository()
    c = Command(id=uuid.uuid4(), code="x", name="X",
                slash_command="/x", system_prompt_addendum="...",
                owner_user_id="alice", status="enabled")
    await repo.create(c)
    assert (await repo.set_visibility(str(c.id), visibility="public",
                                       actor_user_id="bob")) is None
    assert (await repo.set_visibility(str(c.id), visibility="public",
                                       actor_user_id="alice")).visibility == "public"
```

- [ ] **Step 2: 跑测试验证失败**

Run: `pytest tests/test_command_repo_crud.py -v` — FAIL（model 不存在）

- [ ] **Step 3: 写 `Command` 模型**

```python
# src/hermetic_agent/store/models/command.py
from __future__ import annotations
from tortoise import fields
from tortoise.models import Model


class Command(Model):
    id = fields.UUIDField(pk=True, binary=False)
    code = fields.CharField(max_length=128, description="业务短码")
    name = fields.CharField(max_length=255)
    version = fields.IntField(default=1)
    description = fields.TextField(null=True)
    slash_command = fields.CharField(max_length=64,
                                     description="用户输入的命令，如 /summarize")
    system_prompt_addendum = fields.TextField(description="拼到 system_prompt 的说明")
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
        unique_together = [("code", "slash_command")]
        indexes = [
            ("status", "is_deleted"),
            ("owner_user_id", "visibility", "is_deleted"),
            ("slash_command",),
            ("updated_at",),
        ]
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"Command({self.code} {self.slash_command})"


__all__ = ["Command"]
```

- [ ] **Step 4: 导出 Command 模型**

```python
# src/hermetic_agent/store/models/__init__.py 末尾追加:
from hermetic_agent.store.models.command import Command
```

- [ ] **Step 5: 写 `CommandRepository` ABC**

```python
# src/hermetic_agent/store/repositories/command_repo.py
from __future__ import annotations
from abc import abstractmethod
from typing import Any

from hermetic_agent.store.models.command import Command
from hermetic_agent.store.repositories._base import Repository


class CommandRepository(Repository[Command]):
    @abstractmethod
    async def get_by_id(self, command_id): ...
    @abstractmethod
    async def get_by_code(self, code): ...
    @abstractmethod
    async def get_by_slash(self, slash_command: str): ...
    @abstractmethod
    async def list(self, *, limit=50, offset=0, include_deleted=False, **filters): ...
    @abstractmethod
    async def count(self, *, include_deleted=False, **filters): ...
    @abstractmethod
    async def create(self, command): ...
    @abstractmethod
    async def update(self, command_id, **fields): ...
    @abstractmethod
    async def soft_delete(self, command_id): ...
    @abstractmethod
    async def hard_delete(self, command_id): ...
    @abstractmethod
    async def list_visible_to(self, *, actor_user_id, limit=50, offset=0, code=None, status=None): ...
    @abstractmethod
    async def list_public(self, *, limit=50, offset=0, code=None): ...
    @abstractmethod
    async def set_visibility(self, command_id, *, visibility, actor_user_id): ...


__all__ = ["CommandRepository"]
```

- [ ] **Step 6: 实现 `MemoryCommandRepository`**

```python
# src/hermetic_agent/store/repositories/memory/command_repo_memory.py
from __future__ import annotations
from typing import Any

from hermetic_agent.store.models._common import utcnow
from hermetic_agent.store.models.command import Command
from hermetic_agent.store.repositories.memory._base import MemoryRepository
from hermetic_agent.store.repositories.command_repo import CommandRepository


class MemoryCommandRepository(MemoryRepository[Command], CommandRepository):
    async def get_by_id(self, entity_id):
        c = self._store.get(entity_id)
        return None if (c is None or c.is_deleted) else c

    async def get_by_code(self, code):
        for c in self._store.values():
            if c.code == code and not c.is_deleted:
                return c
        return None

    async def get_by_slash(self, slash_command):
        for c in self._store.values():
            if c.slash_command == slash_command and not c.is_deleted:
                return c
        return None

    async def list(self, *, limit=50, offset=0, include_deleted=False, **filters):
        items = list(self._store.values())
        if not include_deleted:
            items = [c for c in items if not c.is_deleted]
        for k in ("code", "status"):
            if filters.get(k) is not None:
                items = [c for c in items if getattr(c, k) == filters[k]]
        items.sort(key=lambda c: (c.updated_at, c.id), reverse=True)
        return items[offset:offset + limit]

    async def count(self, *, include_deleted=False, **filters):
        items = list(self._store.values())
        if not include_deleted:
            items = [c for c in items if not c.is_deleted]
        for k in ("code", "status"):
            if filters.get(k) is not None:
                items = [c for c in items if getattr(c, k) == filters[k]]
        return len(items)

    async def create(self, model):
        self._store[model.id] = model
        return model

    async def update(self, entity_id, **fields):
        c = self._store.get(entity_id)
        if c is None or c.is_deleted:
            return None
        for k, v in fields.items():
            setattr(c, k, v)
        c.updated_at = utcnow()
        return c

    async def soft_delete(self, entity_id):
        c = self._store.get(entity_id)
        if c is None or c.is_deleted:
            return False
        c.is_deleted = True
        c.deleted_at = utcnow()
        return True

    async def hard_delete(self, entity_id):
        return self._store.pop(entity_id, None) is not None

    async def list_visible_to(self, *, actor_user_id, limit=50, offset=0, code=None, status=None):
        items = [c for c in self._store.values()
                 if not c.is_deleted and (
                     c.owner_user_id == actor_user_id or c.visibility == "public"
                 )]
        if code is not None:
            items = [c for c in items if c.code == code]
        if status is not None:
            items = [c for c in items if c.status == status]
        items.sort(key=lambda c: (c.updated_at, c.id), reverse=True)
        return items[offset:offset + limit]

    async def list_public(self, *, limit=50, offset=0, code=None):
        items = [c for c in self._store.values()
                 if not c.is_deleted and c.visibility == "public"]
        if code is not None:
            items = [c for c in items if c.code == code]
        items.sort(key=lambda c: (c.updated_at, c.id), reverse=True)
        return items[offset:offset + limit]

    async def set_visibility(self, command_id, *, visibility, actor_user_id):
        if visibility not in ("private", "public"):
            raise ValueError("invalid visibility")
        c = self._store.get(command_id)
        if c is None or c.is_deleted:
            return None
        if c.owner_user_id != actor_user_id:
            return None
        c.visibility = visibility
        return c


__all__ = ["MemoryCommandRepository"]
```

- [ ] **Step 7: 实现 `MySQLCommandRepository`**

```python
# src/hermetic_agent/store/repositories/mysql/command_repo_mysql.py
from __future__ import annotations
from typing import Any

from tortoise.expressions import Q

from hermetic_agent.store.models._common import utcnow
from hermetic_agent.store.models.command import Command
from hermetic_agent.store.repositories.command_repo import CommandRepository


class MySQLCommandRepository(CommandRepository):
    async def get_by_id(self, entity_id):
        return await Command.get_or_none(id=entity_id, is_deleted=False)

    async def get_by_code(self, code):
        return await Command.get_or_none(code=code, is_deleted=False)

    async def get_by_slash(self, slash_command):
        return await Command.get_or_none(slash_command=slash_command, is_deleted=False)

    async def list(self, *, limit=50, offset=0, include_deleted=False, **filters):
        qs = Command.all()
        if not include_deleted:
            qs = qs.filter(is_deleted=False)
        for k in ("code", "status"):
            if filters.get(k) is not None:
                qs = qs.filter(**{k: filters[k]})
        return await qs.order_by("-updated_at", "-id").offset(offset).limit(limit)

    async def count(self, *, include_deleted=False, **filters):
        qs = Command.all()
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
        await Command.filter(id=entity_id).update(**fields, updated_at=utcnow())
        return await self.get_by_id(entity_id)

    async def soft_delete(self, entity_id):
        rc = await Command.filter(id=entity_id, is_deleted=False).update(
            is_deleted=True, deleted_at=utcnow())
        return rc > 0

    async def hard_delete(self, entity_id):
        rc = await Command.filter(id=entity_id).delete()
        return rc > 0

    async def list_visible_to(self, *, actor_user_id, limit=50, offset=0, code=None, status=None):
        qs = Command.filter(is_deleted=False).filter(
            Q(owner_user_id=actor_user_id) | Q(visibility="public"))
        if code is not None:
            qs = qs.filter(code=code)
        if status is not None:
            qs = qs.filter(status=status)
        return await qs.order_by("-updated_at", "-id").offset(offset).limit(limit)

    async def list_public(self, *, limit=50, offset=0, code=None):
        qs = Command.filter(is_deleted=False, visibility="public")
        if code is not None:
            qs = qs.filter(code=code)
        return await qs.order_by("-updated_at", "-id").offset(offset).limit(limit)

    async def set_visibility(self, command_id, *, visibility, actor_user_id):
        if visibility not in ("private", "public"):
            raise ValueError("invalid visibility")
        rc = await Command.filter(
            id=command_id, is_deleted=False, owner_user_id=actor_user_id
        ).update(visibility=visibility)
        return (await self.get_by_id(command_id)) if rc else None


__all__ = ["MySQLCommandRepository"]
```

- [ ] **Step 8: 导出新 repo**

```python
# src/hermetic_agent/store/repositories/__init__.py 末尾追加:
from hermetic_agent.store.repositories.command_repo import CommandRepository
from hermetic_agent.store.repositories.memory.command_repo_memory import MemoryCommandRepository
from hermetic_agent.store.repositories.mysql.command_repo_mysql import MySQLCommandRepository
```

- [ ] **Step 9: 跑测试**

Run: `pytest tests/test_command_repo_crud.py -v` — 3 passed

- [ ] **Step 10: 提交**

```bash
git add src/hermetic_agent/store/models/command.py \
        src/hermetic_agent/store/models/__init__.py \
        src/hermetic_agent/store/repositories/command_repo.py \
        src/hermetic_agent/store/repositories/memory/command_repo_memory.py \
        src/hermetic_agent/store/repositories/mysql/command_repo_mysql.py \
        src/hermetic_agent/store/repositories/__init__.py \
        tests/test_command_repo_crud.py
git commit -m "feat(store): add Command model + dual repos"
```

---

## Task 5: 新增 Agent 模型 + 双 Repository（L5）

**Files:** 同 Task 3/4 模板，仅模型 / repo 字段差异。变更如下：

- 新建：`src/hermetic_agent/store/models/agent.py`（4 个 `*_codes JSONField` + 4 个配置字段）
- 新建：`src/hermetic_agent/store/repositories/agent_repo.py`（与 Task 3 同形态）
- 新建：`src/hermetic_agent/store/repositories/memory/agent_repo_memory.py`
- 新建：`src/hermetic_agent/store/repositories/mysql/agent_repo_mysql.py`
- 修改：相应 `__init__.py` 列表
- 新建：`tests/test_agent_repo_crud.py`

**Interfaces:** `Agent` 模型字段见 spec 文档 §3 + 表设计 doc §2.5。Repository ABC 含同样 11 个方法（mirror Prompt，无 `get_by_slash`）。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_agent_repo_crud.py
import uuid
import pytest

from hermetic_agent.store.models.agent import Agent
from hermetic_agent.store.repositories.memory.agent_repo_memory import MemoryAgentRepository


@pytest.mark.asyncio
async def test_create_agent_with_reference_lists():
    repo = MemoryAgentRepository()
    a = Agent(
        id=uuid.uuid4(), code="travel-agent", name="Travel",
        description="helps with travel",
        system_prompt="You are a travel assistant.",
        model="openai/gpt-4o-mini", tool_level="standard", network="local",
        skill_codes=["flight-query", "booking"],
        mcp_server_codes=["default_mcp"],
        prompt_codes=["safety"],
        command_codes=["summarize"],
        owner_user_id="alice", visibility="private", status="enabled",
    )
    await repo.create(a)
    got = await repo.get_by_code("travel-agent")
    assert got.skill_codes == ["flight-query", "booking"]
    assert got.prompt_codes == ["safety"]


@pytest.mark.asyncio
async def test_set_visibility_owner_only_and_list_public():
    repo = MemoryAgentRepository()
    a = Agent(id=uuid.uuid4(), code="x", name="X", system_prompt="p",
              model="openai/mini", tool_level="standard", network="local",
              owner_user_id="alice", visibility="private", status="enabled",
              skill_codes=[], mcp_server_codes=[], prompt_codes=[], command_codes=[])
    await repo.create(a)
    assert (await repo.set_visibility(str(a.id), visibility="public",
                                       actor_user_id="bob")) is None
    assert (await repo.set_visibility(str(a.id), visibility="public",
                                       actor_user_id="alice")).visibility == "public"
    pub_list = await repo.list_public(limit=10, offset=0)
    assert len(pub_list) == 1
```

- [ ] **Step 2: 跑测试验证失败**

Run: `pytest tests/test_agent_repo_crud.py -v` — FAIL（model 不存在）

- [ ] **Step 3: 写 `Agent` 模型**

```python
# src/hermetic_agent/store/models/agent.py
from __future__ import annotations
from tortoise import fields
from tortoise.models import Model


class Agent(Model):
    id = fields.UUIDField(pk=True, binary=False)
    code = fields.CharField(max_length=128, unique=True)
    name = fields.CharField(max_length=255)
    version = fields.IntField(default=1)
    description = fields.TextField(null=True)
    system_prompt = fields.TextField(default="")
    model = fields.CharField(max_length=128, default="openai/gpt-4o-mini")
    tool_level = fields.CharField(max_length=16, default="standard")
    network = fields.CharField(max_length=16, default="local")
    skill_codes = fields.JSONField(default=list)
    mcp_server_codes = fields.JSONField(default=list)
    prompt_codes = fields.JSONField(default=list)
    command_codes = fields.JSONField(default=list)
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

    def __str__(self) -> str:
        return f"Agent({self.code})"


__all__ = ["Agent"]
```

- [ ] **Step 4: 导出 + 写 `AgentRepository` ABC**

```python
# src/hermetic_agent/store/repositories/__init__.py 加 Agent
from hermetic_agent.store.models.agent import Agent  # models/__init__.py

# src/hermetic_agent/store/repositories/agent_repo.py
from __future__ import annotations
from abc import abstractmethod
from typing import Any

from hermetic_agent.store.models.agent import Agent
from hermetic_agent.store.repositories._base import Repository


class AgentRepository(Repository[Agent]):
    @abstractmethod
    async def get_by_id(self, agent_id): ...
    @abstractmethod
    async def get_by_code(self, code): ...
    @abstractmethod
    async def list(self, *, limit=50, offset=0, include_deleted=False, **filters): ...
    @abstractmethod
    async def count(self, *, include_deleted=False, **filters): ...
    @abstractmethod
    async def create(self, agent): ...
    @abstractmethod
    async def update(self, agent_id, **fields): ...
    @abstractmethod
    async def soft_delete(self, agent_id): ...
    @abstractmethod
    async def hard_delete(self, agent_id): ...
    @abstractmethod
    async def list_visible_to(self, *, actor_user_id, limit=50, offset=0,
                             code=None, status=None): ...
    @abstractmethod
    async def list_public(self, *, limit=50, offset=0, code=None): ...
    @abstractmethod
    async def set_visibility(self, agent_id, *, visibility, actor_user_id): ...


__all__ = ["AgentRepository"]
```

- [ ] **Step 5: 实现 `MemoryAgentRepository`**

```python
# src/hermetic_agent/store/repositories/memory/agent_repo_memory.py
# 镜像 MemoryPromptRepository，把 Prompt 换为 Agent；11 个方法全列，去掉 get_by_slash。
from __future__ import annotations
from typing import Any

from hermetic_agent.store.models._common import utcnow
from hermetic_agent.store.models.agent import Agent
from hermetic_agent.store.repositories.memory._base import MemoryRepository
from hermetic_agent.store.repositories.agent_repo import AgentRepository


class MemoryAgentRepository(MemoryRepository[Agent], AgentRepository):
    async def get_by_id(self, entity_id):
        a = self._store.get(entity_id)
        return None if (a is None or a.is_deleted) else a

    async def get_by_code(self, code):
        for a in self._store.values():
            if a.code == code and not a.is_deleted:
                return a
        return None

    async def list(self, *, limit=50, offset=0, include_deleted=False, **filters):
        items = list(self._store.values())
        if not include_deleted:
            items = [a for a in items if not a.is_deleted]
        for k in ("code", "status"):
            if filters.get(k) is not None:
                items = [a for a in items if getattr(a, k) == filters[k]]
        items.sort(key=lambda a: (a.updated_at, a.id), reverse=True)
        return items[offset:offset + limit]

    async def count(self, *, include_deleted=False, **filters):
        items = list(self._store.values())
        if not include_deleted:
            items = [a for a in items if not a.is_deleted]
        for k in ("code", "status"):
            if filters.get(k) is not None:
                items = [a for a in items if getattr(a, k) == filters[k]]
        return len(items)

    async def create(self, model):
        self._store[model.id] = model
        return model

    async def update(self, entity_id, **fields):
        a = self._store.get(entity_id)
        if a is None or a.is_deleted:
            return None
        for k, v in fields.items():
            setattr(a, k, v)
        a.updated_at = utcnow()
        return a

    async def soft_delete(self, entity_id):
        a = self._store.get(entity_id)
        if a is None or a.is_deleted:
            return False
        a.is_deleted = True
        a.deleted_at = utcnow()
        return True

    async def hard_delete(self, entity_id):
        return self._store.pop(entity_id, None) is not None

    async def list_visible_to(self, *, actor_user_id, limit=50, offset=0, code=None, status=None):
        items = [a for a in self._store.values()
                 if not a.is_deleted and (
                     a.owner_user_id == actor_user_id or a.visibility == "public"
                 )]
        if code is not None:
            items = [a for a in items if a.code == code]
        if status is not None:
            items = [a for a in items if a.status == status]
        items.sort(key=lambda a: (a.updated_at, a.id), reverse=True)
        return items[offset:offset + limit]

    async def list_public(self, *, limit=50, offset=0, code=None):
        items = [a for a in self._store.values()
                 if not a.is_deleted and a.visibility == "public"]
        if code is not None:
            items = [a for a in items if a.code == code]
        items.sort(key=lambda a: (a.updated_at, a.id), reverse=True)
        return items[offset:offset + limit]

    async def set_visibility(self, agent_id, *, visibility, actor_user_id):
        if visibility not in ("private", "public"):
            raise ValueError("invalid visibility")
        a = self._store.get(agent_id)
        if a is None or a.is_deleted:
            return None
        if a.owner_user_id != actor_user_id:
            return None
        a.visibility = visibility
        return a


__all__ = ["MemoryAgentRepository"]
```

- [ ] **Step 6: 实现 `MySQLAgentRepository`**

```python
# src/hermetic_agent/store/repositories/mysql/agent_repo_mysql.py
# 镜像 MySQLPromptRepository，把 Prompt 换为 Agent；11 个方法。
from __future__ import annotations
from typing import Any

from tortoise.expressions import Q

from hermetic_agent.store.models._common import utcnow
from hermetic_agent.store.models.agent import Agent
from hermetic_agent.store.repositories.agent_repo import AgentRepository


class MySQLAgentRepository(AgentRepository):
    async def get_by_id(self, entity_id):
        return await Agent.get_or_none(id=entity_id, is_deleted=False)

    async def get_by_code(self, code):
        return await Agent.get_or_none(code=code, is_deleted=False)

    async def list(self, *, limit=50, offset=0, include_deleted=False, **filters):
        qs = Agent.all()
        if not include_deleted:
            qs = qs.filter(is_deleted=False)
        for k in ("code", "status"):
            if filters.get(k) is not None:
                qs = qs.filter(**{k: filters[k]})
        return await qs.order_by("-updated_at", "-id").offset(offset).limit(limit)

    async def count(self, *, include_deleted=False, **filters):
        qs = Agent.all()
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
        await Agent.filter(id=entity_id).update(**fields, updated_at=utcnow())
        return await self.get_by_id(entity_id)

    async def soft_delete(self, entity_id):
        rc = await Agent.filter(id=entity_id, is_deleted=False).update(
            is_deleted=True, deleted_at=utcnow())
        return rc > 0

    async def hard_delete(self, entity_id):
        rc = await Agent.filter(id=entity_id).delete()
        return rc > 0

    async def list_visible_to(self, *, actor_user_id, limit=50, offset=0, code=None, status=None):
        qs = Agent.filter(is_deleted=False).filter(
            Q(owner_user_id=actor_user_id) | Q(visibility="public"))
        if code is not None:
            qs = qs.filter(code=code)
        if status is not None:
            qs = qs.filter(status=status)
        return await qs.order_by("-updated_at", "-id").offset(offset).limit(limit)

    async def list_public(self, *, limit=50, offset=0, code=None):
        qs = Agent.filter(is_deleted=False, visibility="public")
        if code is not None:
            qs = qs.filter(code=code)
        return await qs.order_by("-updated_at", "-id").offset(offset).limit(limit)

    async def set_visibility(self, agent_id, *, visibility, actor_user_id):
        if visibility not in ("private", "public"):
            raise ValueError("invalid visibility")
        rc = await Agent.filter(
            id=agent_id, is_deleted=False, owner_user_id=actor_user_id
        ).update(visibility=visibility)
        return (await self.get_by_id(agent_id)) if rc else None


__all__ = ["MySQLAgentRepository"]
```

- [ ] **Step 7: 导出新 repo**

```python
# src/hermetic_agent/store/repositories/__init__.py 末尾追加:
from hermetic_agent.store.repositories.agent_repo import AgentRepository
from hermetic_agent.store.repositories.memory.agent_repo_memory import MemoryAgentRepository
from hermetic_agent.store.repositories.mysql.agent_repo_mysql import MySQLAgentRepository
```

- [ ] **Step 8: 跑测试**

Run: `pytest tests/test_agent_repo_crud.py -v` — 2 passed

- [ ] **Step 9: 提交**

```bash
git add src/hermetic_agent/store/models/agent.py \
        src/hermetic_agent/store/models/__init__.py \
        src/hermetic_agent/store/repositories/agent_repo.py \
        src/hermetic_agent/store/repositories/memory/agent_repo_memory.py \
        src/hermetic_agent/store/repositories/mysql/agent_repo_mysql.py \
        src/hermetic_agent/store/repositories/__init__.py \
        tests/test_agent_repo_crud.py
git commit -m "feat(store): add Agent model + dual repos"
```

---

## Task 6: DTO + 3 个 Service + ServiceContainer 接线（L5）

**Files:**
- 修改：`src/hermetic_agent/store/dto/_common.py`（追加 `ActorContext`）
- 新建：`src/hermetic_agent/store/dto/{prompt,command,agent}.py`
- 修改：`src/hermetic_agent/store/dto/__init__.py`
- 新建：`src/hermetic_agent/store/services/{prompt,command,agent}_service.py`
- 修改：`src/hermetic_agent/store/services/container.py`（3 个新 service + ServiceContainer 字段 + 工厂 wiring）
- 修改：`src/hermetic_agent/store/services/__init__.py`（导出新 service）
- 新建：`tests/test_prompt_service_crud.py`、`test_command_service_crud.py`、`test_agent_service_crud.py`

**Interfaces:**
- `ActorContext(user_id, tenant_id?, roles?)` dataclass
- `*Service` 类（不一一列，mirror PromptService）

- [ ] **Step 1: 添加 `ActorContext` 到 `dto/_common.py`**

```python
# src/hermetic_agent/store/dto/_common.py 末尾追加（保留既有）:
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ActorContext:
    user_id: str
    tenant_id: Optional[str] = None
    roles: list[str] = field(default_factory=list)

    def is_anonymous(self) -> bool:
        return self.user_id == "anonymous"


__all__ = ["ActorContext"]  # 保留既有导出 + 加此项
```

- [ ] **Step 2: 写 `prompt.py` DTO**

```python
# src/hermetic_agent/store/dto/prompt.py
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field


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
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, m) -> "PromptResponse":
        return cls(
            id=str(m.id), code=m.code, name=m.name, version=m.version,
            description=m.description, content=m.content,
            owner_user_id=m.owner_user_id, visibility=m.visibility,
            status=m.status, created_at=m.created_at, updated_at=m.updated_at,
        )


class PromptListResponse(BaseModel):
    total: int
    items: list[PromptResponse]


__all__ = ["CreatePromptRequest", "UpdatePromptRequest", "PromptResponse", "PromptListResponse"]
```

- [ ] **Step 3: 写 `command.py` DTO**

```python
# src/hermetic_agent/store/dto/command.py
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field


class CreateCommandRequest(BaseModel):
    code: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_\-]+$")
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2048)
    slash_command: str = Field(pattern=r"^/[A-Za-z0-9_\-]+$")
    system_prompt_addendum: str = Field(min_length=1)


class UpdateCommandRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2048)
    slash_command: str | None = Field(default=None, pattern=r"^/[A-Za-z0-9_\-]+$")
    system_prompt_addendum: str | None = Field(default=None, min_length=1)
    enabled: bool | None = None
    status: str | None = Field(default=None, pattern=r"^(enabled|disabled|draft)$")


class CommandResponse(BaseModel):
    id: str
    code: str
    name: str
    description: str | None
    slash_command: str
    system_prompt_addendum: str
    enabled: bool
    owner_user_id: str
    visibility: str
    status: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, m) -> "CommandResponse":
        return cls(**{k: getattr(m, k) for k in cls.model_fields.keys()})


class CommandListResponse(BaseModel):
    total: int
    items: list[CommandResponse]


__all__ = ["CreateCommandRequest", "UpdateCommandRequest", "CommandResponse", "CommandListResponse"]
```

- [ ] **Step 4: 写 `agent.py` DTO**

```python
# src/hermetic_agent/store/dto/agent.py
from __future__ import annotations
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field, field_validator
import re

CODE_RE = r"^[A-Za-z0-9_\-.]+$"


def _normalize_codes(v: list[str]) -> list[str]:
    for item in v:
        if not re.match(CODE_RE, item):
            raise ValueError(f"invalid code in list: {item!r}")
    return v


class CreateAgentRequest(BaseModel):
    code: str = Field(min_length=1, max_length=128, pattern=CODE_RE)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2048)
    system_prompt: str = Field(default="")
    model: str = Field(default="openai/gpt-4o-mini", max_length=128)
    tool_level: str = Field(default="standard", pattern=r"^(safe|standard|full)$")
    network: str = Field(default="local", pattern=r"^(off|local|any)$")
    skill_codes: list[str] = Field(default_factory=list, max_length=32)
    mcp_server_codes: list[str] = Field(default_factory=list, max_length=32)
    prompt_codes: list[str] = Field(default_factory=list, max_length=32)
    command_codes: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("skill_codes", "mcp_server_codes", "prompt_codes", "command_codes")
    @classmethod
    def _check_codes(cls, v: list[str]) -> list[str]:
        return _normalize_codes(v)


class UpdateAgentRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    model: str | None = Field(default=None, max_length=128)
    tool_level: str | None = Field(default=None, pattern=r"^(safe|standard|full)$")
    network: str | None = Field(default=None, pattern=r"^(off|local|any)$")
    skill_codes: list[str] | None = Field(default=None, max_length=32)
    mcp_server_codes: list[str] | None = Field(default=None, max_length=32)
    prompt_codes: list[str] | None = Field(default=None, max_length=32)
    command_codes: list[str] | None = Field(default=None, max_length=32)
    status: str | None = None


class AgentResponse(BaseModel):
    id: str
    code: str
    name: str
    description: str | None
    system_prompt: str
    model: str
    tool_level: str
    network: str
    skill_codes: list[str]
    mcp_server_codes: list[str]
    prompt_codes: list[str]
    command_codes: list[str]
    owner_user_id: str
    visibility: str
    status: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, m) -> "AgentResponse":
        return cls(**{k: getattr(m, k) for k in cls.model_fields.keys()})


class AgentListResponse(BaseModel):
    total: int
    items: list[AgentResponse]


__all__ = ["CreateAgentRequest", "UpdateAgentRequest", "AgentResponse", "AgentListResponse"]
```

- [ ] **Step 5: 写失败 service 测试（以 PromptService 为例）**

```python
# tests/test_prompt_service_crud.py
import uuid
import pytest

from hermetic_agent.store.dto._common import ActorContext
from hermetic_agent.store.dto.prompt import CreatePromptRequest, UpdatePromptRequest
from hermetic_agent.store.services.audit_log_service import AuditLogService
from hermetic_agent.store.repositories.memory.audit_log_repo_memory import MemoryAuditLogRepository
from hermetic_agent.store.repositories.memory.prompt_repo_memory import MemoryPromptRepository
from hermetic_agent.store.services.prompt_service import PromptService
from hermetic_agent.store.exceptions import DuplicateError, NotFoundError, PolicyError


@pytest.fixture
def svc():
    repo = MemoryPromptRepository()
    audit = AuditLogService(MemoryAuditLogRepository())
    return PromptService(repo, audit)


@pytest.mark.asyncio
async def test_create_ok(svc):
    actor = ActorContext(user_id="alice")
    p = await svc.create(CreatePromptRequest(
        code="hi", name="hi", description="d", content="c"), actor=actor)
    assert p.owner_user_id == "alice"
    assert p.visibility == "private"


@pytest.mark.asyncio
async def test_create_duplicate_raises(svc):
    actor = ActorContext(user_id="alice")
    await svc.create(CreatePromptRequest(code="hi", name="x", content="c"), actor=actor)
    with pytest.raises(DuplicateError):
        await svc.create(CreatePromptRequest(code="hi", name="y", content="d"), actor=actor)


@pytest.mark.asyncio
async def test_update_owner_only(svc):
    a, b = ActorContext(user_id="alice"), ActorContext(user_id="bob")
    p = await svc.create(CreatePromptRequest(code="x", name="x", content="c"), actor=a)
    with pytest.raises(PolicyError):
        await svc.update(str(p.id), UpdatePromptRequest(name="evil"), actor=b)
    updated = await svc.update(str(p.id), UpdatePromptRequest(name="good"), actor=a)
    assert updated.name == "good"


@pytest.mark.asyncio
async def test_set_visibility_and_list_visible(svc):
    a, b = ActorContext(user_id="alice"), ActorContext(user_id="bob")
    p = await svc.create(CreatePromptRequest(code="x", name="x", content="c"), actor=a)
    pub = await svc.set_visibility(str(p.id), "public", actor=a)
    assert pub.visibility == "public"
    items = await svc.list(actor=b, limit=50, offset=0)
    assert any(x.id == p.id for x in items)
    assert (await svc.set_visibility(str(p.id), "private", actor=b)) is None
```

- [ ] **Step 6: 跑测试验证失败**

Run: `pytest tests/test_prompt_service_crud.py -v` — FAIL（service 不存在）

- [ ] **Step 7: 写 `PromptService`**

```python
# src/hermetic_agent/store/services/prompt_service.py
from __future__ import annotations
import uuid

import structlog

from hermetic_agent.store.dto._common import ActorContext
from hermetic_agent.store.dto.prompt import (
    CreatePromptRequest, PromptResponse, UpdatePromptRequest,
)
from hermetic_agent.store.exceptions import DuplicateError, NotFoundError, PolicyError
from hermetic_agent.store.models.prompt import Prompt
from hermetic_agent.store.repositories.prompt_repo import PromptRepository
from hermetic_agent.store.services.audit_log_service import AuditLogService

logger = structlog.get_logger(__name__)


class PromptService:
    def __init__(self, repo: PromptRepository, audit: AuditLogService) -> None:
        self._repo = repo
        self._audit = audit

    async def get_by_id(self, prompt_id: str) -> Prompt:
        p = await self._repo.get_by_id(prompt_id)
        if p is None:
            raise NotFoundError("prompt", prompt_id)
        return p

    async def get_by_code(self, code: str) -> Prompt:
        p = await self._repo.get_by_code(code)
        if p is None:
            raise NotFoundError("prompt", code)
        return p

    async def list(self, *, actor: ActorContext, limit=50, offset=0,
                   code=None, status=None) -> list[Prompt]:
        return await self._repo.list_visible_to(
            actor_user_id=actor.user_id, limit=limit, offset=offset,
            code=code, status=status)

    async def list_public(self, *, limit=50, offset=0, code=None) -> list[Prompt]:
        return await self._repo.list_public(limit=limit, offset=offset, code=code)

    async def create(self, req: CreatePromptRequest, *,
                    actor: ActorContext) -> Prompt:
        existing = await self._repo.get_by_code(req.code)
        if existing is not None:
            raise DuplicateError(f"prompt {req.code} already exists: {existing.id}")
        p = Prompt(
            id=uuid.uuid4(),
            code=req.code, name=req.name, version=req.version,
            description=req.description, content=req.content,
            owner_user_id=actor.user_id,
            visibility="private", status="enabled",
        )
        await self._repo.create(p)
        await self._audit.record(
            actor_type="user", actor_id=actor.user_id,
            action="create", resource_type="prompt",
            resource_id=str(p.id),
            after_data={"code": p.code, "name": p.name})
        return p

    async def update(self, prompt_id: str, req: UpdatePromptRequest, *,
                     actor: ActorContext) -> Prompt:
        p = await self.get_by_id(prompt_id)
        if p.owner_user_id != actor.user_id:
            raise PolicyError("FORBIDDEN", detail="non-owner cannot update prompt")
        fields = {k: getattr(req, k) for k in (
            "name", "description", "content", "status") if getattr(req, k) is not None}
        if not fields:
            return p
        before = {"name": p.name, "status": p.status}
        updated = await self._repo.update(prompt_id, **fields)
        if updated is None:
            raise NotFoundError("prompt", prompt_id)
        await self._audit.record(
            actor_type="user", actor_id=actor.user_id,
            action="update", resource_type="prompt",
            resource_id=prompt_id,
            before_data=before, after_data=fields)
        return updated

    async def set_visibility(self, prompt_id: str, visibility: str,
                             *, actor: ActorContext) -> Prompt | None:
        return await self._repo.set_visibility(
            prompt_id, visibility=visibility, actor_user_id=actor.user_id)

    async def soft_delete(self, prompt_id: str, *, actor: ActorContext) -> None:
        p = await self.get_by_id(prompt_id)
        await self._repo.soft_delete(prompt_id)
        await self._audit.record(
            actor_type="user", actor_id=actor.user_id,
            action="delete", resource_type="prompt",
            resource_id=prompt_id,
            before_data={"code": p.code})

    @staticmethod
    def to_response(p: Prompt) -> PromptResponse:
        return PromptResponse.from_model(p)


__all__ = ["PromptService"]
```

- [ ] **Step 8: 镜像实现 `CommandService` + `AgentService`**

`CommandService` 与 `PromptService` 同形，**唯一差异**：`create` 多查 `get_by_slash(req.slash_command)`，命中即 `DuplicateError`；update 接受 `slash_command / system_prompt_addendum / enabled`；model 换为 `Command`；DTO 换为 `CreateCommandRequest` 等。

`AgentService` 与 `PromptService` 同形，并加 `resolve_for_chat` 方法：

```python
# src/hermetic_agent/store/services/agent_service.py 末尾（除 CRUD 方法外）追加:
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from hermetic_agent.store.models.skill import Skill
from hermetic_agent.store.models.mcp_config import McpConfig

if TYPE_CHECKING:
    from hermetic_agent.store.services.skill_service import SkillService
    from hermetic_agent.store.services.mcp_config_service import McpConfigService
    from hermetic_agent.store.services.prompt_service import PromptService
    from hermetic_agent.store.services.command_service import CommandService


@dataclass
class ResolvedAgent:
    """chat 时 Agent + 解析后的引用列表 + warnings."""
    agent: "Agent"
    system_prompt: str
    model: str
    tool_level: str
    network: str
    skill_codes: list[str]
    mcp_server_codes: list[str]
    prompt_codes: list[str]
    command_codes: list[str]
    resolved_skills: list["Skill"] = field(default_factory=list)
    resolved_mcps: list["McpConfig"] = field(default_factory=list)
    resolved_prompts: list["Prompt"] = field(default_factory=list)
    resolved_commands: list["Command"] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class AgentService:
    def __init__(self, repo, audit, *, skill_service, mcp_config_service,
                 prompt_service, command_service) -> None:
        self._repo = repo
        self._audit = audit
        self._skill_service = skill_service
        self._mcp_service = mcp_config_service
        self._prompt_service = prompt_service
        self._command_service = command_service

    # ... 同样实现 create / update / soft_delete / set_visibility / list / list_public
    # 本任务关注点: resolve_for_chat
    async def resolve_for_chat(self, *, actor: ActorContext, agent_code: str) -> ResolvedAgent | None:
        a = await self._repo.get_by_code(agent_code)
        if a is None or a.is_deleted or a.status != "enabled":
            return None
        warnings: list[str] = []
        skills: list[Skill] = []
        for code in (a.skill_codes or []):
            try:
                s = await self._skill_service.get_by_code(code)
            except NotFoundError:
                warnings.append(f"skill {code!r} missing")
                continue
            if s.owner_user_id != actor.user_id and s.visibility != "public":
                warnings.append(f"skill {code!r} not visible to actor")
                continue
            if s.status != "enabled":
                warnings.append(f"skill {code!r} disabled")
                continue
            skills.append(s)
        mcp_servers: list[McpConfig] = []
        for code in (a.mcp_server_codes or []):
            try:
                m = await self._mcp_service.get_by_code(code)
            except NotFoundError:
                warnings.append(f"mcp {code!r} missing")
                continue
            if m.owner_user_id != actor.user_id and m.visibility != "public":
                warnings.append(f"mcp {code!r} not visible to actor")
                continue
            mcp_servers.append(m)
        prompts: list[Prompt] = []
        for code in (a.prompt_codes or []):
            try:
                p = await self._prompt_service.get_by_code(code)
            except NotFoundError:
                warnings.append(f"prompt {code!r} missing")
                continue
            if p.owner_user_id != actor.user_id and p.visibility != "public":
                warnings.append(f"prompt {code!r} not visible to actor")
                continue
            prompts.append(p)
        commands: list[Command] = []
        for code in (a.command_codes or []):
            try:
                c = await self._command_service.get_by_code(code)
            except NotFoundError:
                warnings.append(f"command {code!r} missing")
                continue
            if c.owner_user_id != actor.user_id and c.visibility != "public":
                warnings.append(f"command {code!r} not visible to actor")
                continue
            commands.append(c)
        return ResolvedAgent(
            agent=a,
            system_prompt=a.system_prompt, model=a.model,
            tool_level=a.tool_level, network=a.network,
            skill_codes=[s.code for s in skills],
            mcp_server_codes=[m.code for m in mcp_servers],
            prompt_codes=[p.code for p in prompts],
            command_codes=[c.code for c in commands],
            resolved_skills=skills, resolved_mcps=mcp_servers,
            resolved_prompts=prompts, resolved_commands=commands,
            warnings=warnings,
        )
```

写对应测试：
- `tests/test_command_service_crud.py`：4 个用例（创建、重复 reject、`/x` 重复 reject、visibility 非 owner 拒）
- `tests/test_agent_service_crud.py`：3 个用例（创建 owner-private、resolve_for_chat miss 返 None、resolve_for_chat 过滤 owner-private skill）

- [ ] **Step 9: 跑所有 service 测试**

```bash
pytest tests/test_prompt_service_crud.py tests/test_command_service_crud.py tests/test_agent_service_crud.py -v
# 全部 passed
```

- [ ] **Step 10: 接线到 `ServiceContainer`**

```python
# src/hermetic_agent/store/services/container.py 修改:
from hermetic_agent.store.services.agent_service import AgentService
from hermetic_agent.store.services.prompt_service import PromptService
from hermetic_agent.store.services.command_service import CommandService


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
    prompt: PromptService
    command: CommandService
    agent: AgentService

    @property
    def prompt_service(self): return self.prompt
    @property
    def command_service(self): return self.command
    @property
    def agent_service(self): return self.agent


def build_container(
    *, scenario_repo, session_repo, chat_turn_repo,
    message_repo, part_repo, audit_log_repo,
    skill_repo, mcp_config_repo,
    prompt_repo, command_repo, agent_repo,   # 新增
):
    audit = AuditLogService(audit_log_repo)
    session = SessionService(session_repo, audit)
    scenario = ScenarioService(scenario_repo, audit)
    chat_turn = ChatTurnService(chat_turn_repo, audit, session)
    message = MessageService(message_repo, part_repo, audit, session)
    part = PartService(part_repo, audit)
    skill = SkillService(skill_repo, audit)
    mcp_config = McpConfigService(mcp_config_repo, audit)
    prompt = PromptService(prompt_repo, audit)
    command = CommandService(command_repo, audit)
    agent = AgentService(
        agent_repo, audit,
        skill_service=skill, mcp_config_service=mcp_config,
        prompt_service=prompt, command_service=command,
    )
    return ServiceContainer(
        audit_log=audit, scenario=scenario, session=session,
        chat_turn=chat_turn, message=message, part=part,
        skill=skill, mcp_config=mcp_config,
        prompt=prompt, command=command, agent=agent,
    )


async def build_container_from_settings(settings, ddl_sql=None):
    from hermetic_agent.store.models._common import init_tortoise
    from hermetic_agent.store.repositories.memory import (
        MemoryPromptRepository, MemoryCommandRepository, MemoryAgentRepository,
        MemorySkillRepository, MemoryMcpConfigRepository,
        MemoryAuditLogRepository, MemoryChatTurnRepository,
        MemoryMessageRepository, MemoryPartRepository,
        MemoryScenarioRepository, MemorySessionRepository,
    )
    from hermetic_agent.store.repositories.mysql import (
        MySQLPromptRepository, MySQLCommandRepository, MySQLAgentRepository,
        MySQLSkillRepository, MySQLMcpConfigRepository,
        MySQLAuditLogRepository, MySQLChatTurnRepository,
        MySQLMessageRepository, MySQLPartRepository,
        MySQLScenarioRepository, MySQLSessionRepository,
    )

    backend = getattr(settings, "storage_backend", "memory").lower()
    if backend == "memory":
        return build_container(
            ...,
            skill_repo=MemorySkillRepository(),
            mcp_config_repo=MemoryMcpConfigRepository(),
            prompt_repo=MemoryPromptRepository(),
            command_repo=MemoryCommandRepository(),
            agent_repo=MemoryAgentRepository(),
        )
    if backend == "mysql":
        await init_tortoise(getattr(settings, "mysql_dsn", "..."))
        return build_container(
            ...,
            skill_repo=MySQLSkillRepository(),
            mcp_config_repo=MySQLMcpConfigRepository(),
            prompt_repo=MySQLPromptRepository(),
            command_repo=MySQLCommandRepository(),
            agent_repo=MySQLAgentRepository(),
        )
    raise ValueError(...)
```

- [ ] **Step 11: 跑既有测试确认无回退**

```bash
pytest -v  # 全部既有测试 + 本任务测试
```

- [ ] **Step 12: 提交**

```bash
git add src/hermetic_agent/store/dto/_common.py \
        src/hermetic_agent/store/dto/__init__.py \
        src/hermetic_agent/store/dto/{prompt,command,agent}.py \
        src/hermetic_agent/store/services/prompt_service.py \
        src/hermetic_agent/store/services/command_service.py \
        src/hermetic_agent/store/services/agent_service.py \
        src/hermetic_agent/store/services/container.py \
        src/hermetic_agent/store/services/__init__.py \
        tests/test_prompt_service_crud.py \
        tests/test_command_service_crud.py \
        tests/test_agent_service_crud.py
git commit -m "feat(store): add 3 services (Prompt/Command/Agent) + DTO + ServiceContainer wiring"
```

---

## Task 7: ActorContextMiddleware（L1）

**Files:**
- 新建：`src/hermetic_agent/api/http/middleware/actor_context.py`
- 修改：`src/hermetic_agent/api/app/app.py`（注册 middleware）
- 新建：`tests/test_actor_context_middleware.py`

**Interfaces:** Sanic 中间件，从 headers 写入 `request.ctx.actor = ActorContext`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_actor_context_middleware.py
import pytest
from sanic import Sanic
from sanic.response import JSONResponse

from hermetic_agent.api.http.middleware.actor_context import ActorContextMiddleware
from hermetic_agent.store.dto._common import ActorContext


@pytest.mark.asyncio
async def test_middleware_extracts_user_id_header():
    app = Sanic("test_actor_mw")
    seen: list[ActorContext] = []

    @app.get("/probe")
    async def probe(request):
        seen.append(request.ctx.actor)
        return JSONResponse({"ok": True})

    ActorContextMiddleware(app)
    _, response = await app.asgi_client.get("/probe", headers={"X-User-Id": "alice"})
    assert response.status == 200
    assert seen[0].user_id == "alice"
    assert seen[0].is_anonymous() is False


@pytest.mark.asyncio
async def test_anonymous_when_no_header():
    app = Sanic("test_actor_mw_anon")
    seen: list[ActorContext] = []

    @app.get("/probe")
    async def probe(request):
        seen.append(request.ctx.actor)
        return JSONResponse({"ok": True})

    ActorContextMiddleware(app)
    _, response = await app.asgi_client.get("/probe")
    assert seen[0].user_id == "anonymous"
    assert seen[0].is_anonymous()
```

- [ ] **Step 2: 跑测试验证失败**

Run: `pytest tests/test_actor_context_middleware.py -v` — FAIL（middleware 不存在）

- [ ] **Step 3: 写 `ActorContextMiddleware`**

```python
# src/hermetic_agent/api/http/middleware/actor_context.py
from __future__ import annotations

from sanic import Sanic
from sanic.request import Request

from hermetic_agent.store.dto._common import ActorContext


class ActorContextMiddleware:
    HEADER_USER_ID = "X-User-Id"
    HEADER_TENANT_ID = "X-Tenant-Id"
    HEADER_ROLES = "X-Roles"
    HEADER_AUTH = "Authorization"

    def __init__(self, app: Sanic) -> None:
        app.register_middleware(self, "request")

    async def __call__(self, request: Request) -> None:
        user_id = request.headers.get(self.HEADER_USER_ID)
        if user_id is None:
            auth = request.headers.get(self.HEADER_AUTH, "")
            if auth.lower().startswith("bearer "):
                # 简化: 用 token 作为 user_id（生产应校验 JWT 签名后取 sub claim）
                user_id = auth.split(" ", 1)[1].strip() or None
        if user_id is None:
            user_id = "anonymous"
        tenant_id = request.headers.get(self.HEADER_TENANT_ID)
        roles_header = request.headers.get(self.HEADER_ROLES, "")
        roles = [r for r in roles_header.split(",") if r.strip()] if roles_header else []
        request.ctx.actor = ActorContext(
            user_id=user_id, tenant_id=tenant_id, roles=roles)


__all__ = ["ActorContextMiddleware"]
```

- [ ] **Step 4: 在 `app.py` 注册**

打开 `src/hermetic_agent/api/app/app.py`，在 `register_all_blueprints(app)` 之后（**但仍在 `_install_error_handler(app)` 之前**）插入：

```python
from hermetic_agent.api.http.middleware.actor_context import ActorContextMiddleware
ActorContextMiddleware(app)
```

- [ ] **Step 5: 跑测试**

Run: `pytest tests/test_actor_context_middleware.py -v` — 2 passed

- [ ] **Step 6: 提交**

```bash
git add src/hermetic_agent/api/http/middleware/actor_context.py \
        src/hermetic_agent/api/app/app.py \
        tests/test_actor_context_middleware.py
git commit -m "feat(api): add ActorContextMiddleware that extracts user from headers"
```

---

## Task 8: 三个 Controller + Blueprint 注册（L1）

**Files:**
- 新建：`src/hermetic_agent/api/http/controllers/prompts_controller.py`
- 新建：`src/hermetic_agent/api/http/controllers/commands_controller.py`
- 新建：`src/hermetic_agent/api/http/controllers/agents_controller.py`
- 修改：`src/hermetic_agent/api/app/blueprint_registry.py`
- 新建：`tests/test_{prompts,commands,agents}_controller_endpoint.py`

**Interfaces:** 7 个端点 × 3 blueprint，复用 `_container()` + `_err()` + `_actor()` 三个 helper。代码模板见 spec §4 和 Phase 1 控制器模式。

- [ ] **Step 1: 写 `prompts_controller.py`**

```python
# src/hermetic_agent/api/http/controllers/prompts_controller.py
from __future__ import annotations
import structlog
from sanic import Blueprint
from sanic.request import Request
from sanic.response import JSONResponse
from sanic_ext import openapi as sanic_openapi

from hermetic_agent.store.dto._common import ActorContext
from hermetic_agent.store.dto.prompt import (
    CreatePromptRequest, UpdatePromptRequest,
)
from hermetic_agent.store.exceptions import DuplicateError, NotFoundError, PolicyError

logger = structlog.get_logger(__name__)
doc_summary = sanic_openapi.summary
doc_tag = sanic_openapi.tag
prompt_bp = Blueprint("prompts", url_prefix="/agent/prompts")


def _container(request):
    return request.app.ctx.service_container


def _err(code, message, status=400):
    return JSONResponse(
        {"success": False, "code": code, "error": message}, status=status)


def _actor(request):
    return getattr(request.ctx, "actor", ActorContext(user_id="anonymous"))


@prompt_bp.get("/")
@doc_summary("List prompts (own + public)")
@doc_tag("Prompts")
async def list_prompts(request):
    c = _container(request)
    items = await c.prompt.list(
        actor=_actor(request),
        limit=int(request.args.get("limit", "50")),
        offset=int(request.args.get("offset", "0")),
        code=request.args.get("code"),
        status=request.args.get("status"))
    return JSONResponse({
        "total": len(items),
        "items": [c.prompt.to_response(p).model_dump(mode="json") for p in items],
    })


@prompt_bp.get("/community")
@doc_summary("List public prompts only")
@doc_tag("Prompts")
async def list_public_prompts(request):
    c = _container(request)
    items = await c.prompt.list_public(
        limit=int(request.args.get("limit", "50")),
        offset=int(request.args.get("offset", "0")),
        code=request.args.get("code"))
    return JSONResponse({
        "total": len(items),
        "items": [c.prompt.to_response(p).model_dump(mode="json") for p in items],
    })


@prompt_bp.get("/<code>")
@doc_summary("Get a prompt by code")
@doc_tag("Prompts")
async def get_prompt(request, code):
    c = _container(request)
    try:
        p = await c.prompt.get_by_code(code)
    except NotFoundError:
        return _err("PROMPT_NOT_FOUND", f"prompt {code!r} not found", status=404)
    return JSONResponse(c.prompt.to_response(p).model_dump(mode="json"))


@prompt_bp.post("/")
@doc_summary("Create a prompt")
@doc_tag("Prompts")
async def create_prompt(request):
    c = _container(request)
    try:
        req = CreatePromptRequest(**(request.json or {}))
    except Exception as e:
        return _err("VALIDATION_FAILED", f"Invalid body: {e}")
    try:
        p = await c.prompt.create(req, actor=_actor(request))
    except DuplicateError as e:
        return _err("DUPLICATE_PROMPT", str(e), status=409)
    return JSONResponse(c.prompt.to_response(p).model_dump(mode="json"), status=201)


@prompt_bp.put("/<code>")
@doc_summary("Update a prompt")
@doc_tag("Prompts")
async def update_prompt(request, code):
    c = _container(request)
    try:
        req = UpdatePromptRequest(**(request.json or {}))
    except Exception as e:
        return _err("VALIDATION_FAILED", f"Invalid body: {e}")
    try:
        p = await c.prompt.get_by_code(code)
    except NotFoundError:
        return _err("PROMPT_NOT_FOUND", f"prompt {code!r} not found", status=404)
    try:
        u = await c.prompt.update(str(p.id), req, actor=_actor(request))
    except PolicyError as e:
        return _err("FORBIDDEN", e.detail, status=403)
    return JSONResponse(c.prompt.to_response(u).model_dump(mode="json"))


@prompt_bp.delete("/<code>")
@doc_summary("Soft-delete a prompt")
@doc_tag("Prompts")
async def delete_prompt(request, code):
    c = _container(request)
    try:
        p = await c.prompt.get_by_code(code)
    except NotFoundError:
        return _err("PROMPT_NOT_FOUND", f"prompt {code!r} not found", status=404)
    await c.prompt.soft_delete(str(p.id), actor=_actor(request))
    return JSONResponse({"success": True, "code": code})


@prompt_bp.post("/<code>/publish")
@doc_summary("Toggle visibility (owner-only)")
@doc_tag("Prompts")
async def publish_prompt(request, code):
    c = _container(request)
    body = request.json or {}
    visibility = body.get("visibility")
    if visibility not in ("private", "public"):
        return _err("VALIDATION_FAILED", "visibility must be 'private' or 'public'")
    try:
        p = await c.prompt.get_by_code(code)
    except NotFoundError:
        return _err("PROMPT_NOT_FOUND", f"prompt {code!r} not found", status=404)
    out = await c.prompt.set_visibility(
        str(p.id), visibility, actor=_actor(request))
    if out is None:
        return _err("FORBIDDEN", "only owner can change visibility", status=403)
    return JSONResponse(c.prompt.to_response(out).model_dump(mode="json"))


__all__ = ["prompt_bp"]
```

- [ ] **Step 2: 镜像实现 `commands_controller.py` + `agents_controller.py`**

`commands_controller.py`：与 prompts 同形态，model/DTO/字段替为 command 体系。`/community`、`POST /<code>/publish` 同形。约 150 LOC。

`agents_controller.py`：与 prompts 同形态，DTO 多 4 个 *_codes + system_prompt + model + tool_level + network 字段。约 155 LOC。**所有 3 个 controller 均 ≤ 200 LOC**，符合约束。

- [ ] **Step 3: 写 controller 测试（Prompts 完整，Commands/Agents 镜像）**

```python
# tests/test_prompts_controller_endpoint.py
import pytest
from sanic import Sanic

from hermetic_agent.api.http.controllers.prompts_controller import prompt_bp
from hermetic_agent.store.dto._common import ActorContext
from hermetic_agent.store.services.audit_log_service import AuditLogService
from hermetic_agent.store.repositories.memory.audit_log_repo_memory import MemoryAuditLogRepository
from hermetic_agent.store.repositories.memory.prompt_repo_memory import MemoryPromptRepository
from hermetic_agent.store.services.prompt_service import PromptService


@pytest.fixture
def container():
    return type("C", (), {})()  # 占位; 实际 fixture 需替换


@pytest.fixture
async def app():
    app = Sanic("test_prompts_app")
    app.blueprint(prompt_bp)
    audit = AuditLogService(MemoryAuditLogRepository())
    repo = MemoryPromptRepository()
    svc = PromptService(repo, audit)

    class C: pass
    c = C()
    c.prompt = svc

    app.ctx.service_container = c

    async def fake_actor_mw(request):
        from hermetic_agent.store.dto._common import ActorContext
        request.ctx.actor = ActorContext(
            user_id=request.headers.get("X-User-Id", "anonymous"))
    app.register_middleware(fake_actor_mw, "request")
    return app


@pytest.mark.asyncio
async def test_create_then_get_prompt(app):
    client = app.asgi_client
    _, r = await client.post("/agent/prompts/", json={
        "code": "hi", "name": "Hi", "description": "test", "content": "say hi",
    }, headers={"X-User-Id": "alice"})
    assert r.status == 201
    assert r.json["owner_user_id"] == "alice"
    _, r2 = await client.get("/agent/prompts/hi")
    assert r2.status == 200
    assert r2.json["content"] == "say hi"


@pytest.mark.asyncio
async def test_publish_makes_visible_to_others(app):
    client = app.asgi_client
    _, r = await client.post("/agent/prompts/", json={
        "code": "shared", "name": "S", "content": "c",
    }, headers={"X-User-Id": "alice"})
    pid = r.json["id"]
    _, r2 = await client.post(
        f"/agent/prompts/shared/publish",
        json={"visibility": "public"},
        headers={"X-User-Id": "alice"},
    )
    assert r2.status == 200
    # bob 现在能看到
    _, r3 = await client.get(
        "/agent/prompts/", headers={"X-User-Id": "bob"})
    codes = [p["code"] for p in r3.json["items"]]
    assert "shared" in codes


@pytest.mark.asyncio
async def test_publish_denies_non_owner(app):
    client = app.asgi_client
    await client.post("/agent/prompts/", json={
        "code": "private-x", "name": "P", "content": "c",
    }, headers={"X-User-Id": "alice"})
    _, r = await client.post(
        "/agent/prompts/private-x/publish",
        json={"visibility": "public"},
        headers={"X-User-Id": "bob"},
    )
    assert r.status == 403
```

- [ ] **Step 4: 跑 controller 测试 + 注册 BP**

```python
# src/hermetic_agent/api/app/blueprint_registry.py
from hermetic_agent.api.http.controllers.agents_controller import agent_bp
from hermetic_agent.api.http.controllers.commands_controller import command_bp
from hermetic_agent.api.http.controllers.prompts_controller import prompt_bp

# 在 register_all_blueprints 末尾添加:
app.blueprint(prompt_bp)
app.blueprint(command_bp)
app.blueprint(agent_bp)
```

- [ ] **Step 5: 跑所有 controller 测试**

```bash
pytest tests/test_prompts_controller_endpoint.py \
       tests/test_commands_controller_endpoint.py \
       tests/test_agents_controller_endpoint.py -v
```

- [ ] **Step 6: 提交**

```bash
git add src/hermetic_agent/api/http/controllers/prompts_controller.py \
        src/hermetic_agent/api/http/controllers/commands_controller.py \
        src/hermetic_agent/api/http/controllers/agents_controller.py \
        src/hermetic_agent/api/app/blueprint_registry.py \
        tests/test_prompts_controller_endpoint.py \
        tests/test_commands_controller_endpoint.py \
        tests/test_agents_controller_endpoint.py
git commit -m "feat(api): add 3 controllers (prompts/commands/agents) + register BPs"
```

---

## Task 9: 扩展 SkillService + McpConfigService 加 visibility 路径（L5）

**Files:**
- 修改：`src/hermetic_agent/store/services/skill_service.py`
- 修改：`src/hermetic_agent/store/services/mcp_config_service.py`
- 新建：`tests/test_skill_service_visibility.py`、`test_mcp_config_service_visibility.py`

**Interfaces:** 服务层加 3 个方法: `list / list_public / set_visibility`，包装 repo。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_skill_service_visibility.py
import uuid
import pytest

from hermetic_agent.store.dto._common import ActorContext
from hermetic_agent.store.models.skill import Skill
from hermetic_agent.store.repositories.memory.audit_log_repo_memory import MemoryAuditLogRepository
from hermetic_agent.store.repositories.memory.skill_repo_memory import MemorySkillRepository
from hermetic_agent.store.services.audit_log_service import AuditLogService
from hermetic_agent.store.services.skill_service import SkillService


def test_skill_service_list_visible_only_returns_owner_and_public():
    repo = MemorySkillRepository()
    audit = AuditLogService(MemoryAuditLogRepository())
    svc = SkillService(repo, audit)

    pub = Skill(id=uuid.uuid4(), code="pub", name="P",
                 owner_user_id="bob", visibility="public", status="enabled",
                 description="", version=1)
    priv = Skill(id=uuid.uuid4(), code="priv", name="P",
                  owner_user_id="bob", visibility="private", status="enabled",
                  description="", version=1)
    repo._store[pub.id] = pub
    repo._store[priv.id] = priv

    alice = ActorContext(user_id="alice")
    import asyncio
    items = asyncio.get_event_loop().run_until_complete(
        svc.list(actor=alice, limit=10, offset=0))
    assert {s.code for s in items} == {"pub"}


@pytest.mark.asyncio
async def test_skill_service_set_visibility_owner_only():
    repo = MemorySkillRepository()
    audit = AuditLogService(MemoryAuditLogRepository())
    svc = SkillService(repo, audit)
    a, b = ActorContext(user_id="alice"), ActorContext(user_id="bob")
    s = Skill(id=uuid.uuid4(), code="x", name="X", owner_user_id="alice",
              visibility="private", status="enabled",
              description="", version=1)
    repo._store[s.id] = s
    assert (await svc.set_visibility(str(s.id), "public", actor=b)) is None
    assert (await svc.set_visibility(str(s.id), "public", actor=a)).visibility == "public"
```

- [ ] **Step 2: 跑测试验证失败**

Run: `pytest tests/test_skill_service_visibility.py -v` — FAIL（`list` 不存在）

- [ ] **Step 3: 扩展 `SkillService`**

```python
# src/hermetic_agent/store/services/skill_service.py 末尾追加:
async def list(self, *, actor: ActorContext, limit=50, offset=0,
               code=None, status=None) -> list[Skill]:
    return await self._repo.list_visible_to(
        actor_user_id=actor.user_id, limit=limit, offset=offset,
        code=code, status=status)

async def list_public(self, *, limit=50, offset=0, code=None) -> list[Skill]:
    return await self._repo.list_public(limit=limit, offset=offset, code=code)

async def set_visibility(self, skill_id: str, visibility: str, *,
                         actor: ActorContext) -> Skill | None:
    return await self._repo.set_visibility(
        skill_id, visibility=visibility, actor_user_id=actor.user_id)
```

`McpConfigService` 同形态（model 替为 `McpConfig`）。

- [ ] **Step 4: 跑所有测试**

```bash
pytest tests/test_skill_service_visibility.py tests/test_mcp_config_service_visibility.py -v
```

- [ ] **Step 5: 提交**

```bash
git add src/hermetic_agent/store/services/skill_service.py \
        src/hermetic_agent/store/services/mcp_config_service.py \
        tests/test_skill_service_visibility.py \
        tests/test_mcp_config_service_visibility.py
git commit -m "feat(services): extend Skill/McpConfig service with visibility methods"
```

---

> **继续阅读 `2026-06-30-asset-registry-plan-3.md`（Phase 2 MinIO 文件面 + Phase 3 chat 集成 + Phase 4 收口，Task 10–16）**。
