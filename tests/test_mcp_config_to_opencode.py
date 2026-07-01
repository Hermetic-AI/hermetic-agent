"""tests/test_mcp_config_to_opencode.py — Task 20 review (I3).

Verify ``McpConfig.to_opencode()`` correctly branches on mcp_type:

- stdio → ``{name, command, args, env}`` (sub-process MCP)
- http/sse → ``{name, url, headers}``
"""
from __future__ import annotations

import uuid

from hermetic_agent.store.models.mcp_config import McpConfig


def _new(code: str, **kw) -> McpConfig:
    base = dict(
        id=uuid.uuid4(), code=code, name=code,
        mcp_type="http", url="http://mcp/x", command=None, args=None,
        env=None, cwd=None, headers=None,
        allowed_tools=None, disabled=False, config=None,
        source="db", status="enabled", owner_user_id="alice",
        visibility="private", is_deleted=False, deleted_at=None,
    )
    base.update(kw)
    return McpConfig(**base)


def test_to_opencode_http_returns_url_and_headers() -> None:
    m = _new("weather", url="http://mcp/weather", headers={"X-K": "v"})
    out = m.to_opencode()
    assert out["name"] == "weather"
    assert out["url"] == "http://mcp/weather"
    assert out["headers"] == {"X-K": "v"}


def test_to_opencode_sse_returns_url_and_headers() -> None:
    m = _new("events", mcp_type="sse", url="http://mcp/events")
    out = m.to_opencode()
    assert out["name"] == "events"
    assert out["url"] == "http://mcp/events"
    assert out["headers"] == {}


def test_to_opencode_stdio_returns_command_args_env() -> None:
    m = _new(
        "ask_user",
        mcp_type="stdio",
        command="python",
        args=["-m", "ask_user"],
        env={"FOO": "bar"},
        url=None,
    )
    out = m.to_opencode()
    assert out["name"] == "ask_user"
    assert out["command"] == "python"
    assert out["args"] == ["-m", "ask_user"]
    assert out["env"] == {"FOO": "bar"}


def test_to_opencode_stdio_defaults_empty_args_and_env() -> None:
    m = _new("minimal", mcp_type="stdio", command="bin", url=None)
    out = m.to_opencode()
    assert out["args"] == []
    assert out["env"] == {}