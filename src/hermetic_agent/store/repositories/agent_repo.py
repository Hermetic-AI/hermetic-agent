"""AgentRepository ABC — Agent 资产仓储接口."""
from __future__ import annotations

from abc import abstractmethod
from typing import Any

from hermetic_agent.store.models.agent import Agent
from hermetic_agent.store.repositories._base import Repository


class AgentRepository(Repository[Agent]):
    """Agent 仓储抽象接口 (mirror Prompt, 11 个方法, 不含 get_by_slash)."""

    @abstractmethod
    async def get_by_id(self, agent_id: str) -> Agent | None:
        """按 ID 加载单个 Agent. 软删除的默认不返回."""

    @abstractmethod
    async def get_by_code(self, code: str) -> Agent | None:
        """按业务编码查 Agent."""

    @abstractmethod
    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        **filters: Any,
    ) -> list[Agent]:
        """列表查询, 默认按 updated_at DESC 排序."""

    @abstractmethod
    async def count(
        self, *, include_deleted: bool = False, **filters: Any,
    ) -> int:
        """总数, 配合 list 做分页."""

    @abstractmethod
    async def create(self, agent: Agent) -> Agent:
        """创建 Agent. id 由调用方或本方法内部生成."""

    @abstractmethod
    async def update(self, agent_id: str, **fields: Any) -> Agent | None:
        """按 ID 局部更新. 返回更新后的实体, 不存在返回 None."""

    @abstractmethod
    async def soft_delete(self, agent_id: str) -> bool:
        """软删除. 成功返回 True, 不存在或已删返回 False (幂等)."""

    @abstractmethod
    async def hard_delete(self, agent_id: str) -> bool:
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
    ) -> list[Agent]:
        """列出对 actor 可见的 Agent (own + 全部 public)."""

    @abstractmethod
    async def list_public(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        code: str | None = None,
    ) -> list[Agent]:
        """列出全部 public Agent."""

    @abstractmethod
    async def set_visibility(
        self,
        agent_id: str,
        *,
        visibility: str,
        actor_user_id: str,
    ) -> Agent | None:
        """owner 切换 public/private; 非 owner 或不存在返回 None."""


__all__ = ["AgentRepository"]
