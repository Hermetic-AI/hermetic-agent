"""SkillRepository ABC — 技能仓储接口."""

from __future__ import annotations

from abc import abstractmethod

from hermetic_agent.store.models.skill import Skill
from hermetic_agent.store.repositories._base import Repository


class SkillRepository(Repository[Skill]):
    """技能仓储接口."""

    @abstractmethod
    async def get_by_code(self, code: str) -> Skill | None:
        """按业务编码查技能."""

    @abstractmethod
    async def list_active(self, *, limit: int = 100) -> list[Skill]:
        """列出 status=enabled 的技能(运行时注册表用)."""

    @abstractmethod
    async def list_visible_to(
        self,
        *,
        actor_user_id: str,
        limit: int = 50,
        offset: int = 0,
        code: str | None = None,
        status: str | None = None,
    ) -> list[Skill]:
        """列出对 actor 可见的技能 (own + 全部 public)."""

    @abstractmethod
    async def list_public(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        code: str | None = None,
    ) -> list[Skill]:
        """列出全部 public 技能."""

    @abstractmethod
    async def update_file_fingerprint(
        self,
        skill_id: str,
        *,
        file_count: int,
        file_fingerprint: str,
    ) -> Skill | None:
        """更新 file_count + file_fingerprint (MinIO 同步后回填)."""

    @abstractmethod
    async def set_visibility(
        self,
        skill_id: str,
        *,
        visibility: str,
        actor_user_id: str,
    ) -> Skill | None:
        """owner 切换 public/private; 非 owner 或不存在返回 None."""


__all__ = ["SkillRepository"]
