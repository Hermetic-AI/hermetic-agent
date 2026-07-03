"""Memory Repository 公共基类.

简化策略:
- 单 ID 操作(get_by_id / create / update / soft_delete / hard_delete) 放基类
- 列表 / 业务方法 留给子类(每个实体的 filter 字段不同)
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from hermetic_agent.store.models._common import utcnow
from hermetic_agent.store.repositories._base import Repository

M = TypeVar("M")


class MemoryRepository(Repository[M], Generic[M]):
    """内存版仓储公共基类.

    数据存在 ``self._store: dict[id, Model]``, 软删除标记 ``is_deleted`` 过滤.
    """

    def __init__(self) -> None:
        self._store: dict[str, M] = {}

    async def get_by_id(self, entity_id: str) -> M | None:
        # ID 兼容: Tortoise ``UUIDField`` 返回 ``uuid.UUID`` 对象, 但
        # ``mark_started`` / ``delete_session`` 之类业务方法传进来的是 ``str``.
        # 把两边都规范成 ``str`` 比较, 跟生产 MySQL 路径 (``CHAR(36)`` 存 str)
        # 行为一致.
        target = str(entity_id) if entity_id is not None else entity_id
        for k, m in self._store.items():
            if str(k) == target and not getattr(m, "is_deleted", False):
                return m
        return None

    async def get_by_id_including_deleted(self, entity_id: str) -> M | None:
        target = str(entity_id) if entity_id is not None else entity_id
        for k, m in self._store.items():
            if str(k) == target:
                return m
        return None

    async def create(self, model: M) -> M:
        eid = getattr(model, "id", None)
        if not eid:
            raise ValueError("Model must have id")
        now = utcnow()
        if hasattr(model, "created_at") and getattr(model, "created_at", None) is None:
            model.created_at = now
        if hasattr(model, "updated_at") and getattr(model, "updated_at", None) is None:
            model.updated_at = now
        self._store[str(eid)] = model
        return model

    async def update(self, entity_id: str, **fields: Any) -> M | None:
        m = self._store.get(entity_id)
        if m is None or getattr(m, "is_deleted", False):
            return None
        for k, v in fields.items():
            setattr(m, k, v)
        if hasattr(m, "updated_at"):
            m.updated_at = utcnow()
        return m

    async def soft_delete(self, entity_id: str) -> bool:
        m = self._store.get(entity_id)
        if m is None or getattr(m, "is_deleted", False):
            return False
        m.is_deleted = True
        m.deleted_at = utcnow()
        if hasattr(m, "updated_at"):
            m.updated_at = utcnow()
        return True

    async def hard_delete(self, entity_id: str) -> bool:
        return self._store.pop(entity_id, None) is not None

    # ---------- 子类需实现 ----------

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[M]:
        raise NotImplementedError

    async def count(
        self, *, include_deleted: bool = False, **filters: Any
    ) -> int:
        raise NotImplementedError

    # ---------- 测试辅助 ----------

    def clear(self) -> None:
        """清空所有数据(测试用)."""
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)
