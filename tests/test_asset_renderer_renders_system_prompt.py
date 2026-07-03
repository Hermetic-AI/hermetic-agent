"""tests/test_asset_renderer_renders_system_prompt.py — 验证 AssetRenderer 渲染顺序.

AssetRenderer 是 chat_inject (L3) 的纯函数组件, 把 ResolvedAgent / Prompts /
Commands 拼成 chat 的 system_prompt; 把 McpConfig 列表拼成 opencode 期望的
``mcpServers`` block. 这里不接 DB / sandbox, 用 SimpleNamespace 模拟.
"""
from __future__ import annotations

from types import SimpleNamespace

from hermetic_agent.chat_inject.asset_renderer import AssetRenderer


def test_render_system_prompt_concatenates_in_order() -> None:
    r = AssetRenderer()
    out = r.render_system_prompt(
        scenario_prompt="You are helpful.",
        agent=None, prompts=[], commands=[],
    )
    assert out == "You are helpful."


def test_render_system_prompt_includes_agent_prompts_commands_in_order() -> None:
    r = AssetRenderer()
    agent = SimpleNamespace(system_prompt="AP.")
    prompts = [
        SimpleNamespace(content="P1."),
        SimpleNamespace(content="P2."),
    ]
    commands = [SimpleNamespace(system_prompt_addendum="CMD x.")]
    out = r.render_system_prompt(
        scenario_prompt="SC.",
        agent=agent, prompts=prompts, commands=commands,
    )
    parts = ["SC.", "AP.", "P1.", "P2.", "CMD x."]
    for i in range(len(parts) - 1):
        prev, nxt = parts[i], parts[i + 1]
        assert out.index(prev) < out.index(nxt), (
            f"expected {prev!r} before {nxt!r} in {out!r}"
        )


def test_render_opencode_mcp_block_uses_mcp_to_opencode_or_code_url() -> None:
    mcp_a = SimpleNamespace(
        code="a",
        url="http://a",
        to_opencode=lambda: {"name": "a", "url": "http://a"},
    )
    r = AssetRenderer()
    out = r.render_opencode_mcp_block(resolved_mcps=[mcp_a])
    assert "a" in out
    assert out["a"]["url"] == "http://a"
