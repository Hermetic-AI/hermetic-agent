from __future__ import annotations

from types import SimpleNamespace


def test_agent_bridge_preserves_native_opencode_tool_names() -> None:
    from openagent.mcp.registry import MCPTool
    from openagent.providers.agent_bridge import AgentBridge

    registry = SimpleNamespace(
        list_all_by_names=lambda names: [MCPTool(name="ask_user")],
    )
    bridge = AgentBridge(skill_registry=None, mcp_registry=registry, storage=SimpleNamespace())

    out = bridge._resolve_tools_for_adapter([
        "ask_user",
        "feihe-travel_queryFlightBasic",
    ])

    assert out is not None
    assert out[0].name == "ask_user"
    assert out[1] == "feihe-travel_queryFlightBasic"


def test_agent_bridge_create_session_uses_agent_default_model(monkeypatch) -> None:
    import asyncio

    from openagent.providers.agent_bridge import AgentBridge
    from openagent.providers.base import AgentConfig, SessionInfo

    captured = {}

    class _Provider:
        async def create_session(self, **kwargs):
            captured.update(kwargs)
            return SessionInfo(
                session_id="ses_1",
                agent_name=kwargs["agent_name"],
                agent_base_url=kwargs["base_url"],
                model=kwargs["model"],
            )

    bridge = AgentBridge(skill_registry=None, mcp_registry=None, storage=SimpleNamespace())
    bridge._providers["opencode-core"] = _Provider()
    bridge._agents["opencode-core"] = AgentConfig(
        name="opencode-core",
        base_url="http://opencode-1:14096",
        sdk_type="opencode",
        default_model="MiniMax-M2.7-highspeed",
    )

    asyncio.run(bridge.create_session("opencode-core"))

    assert captured["model"] == "MiniMax-M2.7-highspeed"


def test_extract_mcp_token_falls_back_to_flight_api_key(monkeypatch) -> None:
    from openagent.api.controllers.chat_controller import _extract_effective_mcp_token

    monkeypatch.setenv("FLIGHT_API_KEY", "env-token-123")
    request = SimpleNamespace(headers={})

    assert _extract_effective_mcp_token(request) == "env-token-123"


def test_runtime_context_does_not_expose_mcp_token() -> None:
    from openagent.providers.opencode_chat import _build_runtime_context

    out = _build_runtime_context("base", "secret-token-123")

    assert out is not None
    assert "secret-token-123" not in out
    assert "MCP_TOKEN:" not in out
    assert "queryFlightBasic" in out
    assert "不要手写 curl" in out


def test_resolve_tool_names_adds_feihe_native_alias() -> None:
    from openagent.providers.opencode_chat import _resolve_tool_names

    out = _resolve_tool_names(SimpleNamespace(), ["queryFlightBasic", "ask_user"])

    assert out is not None
    assert out["queryFlightBasic"] is True
    assert out["feihe-travel_queryFlightBasic"] is True
    assert out["ask_user"] is True


def test_build_session_prompt_payload_uses_current_opencode_schema() -> None:
    from openagent.providers.opencode_chat import _build_session_prompt_payload

    payload = _build_session_prompt_payload({
        "provider_id": "openai",
        "model_id": "MiniMax-M3",
        "parts": [{"type": "text", "text": "hello", "id": "prt_1"}],
        "system": "system",
        "tools": {"feihe-travel_queryFlightBasic": True},
    })

    assert payload["model"] == {"providerID": "openai", "modelID": "MiniMax-M3"}
    assert "providerID" not in payload
    assert "modelID" not in payload
    assert payload["tools"]["feihe-travel_queryFlightBasic"] is True


def test_resolve_tool_names_disables_unlisted_opencode_builtins() -> None:
    from openagent.providers.opencode_chat import _resolve_tool_names

    out = _resolve_tool_names(SimpleNamespace(), ["queryFlightBasic", "ask_user"])

    assert out is not None
    for name in ("question", "skill", "read", "glob", "grep", "task", "todowrite"):
        assert out[name] is False


def test_resolve_tool_names_allows_explicit_builtin_tool() -> None:
    from openagent.providers.opencode_chat import _resolve_tool_names

    out = _resolve_tool_names(SimpleNamespace(), ["question"])

    assert out is not None
    assert out["question"] is True


