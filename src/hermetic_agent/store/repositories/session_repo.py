"""SessionRepository ABC — 会话仓储接口."""

from __future__ import annotations

from abc import abstractmethod

from hermetic_agent.store.models.session import Session
from hermetic_agent.store.repositories._base import Repository


class SessionRepository(Repository[Session]):
    """会话仓储接口."""

    @abstractmethod
    async def list_by_user(
        self,
        user_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> list[Session]:
        """按用户 ID 列出会话(按 updated_at DESC)."""

    @abstractmethod
    async def list_by_scenario(
        self, scenario_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[Session]:
        """按场景 ID 列出使用该场景的所有会话."""

    @abstractmethod
    async def update_aggregates(
        self,
        session_id: str,
        *,
        message_count: int | None = None,
        cost_delta: float | None = None,
        tokens_input_delta: int | None = None,
        tokens_output_delta: int | None = None,
        tokens_reasoning_delta: int | None = None,
        tokens_cache_read_delta: int | None = None,
        tokens_cache_write_delta: int | None = None,
    ) -> Session | None:
        """增量更新 session 聚合字段(写完 turn / message 后调).

        业务规则: cost / tokens 是增量叠加, message_count 是绝对值覆盖.
        """


__all__ = ["SessionRepository"]
