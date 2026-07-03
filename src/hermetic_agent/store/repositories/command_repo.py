"""CommandRepository ABC — Command 资产仓储接口."""
from __future__ import annotations

from abc import abstractmethod
from typing import Any

from hermetic_agent.store.models.command import Command
from hermetic_agent.store.repositories._base import Repository


class CommandRepository(Repository[Command]):
    """Command 仓储抽象接口."""

    @abstractmethod
    async def get_by_id(self, command_id: str) -> Command | None:
        """按 ID 加载单个 Command. 软删除的默认不返回."""

    @abstractmethod
    async def get_by_code(self, code: str) -> Command | None:
        """按业务编码查 Command."""

    @abstractmethod
    async def get_by_slash(self, slash_command: str) -> Command | None:
        """按 slash 字符串 (例如 ``/summarize``) 查 Command. 用户输入路由时用."""

    @abstractmethod
    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[Command]:
        """列表查询, 默认按 updated_at DESC 排序."""

    @abstractmethod
    async def count(
        self, *, include_deleted: bool = False, **filters: Any,
    ) -> int:
        """总数, 配合 list 做分页."""

    @abstractmethod
    async def create(self, command: Command) -> Command:
        """创建 Command. id 由调用方或本方法内部生成."""

    @abstractmethod
    async def update(self, command_id: str, **fields: Any) -> Command | None:
        """按 ID 局部更新. 返回更新后的实体, 不存在返回 None."""

    @abstractmethod
    async def soft_delete(self, command_id: str) -> bool:
        """软删除. 成功返回 True, 不存在或已删返回 False (幂等)."""

    @abstractmethod
    async def hard_delete(self, command_id: str) -> bool:
        """物理删除 (测试 / 后台清理用, 业务慎用)."""

    @abstractmethod
    async def list_visible_to(
        self,
        *,
        actor_user_id: str,
        limit: int = 50,
        offset: int = 0,
        code: str | None = None,
        status: str | None = None,
    ) -> list[Command]:
        """列出对 actor 可见的 Command (own + 全部 public)."""

    @abstractmethod
    async def list_public(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        code: str | None = None,
    ) -> list[Command]:
        """列出全部 public Command."""

    @abstractmethod
    async def set_visibility(
        self,
        command_id: str,
        *,
        visibility: str,
        actor_user_id: str,
    ) -> Command | None:
        """owner 切换 public/private; 非 owner 或不存在返回 None."""


__all__ = ["CommandRepository"]
