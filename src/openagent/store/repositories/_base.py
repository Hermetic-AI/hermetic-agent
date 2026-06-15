"""Repository ABC 公共基类 + 通用类型.

每个实体一个 ABC (ScenarioRepository / SessionRepository / ...), 继承 ``Repository[M]``.
约定:
- ``get_by_id`` 返回 ``Model | None``, 不抛 NotFoundError (业务层决定要不要抛)
- ``list`` 默认按 ``updated_at DESC`` 或 ``created_at DESC`` 排序, ``limit`` 默认 50
- ``create(model)`` 接受完整 Model, 内部只负责 INSERT; id 已生成
- ``update(id, **fields)`` 接受要更新的字段, 内部生成 SQL
- ``soft_delete(id)`` 设 ``is_deleted=1, deleted_at=now``
- ``count(*, ...)`` 配合 list 用, 做分页
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

M = TypeVar("M")


class Repository(ABC, Generic[M]):
    """仓储抽象基类(所有实体 Repository 都继承本类)."""

    @abstractmethod
    async def get_by_id(self, entity_id: str) -> M | None:
        """按 ID 加载单实体. 软删除的默认不返回(include_deleted=False)."""

    @abstractmethod
    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[M]:
        """列表查询. filters 由子类定义(如 user_id=..., status=...)."""

    @abstractmethod
    async def count(self, *, include_deleted: bool = False, **filters: Any) -> int:
        """总数, 配合 list 做分页."""

    @abstractmethod
    async def create(self, model: M) -> M:
        """创建实体. id 由调用方或本方法内部生成."""

    @abstractmethod
    async def update(self, entity_id: str, **fields: Any) -> M | None:
        """按 ID 局部更新. 返回更新后的实体, 不存在返回 None."""

    @abstractmethod
    async def soft_delete(self, entity_id: str) -> bool:
        """软删除. 成功返回 True, 不存在返回 False."""

    @abstractmethod
    async def hard_delete(self, entity_id: str) -> bool:
        """物理删除(测试 / 后台清理用, 业务慎用)."""


__all__ = ["Repository"]
