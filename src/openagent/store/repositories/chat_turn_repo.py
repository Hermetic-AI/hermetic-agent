"""ChatTurnRepository ABC — 单轮执行仓储接口."""

from __future__ import annotations

from abc import abstractmethod
from datetime import datetime

from openagent.store.models.chat_turn import ChatTurn
from openagent.store.repositories._base import Repository


class ChatTurnRepository(Repository[ChatTurn]):
    """单轮执行仓储接口."""

    @abstractmethod
    async def list_by_session(
        self,
        session_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
    ) -> list[ChatTurn]:
        """按 session 列 turn(按 created_at DESC)."""

    @abstractmethod
    async def list_by_status(
        self,
        status: str,
        *,
        limit: int = 50,
        since: datetime | None = None,
    ) -> list[ChatTurn]:
        """按状态列 turn(监控 / 失败重试用)."""

    @abstractmethod
    async def mark_started(self, turn_id: str, when: datetime | None = None) -> ChatTurn | None:
        """标 turn 进入 running, 同时写 started_at."""

    @abstractmethod
    async def mark_finished(
        self,
        turn_id: str,
        status: str,
        *,
        finished_at: datetime | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> ChatTurn | None:
        """标 turn 进入 success/failed/cancelled, 写 finished_at + duration_ms."""


__all__ = ["ChatTurnRepository"]
