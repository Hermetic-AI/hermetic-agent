"""Agent resolve 辅助 — 过滤 Agent 引用的 4 类资产, 输出 ResolvedAgent.

把 resolve_for_chat 的过滤逻辑独立成模块, 避免 agent_service.py 超 200 行.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from hermetic_agent.store.dto._common import ActorContext
from hermetic_agent.store.exceptions import NotFoundError
from hermetic_agent.store.models.agent import Agent
from hermetic_agent.store.models.command import Command
from hermetic_agent.store.models.mcp_config import McpConfig
from hermetic_agent.store.models.prompt import Prompt
from hermetic_agent.store.models.skill import Skill
from hermetic_agent.store.services.command_service import CommandService
from hermetic_agent.store.services.mcp_config_service import McpConfigService
from hermetic_agent.store.services.prompt_service import PromptService
from hermetic_agent.store.services.skill_service import SkillService


@dataclass
class ResolvedAgent:
    """chat 时 Agent + 解析后的引用列表 + warnings."""

    agent: Agent
    system_prompt: str
    model: str
    tool_level: str
    network: str
    skill_codes: list[str]
    mcp_server_codes: list[str]
    prompt_codes: list[str]
    command_codes: list[str]
    resolved_skills: list[Skill] = field(default_factory=list)
    resolved_mcps: list[McpConfig] = field(default_factory=list)
    resolved_prompts: list[Prompt] = field(default_factory=list)
    resolved_commands: list[Command] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


async def resolve_agent(
    *,
    agent: Agent,
    actor: ActorContext,
    skill_service: SkillService,
    mcp_service: McpConfigService | None,
    prompt_service: PromptService,
    command_service: CommandService,
) -> ResolvedAgent:
    """按 actor 可见性 + 启用状态 过滤 4 类资产引用."""
    warnings: list[str] = []
    skills = await _filter(skill_service.get_by_code, actor,
                           agent.skill_codes or [], warnings, "skill",
                           check_status=True)
    mcps: list[McpConfig] = []
    if mcp_service is not None:
        mcps = await _filter(mcp_service.get_by_code, actor,
                             agent.mcp_server_codes or [], warnings, "mcp")
    prompts = await _filter(prompt_service.get_by_code, actor,
                            agent.prompt_codes or [], warnings, "prompt")
    commands = await _filter(command_service.get_by_code, actor,
                             agent.command_codes or [], warnings, "command")
    return ResolvedAgent(
        agent=agent,
        system_prompt=agent.system_prompt,
        model=agent.model,
        tool_level=agent.tool_level,
        network=agent.network,
        skill_codes=[s.code for s in skills],
        mcp_server_codes=[m.code for m in mcps],
        prompt_codes=[p.code for p in prompts],
        command_codes=[c.code for c in commands],
        resolved_skills=skills,
        resolved_mcps=mcps,
        resolved_prompts=prompts,
        resolved_commands=commands,
        warnings=warnings,
    )


async def _filter(
    get_by_code,
    actor: ActorContext,
    codes: list[str],
    warnings: list[str],
    label: str,
    *,
    check_status: bool = False,
) -> list:
    """按 code 列表过滤缺失 / 不可见 / (可选) 禁用的资产."""
    out: list = []
    for code in codes:
        try:
            item = await get_by_code(code)
        except NotFoundError:
            warnings.append(f"{label} {code!r} missing")
            continue
        if item.owner_user_id != actor.user_id and item.visibility != "public":
            warnings.append(f"{label} {code!r} not visible to actor")
            continue
        if check_status and item.status != "enabled":
            warnings.append(f"{label} {code!r} disabled")
            continue
        out.append(item)
    return out


__all__ = ["ResolvedAgent", "resolve_agent"]
