"""chat_inject/injector_adapter.py — chat 钩子: agent_code -> 系统提示词注入.

L3 适配层: 把 ``AgentResolver`` + ``AssetRenderer`` 包成一个
``inject_agent_into_chat(*, request, chat_request, agent_service, setting_default_code=None)``
钩子, 由 ``chat_controller`` 在 chat handler 顶部调用一次.

设计要点:
- 不修改入参 ``chat_request`` — 通过 ``copy.copy`` 返回新对象.
- 无 agent_code / resolve 失败 → 原样返回 chat_request (no-op).
- 优先级: body.agent_code > X-Agent-Code header > scenario.agent_code > setting_default_code.

Chat-shell 侧信道 (Task E):
- 解析成功后, 在返回的 chat_request 上挂一个 ``resolved_assets`` 字段
  (agent_code + 4 类 code 列表), 供 ``chat_controller`` 读取后 emit
  ``StreamEvent.assets_loaded`` 给前端 chip 行.
- 这是单纯 attach 字段, 不动 Pydantic model schema, 不破坏现有签名 / 测试.
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

    解析成功时, 返回对象上会多一个 ``resolved_assets`` 属性 (dict):
    ``{agent_code, prompts[], commands[], skills[], mcps[]}``. 供 controller
    emit ``StreamEvent.assets_loaded``.  ``None`` 表示未解析 (no-op / 失败).
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
    if not getattr(chat_request, "model", None) and getattr(resolved.agent, "model", None):
        new_req.model = resolved.agent.model
    new_req.extra_opencode_mcp = {
        **(getattr(chat_request, "extra_opencode_mcp", {}) or {}),
        **new_mcp,
    }
    if resolved.warnings:
        new_req.warnings = list(
            getattr(chat_request, "warnings", []) or [],
        ) + resolved.warnings
    # Chat-shell 侧信道: 挂 resolved codes 给 controller.
    # 用 setattr 避开 Pydantic model 严格字段约束 (BaseModel.copy 后
    # 不会校验未声明字段; 直接赋值会触发 model_config 警告).
    resolved_assets = {
        "agent_code": getattr(resolved.agent, "code", None),
        "prompts": [p.code for p in (resolved.resolved_prompts or [])],
        "commands": [c.code for c in (resolved.resolved_commands or [])],
        "skills": [s.code for s in (resolved.resolved_skills or [])],
        "mcps": [m.code for m in (resolved.resolved_mcps or [])],
    }
    try:
        setattr(new_req, "resolved_assets", resolved_assets)  # noqa: B010 (动态字段)
    except Exception as e:
        # Pydantic v2 严格模式下可能拒绝未声明字段; 退化到 __dict__ 直接挂.
        logger.debug("resolved_assets_setattr_fallback", error=str(e))
        try:
            object.__setattr__(new_req, "resolved_assets", resolved_assets)
        except Exception as e2:
            logger.warning(
                "resolved_assets_attach_failed",
                error=str(e2),
                note="chat-shell chip 事件将无法 emit, controller 会跳过",
            )
    return new_req


__all__ = ["inject_agent_into_chat"]