def test_render_config_adds_flight_mcp_from_env(monkeypatch) -> None:
    from docker.render_config import render

    monkeypatch.setenv("FLIGHT_API_KEY", "env-token-123")
    cfg = render({"agent": {"model": "openai/qwen"}, "tool_level": "standard"})

    flight = cfg["mcp"]["feihe-travel"]
    assert flight["type"] == "remote"
    assert flight["url"] == "https://traveldev.feiheair.com/api/mcp"
    assert flight["oauth"] is False
    assert flight["headers"]["token"] == "{env:FLIGHT_API_KEY}"
    assert "env-token-123" not in str(flight)
    assert cfg["tool_output"]["max_bytes"] >= 1048576


def test_render_config_registers_flight_mcp_without_env_token(monkeypatch) -> None:
    from docker.render_config import render

    monkeypatch.delenv("FLIGHT_API_KEY", raising=False)
    cfg = render({"agent": {"model": "openai/qwen"}, "tool_level": "standard"})

    flight = cfg["mcp"]["feihe-travel"]
    assert flight["enabled"] is True
    assert flight["headers"]["token"] == "{env:FLIGHT_API_KEY}"


def test_render_config_safe_level_denies_task_tool() -> None:
    from docker.render_config import render

    cfg = render({"agent": {"model": "openai/qwen"}, "tool_level": "safe"})

    assert cfg["permission"]["task"] == "deny"
    assert cfg["permission"]["todowrite"] == "deny"


def test_render_config_normalizes_policy_mcp_servers(monkeypatch) -> None:
    from docker.render_config import render

    monkeypatch.delenv("FLIGHT_API_KEY", raising=False)
    cfg = render({
        "agent": {"model": "openai/qwen"},
        "mcp_servers": {
            "mcpServers": {
                "feihe-travel": {
                    "type": "http",
                    "url": "https://example.test/mcp",
                    "disabled": False,
                },
            },
        },
    })

    flight = cfg["mcp"]["feihe-travel"]
    assert flight["type"] == "remote"
    assert flight["enabled"] is True
    assert "disabled" not in flight


def test_render_config_preserves_explicit_tool_output(monkeypatch) -> None:
    from docker.render_config import render

    monkeypatch.setenv("FLIGHT_API_KEY", "env-token-123")
    cfg = render({
        "agent": {"model": "openai/qwen"},
        "tool_output": {"max_lines": 100, "max_bytes": 200000},
    })

    assert cfg["tool_output"] == {"max_lines": 100, "max_bytes": 200000}


# ---------------------------------------------------------------------------
# _push_flight_token_to_opencode: token 透传到 opencode 容器 env 的链路
# ---------------------------------------------------------------------------


class _FakeAsyncClient:
    """httpx.AsyncClient 的最小替身, 记录请求体 + 给出固定响应."""

    instances: list[_FakeAsyncClient] = []

    def __init__(self, *, timeout: float = 0.0):
        self.timeout = timeout
        self.requests: list[tuple[str, dict | None]] = []
        self.status_code = 200
        self.text = "ok"
        _FakeAsyncClient.instances.append(self)

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *args) -> None:
        return None

    async def post(self, url: str, json: dict | None = None, headers: dict | None = None):
        self.requests.append((url, json))
        # 给一个简单的 Response-like 对象
        return SimpleNamespace(status_code=self.status_code, text=self.text)

    async def get(self, url: str):
        self.requests.append((url, None))
        return SimpleNamespace(status_code=200, json=lambda: {"healthy": True})


def _run(coro):
    """简易 await helper (不依赖 pytest-asyncio)."""
    import asyncio
    return asyncio.get_event_loop().run_until_complete(coro) if False else coro


async def _noop():
    return None


def test_push_flight_token_writes_env_and_reload_first_time(monkeypatch) -> None:
    """首次写入: 应触发 POST /admin/env + POST /admin/reload, body 含 token."""
    from openagent.providers import opencode_chat

    monkeypatch.setenv("OPENCODE_RELOAD_SETTLE_SECONDS", "0")
    _FakeAsyncClient.instances.clear()
    monkeypatch.setattr(opencode_chat, "httpx", SimpleNamespace(
        AsyncClient=_FakeAsyncClient,
        HTTPError=Exception,
    ))
    # 清缓存, 强制走写入路径
    opencode_chat._FLIGHT_TOKEN_LAST_WRITTEN.clear()

    import asyncio
    asyncio.run(
        opencode_chat._push_flight_token_to_opencode(
            agent_base_url="http://opencode-1:14096",
            mcp_token="user-session-token-abc",
        )
    )

    assert len(_FakeAsyncClient.instances) == 1
    cli = _FakeAsyncClient.instances[0]
    # 第一次请求 = /admin/env 写 FLIGHT_API_KEY
    url1, body1 = cli.requests[0]
    assert url1 == "http://opencode-1:7778/admin/env"
    assert body1 == {"FLIGHT_API_KEY": "user-session-token-abc"}
    # 第二次请求 = /admin/reload 触发 opencode 重启
    url2, body2 = cli.requests[1]
    assert url2 == "http://opencode-1:7778/admin/reload"
    assert body2 == {}
    # 缓存已记录, 下次同 token 不再写
    assert opencode_chat._FLIGHT_TOKEN_LAST_WRITTEN["http://opencode-1:14096"] == "user-session-token-abc"


