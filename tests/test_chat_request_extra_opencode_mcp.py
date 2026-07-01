"""tests/test_chat_request_extra_opencode_mcp.py — Task 20 review (C2).

Verify that ``ChatRequest.extra_opencode_mcp`` field survives the round-trip:

1. ``ChatRequest(**body)`` accepts the field (pydantic v2 declared, not dropped).
2. Default value is an empty dict (so unset requests don't crash downstream).
3. JSON serialization round-trip preserves the field.
4. ``AgentBridge.chat`` accepts the new ``mcp_servers`` kwarg without TypeError.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from hermetic_agent.api.http.schemas import ChatRequest
from hermetic_agent.mcp.registry import MCPRegistry
from hermetic_agent.providers.agent_bridge import AgentBridge
from hermetic_agent.skills.registry import SkillRegistry
from hermetic_agent.store.memory import MemoryStorage


def test_chat_request_accepts_extra_opencode_mcp() -> None:
    body = {
        "message": "hi",
        "extra_opencode_mcp": {
            "ask_user": {"type": "stdio", "command": "python",
                         "args": ["-m", "ask_user"]},
        },
    }
    req = ChatRequest(**body)
    assert req.extra_opencode_mcp == body["extra_opencode_mcp"]


def test_chat_request_extra_opencode_mcp_defaults_to_empty_dict() -> None:
    req = ChatRequest(message="hi")
    assert req.extra_opencode_mcp == {}


def test_chat_request_round_trip_json() -> None:
    payload = {
        "ask_user": {"type": "stdio", "command": "python"},
        "weather": {"type": "http", "url": "http://mcp/weather"},
    }
    req = ChatRequest(message="hi", extra_opencode_mcp=payload)
    dumped = req.model_dump()
    assert dumped["extra_opencode_mcp"] == payload
    rebuilt = ChatRequest(**dumped)
    assert rebuilt.extra_opencode_mcp == payload


@pytest.fixture
def bridge() -> AgentBridge:
    return AgentBridge(
        skill_registry=SkillRegistry(),
        mcp_registry=MCPRegistry(),
        storage=MemoryStorage(),
    )


@pytest.mark.asyncio
async def test_bridge_chat_accepts_mcp_servers_kwarg(bridge: AgentBridge) -> None:
    """AgentBridge.chat should accept mcp_servers kwarg without raising."""
    adapter = MagicMock()
    adapter.chat = AsyncMock(return_value="result")
    bridge._agents["opencode-core"] = MagicMock(default_model="m")
    bridge._session_to_agent["ses_x"] = "opencode-core"
    bridge.get_provider = MagicMock(return_value=adapter)

    await bridge.chat(
        session_id="ses_x",
        messages=[],
        mcp_servers={"ask_user": {"command": "python"}},
    )
    assert adapter.chat.await_count == 1


@pytest.mark.asyncio
async def test_bridge_chat_mcp_servers_kwarg_defaults_to_none(
    bridge: AgentBridge,
) -> None:
    """Calling without mcp_servers keeps the kwarg backward-compatible."""
    adapter = MagicMock()
    adapter.chat = AsyncMock(return_value="result")
    bridge._agents["opencode-core"] = MagicMock(default_model="m")
    bridge._session_to_agent["ses_y"] = "opencode-core"
    bridge.get_provider = MagicMock(return_value=adapter)

    await bridge.chat(session_id="ses_y", messages=[])
    assert adapter.chat.await_count == 1