"""ScenarioRepository ABC — 场景仓储接口."""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from openagent.store.models.scenario import Scenario
from openagent.store.repositories._base import Repository


class ScenarioRepository(Repository[Scenario]):
    """场景仓储接口."""

    @abstractmethod
    async def get_by_code_version(self, code: str, version: int) -> Scenario | None:
        """按 ``(code, version)`` 查场景(应用层唯一约束检查)."""

    @abstractmethod
    async def list_active(self, *, limit: int = 100) -> list[Scenario]:
        """列出 status=enabled 的场景(运行时注册表用)."""

    @abstractmethod
    async def create_new_version(
        self, parent: Scenario, new_config: dict[str, Any], new_name: str | None = None
    ) -> Scenario:
        """基于父版本创建新版本(自动 parent_id + version+1 + 同 code).

        业务规则: 同一 code 的 version 必须严格 +1, 跨版本无空洞.
        """


__all__ = ["ScenarioRepository"]