def test_push_flight_token_skipped_when_token_unchanged(monkeypatch) -> None:
    """同一 token 反复调用: 不应触发任何 HTTP 请求 (避免每条 chat 都 reload)."""
    from openagent.providers import opencode_chat

    _FakeAsyncClient.instances.clear()
    monkeypatch.setattr(opencode_chat, "httpx", SimpleNamespace(
        AsyncClient=_FakeAsyncClient,
        HTTPError=Exception,
    ))
    # 预填缓存 = 同一 token, 模拟上一次写过
    opencode_chat._FLIGHT_TOKEN_LAST_WRITTEN["http://opencode-1:14096"] = "stable-token"

    import asyncio
    asyncio.run(
        opencode_chat._push_flight_token_to_opencode(
            agent_base_url="http://opencode-1:14096",
            mcp_token="stable-token",
        )
    )

    # 关键断言: 0 个 AsyncClient 实例被创建, 0 个请求
    assert _FakeAsyncClient.instances == []


def test_push_flight_token_writes_again_on_token_change(monkeypatch) -> None:
    """用户重新登录 (token 变化): 必须再次触发 admin env + reload."""
    from openagent.providers import opencode_chat

    monkeypatch.setenv("OPENCODE_RELOAD_SETTLE_SECONDS", "0")
    _FakeAsyncClient.instances.clear()
    monkeypatch.setattr(opencode_chat, "httpx", SimpleNamespace(
        AsyncClient=_FakeAsyncClient,
        HTTPError=Exception,
    ))
    opencode_chat._FLIGHT_TOKEN_LAST_WRITTEN["http://opencode-1:14096"] = "old-token"

    import asyncio
    asyncio.run(
        opencode_chat._push_flight_token_to_opencode(
            agent_base_url="http://opencode-1:14096",
            mcp_token="new-token",
        )
    )

    assert len(_FakeAsyncClient.instances) == 1
    cli = _FakeAsyncClient.instances[0]
    assert cli.requests[0][1] == {"FLIGHT_API_KEY": "new-token"}
    assert opencode_chat._FLIGHT_TOKEN_LAST_WRITTEN["http://opencode-1:14096"] == "new-token"


def test_push_flight_token_swallows_network_errors(monkeypatch) -> None:
    """admin 端点不通 (容器未起 / 端口被挡): 不能让 chat 抛异常, 仅 warn."""
    from openagent.providers import opencode_chat

    class _BoomClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            raise OSError("connection refused")

        async def __aexit__(self, *args):
            return None

    monkeypatch.setattr(opencode_chat, "httpx", SimpleNamespace(
        AsyncClient=_BoomClient,
        HTTPError=Exception,
    ))
    opencode_chat._FLIGHT_TOKEN_LAST_WRITTEN.clear()

    import asyncio
    # 不应抛
    asyncio.run(
        opencode_chat._push_flight_token_to_opencode(
            agent_base_url="http://opencode-1:14096",
            mcp_token="some-token",
        )
    )
    # 缓存不应在失败时记录 (下次会再试)
    assert "http://opencode-1:14096" not in opencode_chat._FLIGHT_TOKEN_LAST_WRITTEN


def test_routes_extract_mcp_token_accepts_bare_token_header() -> None:
    """飞鹤 traveldev 后端用单 `token` header (跟 logonV2 响应头同名),
    routes._extract_mcp_token 必须能从这个 header 提取出来."""
    from openagent.api.routes import _extract_mcp_token

    request = SimpleNamespace(headers={
        "token": "feihe-session-xyz",
    })
    assert _extract_mcp_token(request) == "feihe-session-xyz"

    # 优先级: X-MCP-Token > Authorization Bearer > token
    request2 = SimpleNamespace(headers={
        "X-MCP-Token": "explicit",
        "token": "feihe-fallback",
    })
    assert _extract_mcp_token(request2) == "explicit"
