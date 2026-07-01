"""chat_inject/injector_adapter.py — chat 钩子: agent_code -> 系统提示词注入.

L3 适配层: 把 ``AgentResolver`` + ``AssetRenderer`` 包成一个
``inject_agent_into_chat(*, request, chat_request, agent_service, setting_default_code=None)``
钩子, 由 ``chat_controller`` 在 chat handler 顶部调用一次.

设计要点:
- 不修改入参 ``chat_request`` — 通过 ``copy.copy`` 返回新对象.
- 无 agent_code / resolve 失败 → 原样返回 chat_request (no-op).
- 优先级: body.agent_code > X-Agent-Code header > scenario.agent_code > setting_default_code.
"""
from __future__ import annotations

import copy

import structlog

from hermetic_agent.chat_inject.agent_resolver import AgentResolver
from hermetic_agent.chat_inject.asset_renderer import AssetRenderer
from hermetic_agent.store.dto._common import ActorContext

logger = structlog.get_logger(__name__)


def _resolve_agent_code(request, chat_request) -> str | None:
    """agent_code 优先级: body > header > scenario.yaml > settings default."""
    body = getattr(request, "json", None) or {}
    headers = getattr(request, "headers", {}) or {}
    scenario = getattr(chat_request, "scenario", None)
    scenario_code = getattr(scenario, "agent_code", None) if scenario is not None else None
    return (
        body.get("agent_code")
        or headers.get("X-Agent-Code")
        or scenario_code
    )


async def inject_agent_into_chat(
    *,
    request,
    chat_request,
    agent_service,
    setting_default_code: str | None = None,
):
    """chat 钩子: 取 agent_code -> 解析 -> 改写 system_prompt + extra_opencode_mcp.

    不修改 request / chat_request 既有字段名; 通过 ``copy.copy`` 返回新对象.
    无 agent_code 或 resolve 失败时原样返回 chat_request.
    """
    actor: ActorContext = getattr(
        request.ctx, "actor", ActorContext(user_id="anonymous"),
    )
    agent_code = _resolve_agent_code(request, chat_request) or setting_default_code
    if not agent_code:
        return chat_request

    resolver = AgentResolver(agent_service)
    resolved = await resolver.resolve(actor=actor, agent_code=agent_code)
    if resolved is None:
        logger.info(
            "agent_resolution_skipped", code=agent_code, actor=actor.user_id,
        )
        return chat_request

    renderer = AssetRenderer()
    new_prompt = renderer.render_system_prompt(
        scenario_prompt=getattr(chat_request, "system_prompt", "") or "",
        agent=resolved.agent,
        prompts=resolved.resolved_prompts,
        commands=resolved.resolved_commands,
    )
    new_mcp = renderer.render_opencode_mcp_block(
        resolved_mcps=resolved.resolved_mcps,
    )
    new_req = copy.copy(chat_request)
    new_req.system_prompt = new_prompt
    new_req.extra_opencode_mcp = {
        **(getattr(chat_request, "extra_opencode_mcp", {}) or {}),
        **new_mcp,
    }
    if resolved.warnings:
        new_req.warnings = list(
            getattr(chat_request, "warnings", []) or [],
        ) + resolved.warnings
    return new_req


__all__ = ["inject_agent_into_chat"]
