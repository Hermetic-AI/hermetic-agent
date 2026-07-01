"""chat_inject/asset_renderer.py — 把 Agent / Prompts / Commands 渲染为 system_prompt + mcp block.

L3 纯函数组件. 不做 IO. 依赖:

  - store/models/prompt.py        Prompt (TYPE_CHECKING)
  - store/models/command.py       Command (TYPE_CHECKING)
  - store/models/mcp_config.py    McpConfig (TYPE_CHECKING)

输出形状:

  - render_system_prompt 返回 ``str``: ``scenario_prompt`` + ``agent.system_prompt``
    + prompts[].content + commands[].system_prompt_addendum, 以 ``\\n\\n`` 拼接.
  - render_opencode_mcp_block 返回 ``dict[str, dict]``: opencode 期望的
    ``mcpServers`` 块; key = MCP 名称 (m.to_opencode() 的 name, 否则 m.code),
    value = name 之外的其余字段 (默认 ``{"url": m.url}``).
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hermetic_agent.store.models.command import Command
    from hermetic_agent.store.models.mcp_config import McpConfig
    from hermetic_agent.store.models.prompt import Prompt


class AssetRenderer:
    """把 Agent / DB Prompt / Command 渲染为 system_prompt 与 opencode mcp block.

    纯函数式 / 同步, 不做 IO.
    """

    SEP = "\n\n"

    def render_system_prompt(
        self,
        *,
        scenario_prompt: str,
        agent,
        prompts: Iterable[Prompt],
        commands: Iterable[Command],
    ) -> str:
        parts: list[str] = []
        if scenario_prompt:
            parts.append(scenario_prompt)
        if agent is not None and getattr(agent, "system_prompt", ""):
            parts.append(agent.system_prompt)
        for p in prompts:
            content = getattr(p, "content", None)
            if content:
                parts.append(content)
        for c in commands:
            add = getattr(c, "system_prompt_addendum", None)
            if add:
                parts.append(add)
        return self.SEP.join(parts)

    def render_opencode_mcp_block(
        self, *, resolved_mcps: Iterable[McpConfig],
    ) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for m in resolved_mcps:
            d = m.to_opencode() if hasattr(m, "to_opencode") else {"name": m.code, "url": m.url}
            name = d.get("name", getattr(m, "code", "mcp"))
            entry = {k: v for k, v in d.items() if k != "name"}
            out[name] = entry
        return out


__all__ = ["AssetRenderer"]
