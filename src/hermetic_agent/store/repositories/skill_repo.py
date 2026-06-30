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


__all__ = ["SkillRepository"]
