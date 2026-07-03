"""chat_inject/agent_resolver.py — 薄包装 AgentService.resolve_for_chat.

L3 组件. 让 chat_inject 单独 import 这层 — 单元测试可以单独 mock
agent_service, 不必拖整个 AgentService 依赖图.

依赖:
  - store/services/agent_service.AgentService
  - store/dto/_common.ActorContext

输出形状: ``resolve`` 返回 ``ResolvedAgent | None``, 与底层 service 完全一致.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from hermetic_agent.store.dto._common import ActorContext
from hermetic_agent.store.services.agent_service import AgentService

if TYPE_CHECKING:
    from hermetic_agent.store.services._agent_resolve import ResolvedAgent


class AgentResolver:
    """薄包装 AgentService.resolve_for_chat — 让 chat_inject 单独 import 这层."""

    def __init__(self, agent_service: AgentService) -> None:
        self._svc = agent_service

    async def resolve(
        self, *, actor: ActorContext, agent_code: str,
    ) -> ResolvedAgent | None:
        return await self._svc.resolve_for_chat(
            actor=actor, agent_code=agent_code,
        )


__all__ = ["AgentResolver"]

