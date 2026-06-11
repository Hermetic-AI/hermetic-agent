"""Chat dispatch for the OpenCode adapter.

Module-level functions take the adapter instance as the first arg so they
can read its state (clients, sessions, mcp_registry, storage) without
becoming methods. The adapter class in ``opencode_adapter.py`` is a
thin shell that delegates to these functions.

Real-time streaming follows the official SDK recommendation
(https://github.com/anomalyco/opencode-sdk-python#streaming-responses):
subscribe to the long-lived ``client.event.list()`` SSE stream and filter
events for the target session_id, rather than parsing HTTP response bodies.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import os
import traceback
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from openagent.providers.base import (
    ChatMessage,
    ChatResult,
    SessionInfo,
    ToolCall,
)
from openagent.providers.llm_payload import (
    build_opencode_payload,
    log_opencode_request,
)
from openagent.store.base import Message as StorageMessage
from openagent.streaming import (
    OPENCODE_STREAM_END,
    StreamEvent,
    map_opencode_event,
)

try:
    from opencode_ai import AsyncOpencode
except ImportError:  # pragma: no cover
    from openagent._vendor.opencode import AsyncOpencode  # type: ignore

if TYPE_CHECKING:
    from openagent.providers.opencode_adapter import OpenCodeAdapter

logger = structlog.get_logger(__name__)


# Per-session 去重: Hub 端兜底 FLIGHT_RESULT 卡片, 每个 session 只 emit 一次.
# 如果 LLM 在一轮对话里多次调 queryFlightBasic (用户追问细化), Hub 只组装第一
# 次的卡片, 后续当普通 tool_result 透传 (避免重复轰炸前端).
_FLIGHT_CARD_EMITTED: set[str] = set()

# 缓存: 同一 opencode 节点 (按 base_url 标识) 上一次写入的 FLIGHT_API_KEY.
# 同一个用户连发 N 条消息, 只在 token 变化时调一次 admin API 写 env +
# reload. 避免每条 chat 都触发 opencode 重启 (~1s 卡顿).
_FLIGHT_TOKEN_LAST_WRITTEN: dict[str, str] = {}

# ENV var name — feihe-travel MCP 调外部 HTTP 时, render_config.py 读这个
# env 渲染到 opencode config.json 的 mcp.feihe-travel.headers.token.
# 跟 render_config._flight_mcp_server_from_env / _flight_auth_header_value
# 保持一致.
FLIGHT_MCP_TOKEN_ENV = "FLIGHT_API_KEY"
# Admin server 监听端口 (跟 docker/admin_server.py / docker-compose.yml 一致)
# 历史硬编码: 7778. 现在从 settings.opencode_admin_port 读, 保留模块级常量
# 作为兜底 (settings import 失败 / 单测不传 settings 的场景).
OPENCODE_ADMIN_PORT_FALLBACK = 7778


def _settings():
    """懒加载 settings, 避免顶层 import 触发 .env 解析副作用."""
    try:
        from openagent.config.settings import get_settings
        return get_settings()
    except Exception:  # pragma: no cover
        return None


def _opencode_admin_port() -> int:
    """OpenCode admin server 端口. 优先 settings, 兜底模块常量."""
    s = _settings()
    if s is not None:
        return int(s.opencode_admin_port)
    return OPENCODE_ADMIN_PORT_FALLBACK


def _flight_mcp_token_env() -> str:
    """feihe-travel MCP token env 名. 优先 settings, 兜底模块常量."""
    s = _settings()
    if s is not None:
        return str(s.flight_mcp_token_env)
    return FLIGHT_MCP_TOKEN_ENV


# 向后兼容: 旧代码 ``OPENCODE_ADMIN_PORT`` / ``FLIGHT_MCP_TOKEN_ENV`` 直接
# 引用模块名的也工作. 优先用上面的 _opencode_admin_port() / _flight_mcp_token_env().
OPENCODE_ADMIN_PORT = OPENCODE_ADMIN_PORT_FALLBACK


def _is_transient_opencode_error(exc: BaseException) -> bool:
    """Return True for connection resets caused by opencode restart/reload."""
    transient_names = {
        "ReadError",
        "ConnectError",
        "RemoteProtocolError",
        "TransportError",
        "APIConnectionError",
    }
    current: BaseException | None = exc
    seen = 0
    while current is not None and seen < 5:
        name = type(current).__name__
        if name in transient_names or any(n in str(current) for n in transient_names):
            return True
        current = current.__cause__ or current.__context__
        seen += 1
    return False


def _is_opencode_session_init_race(exc: BaseException) -> bool:
    """Detect opencode 1.17.0 share-subscriber race on first session prompt.

    Right after a brand-new session is created, opencode's internal
    ``share subscriber`` (which broadcasts ``message.updated`` events) can
    fire *before* the session's primary model binding is fully visible to
    ``SessionPrompt.getModel``. When that happens the subscriber raises
    ``ProviderModelNotFoundError`` and the entire ``POST /session/{id}/message``
    returns 500 — even though a *retry* of the same POST a few hundred ms
    later goes through cleanly because the binding has settled.

    We treat such 5xx + ``ProviderModelNotFoundError`` as a transient race
    that deserves a short backoff retry, separate from the
    connect/reload-style errors handled by ``_is_transient_opencode_error``.
    """
    import httpx

    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code >= 500:
            blob = (exc.response.text or "") + " " + str(exc)
            if "ProviderModelNotFoundError" in blob or "UnknownError" in blob:
                return True
    current: BaseException | None = exc
    seen = 0
    while current is not None and seen < 5:
        if "ProviderModelNotFoundError" in str(current):
            return True
        current = current.__cause__ or current.__context__
        seen += 1
    return False


async def _wait_opencode_health(
    base_url: str,
    *,
    timeout_seconds: float | None = None,
    interval_seconds: float | None = None,
    client: httpx.AsyncClient | None = None,
) -> bool:
    """Wait until opencode serve is ready after admin reload.

    ``timeout_seconds`` / ``interval_seconds`` 为 None 时从 settings 读
    (opencode_wait_health_timeout / opencode_wait_health_interval), 再
    兜底模块常量.
    """
    s = _settings()
    if timeout_seconds is None:
        timeout_seconds = (
            float(s.opencode_wait_health_timeout)
            if s is not None
            else 8.0
        )
    if interval_seconds is None:
        interval_seconds = (
            float(s.opencode_wait_health_interval)
            if s is not None
            else 0.25
        )

    deadline = asyncio.get_running_loop().time() + timeout_seconds
    if client is not None:
        while True:
            try:
                resp = await client.get(f"{base_url}/global/health")
                if resp.status_code < 400:
                    data = resp.json()
                    if not isinstance(data, dict) or data.get("healthy", True):
                        logger.debug("opencode_reload_health_ok", base_url=base_url)
                        return True
            except Exception as e:
                logger.debug("opencode_reload_health_waiting", base_url=base_url, error=str(e))
            if asyncio.get_running_loop().time() >= deadline:
                return False
            await asyncio.sleep(interval_seconds)
    async with httpx.AsyncClient(timeout=2.0) as new_client:
        return await _wait_opencode_health(
            base_url,
            timeout_seconds=timeout_seconds,
            interval_seconds=interval_seconds,
            client=new_client,
        )


async def _close_cached_opencode_client(
    adapter: OpenCodeAdapter,
    agent_name: str,
    base_url: str,
) -> None:
    key = f"{agent_name}:{base_url}"
    client = adapter._clients.pop(key, None)
    if client is None:
        return
    for candidate in (client, getattr(client, "_client", None)):
        if candidate is None:
            continue
        close = getattr(candidate, "aclose", None) or getattr(candidate, "close", None)
        if not callable(close):
            continue
        try:
            result = close()
            if inspect.isawaitable(result):
                await result
        except Exception as e:
            logger.debug("opencode_client_close_warn", key=key, error=str(e))
        break
    logger.debug("opencode_client_cache_invalidated", key=key)


async def _push_flight_token_to_opencode(
    agent_base_url: str,
    mcp_token: str,
) -> bool:
    """把当前 mcp_token 写进 opencode 容器的 env.runtime + reload.

    触发条件: 同 base_url 上次的 token != 现在的 token.
    副作用: opencode serve 被 SIGTERM, supervisor ~1s 内拉起新进程, 新进程
    从 env.runtime 读 FLIGHT_API_KEY → render_config.py 把它塞进
    mcp.feihe-travel.headers.token → 后续 MCP HTTP 调用带 `token: <value>`
    header.

    Args:
        agent_base_url: e.g. ``http://opencode-1:14096``. 我们推导 admin 端口.
        mcp_token: 来自 Hub ``_extract_mcp_token`` 的 token, 可能是 feihe
            logonV2 返回的 session token, 也可能是 X-MCP-Token 透传.

    Side effects:
        - HTTP POST 到容器内 :7778/admin/env (写 env.runtime)
        - HTTP POST 到容器内 :7778/admin/reload (SIGTERM + 1s 后自启)
        失败时仅 logger.warning, 不抛 — 当前 chat 仍然能跑 (只是 feihe MCP
        会用旧 token / 没 token, 然后 401, SKILL.md 错误处理兜底).
    """
    last = _FLIGHT_TOKEN_LAST_WRITTEN.get(agent_base_url)
    if last == mcp_token:
        return False  # token 没变, 跳过

    # 从 base_url 推导 admin URL: http://host:14096 → http://host:7778
    # base_url 形如 "http://opencode-1:14096", 切到 admin 端口即可
    try:
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(agent_base_url)
        admin_netloc = (
            f"{parsed.hostname}:{_opencode_admin_port()}"
            if parsed.hostname
            else None
        )
        if not admin_netloc:
            return False
        admin_url = urlunparse(parsed._replace(netloc=admin_netloc))
    except Exception as e:  # pragma: no cover - 防御
        logger.warning("push_flight_token_url_parse_failed", error=str(e))
        return False

    token_env_name = _flight_mcp_token_env()
    headers = {"Content-Type": "application/json"}
    env_body = {token_env_name: mcp_token}
    reload_healthy = False

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # 1) 写 env
            r1 = await client.post(
                f"{admin_url}/admin/env",
                json=env_body,
                headers=headers,
            )
            if r1.status_code >= 400:
                logger.warning(
                    "push_flight_token_env_write_failed",
                    agent_base_url=agent_base_url,
                    status=r1.status_code,
                    body=r1.text[:200],
                )
                return False
            logger.info(
                "push_flight_token_env_written",
                agent_base_url=agent_base_url,
                admin_url=admin_url,
                env=token_env_name,
                token_len=len(mcp_token),
            )
            # 2) trigger reload (SIGTERM → supervisor ~1s 重启)
            r2 = await client.post(
                f"{admin_url}/admin/reload",
                json={},
                headers=headers,
            )
            if r2.status_code >= 400:
                logger.warning(
                    "push_flight_token_reload_failed",
                    agent_base_url=agent_base_url,
                    status=r2.status_code,
                    body=r2.text[:200],
                )
                return False
            logger.info(
                "push_flight_token_reload_triggered",
                agent_base_url=agent_base_url,
                admin_url=admin_url,
            )
            s = _settings()
            settle_seconds = (
                float(s.opencode_reload_settle_seconds)
                if s is not None
                else float(os.environ.get("OPENCODE_RELOAD_SETTLE_SECONDS", "1.0"))
            )
            if settle_seconds > 0:
                await asyncio.sleep(settle_seconds)
            reload_healthy = await _wait_opencode_health(
                agent_base_url,
                client=client,
            )
    except (httpx.HTTPError, OSError) as e:
        # 网络/超时 — 别把 chat 拖死, 仅告警
        logger.warning(
            "push_flight_token_admin_unreachable",
            agent_base_url=agent_base_url,
            error=str(e),
        )
        return False

    if not reload_healthy:
        logger.warning(
            "push_flight_token_reload_health_timeout",
            agent_base_url=agent_base_url,
        )
        return False

    _FLIGHT_TOKEN_LAST_WRITTEN[agent_base_url] = mcp_token
    logger.info(
        "push_flight_token_ok",
        agent_base_url=agent_base_url,
        env=token_env_name,
        token_len=len(mcp_token),
    )
    return True


_FEIHE_TRAVEL_TOOLS = {
    "checkProductAccess",
    "getDateInfo",
    "listUpcomingHolidays",
    "getHolidayDate",
    "queryFlightBasic",
    "filterFlightList",
    "chooseFlight",
    "getFlightPolicyInfo",
    "chooseCabin",
    "chooseAlternativeCabin",
    "listTripApplications",
    "getTripApplicationDetail",
    "listCostCenters",
    "bindCostCenter",
    "getDefaultContact",
    "fillPassenger",
    "validateBookingInfo",
    "recordPolicyUserDecision",
    "buildOrderPreview",
    "getOrderDetail",
    "resetBookingSession",
}


_OPENCODE_BUILTIN_TOOLS = {
    "bash",
    "edit",
    "glob",
    "grep",
    "question",
    "read",
    "skill",
    "task",
    "todo",
    "todoread",
    "todowrite",
    "write",
    "Bash",
    "Edit",
    "Glob",
    "Grep",
    "Read",
    "Task",
    "Write",
}


# ---------------------------------------------------------------------------
# Client lookup
# ---------------------------------------------------------------------------


def _build_http_client() -> httpx.AsyncClient:
    """构造带显式 timeout + 限流的 httpx.AsyncClient, 注入到 SDK 客户端.

    重要 — 不调这个会断流:
    - SDK ``AsyncOpencode(base_url=...)`` 默认 ``timeout=NOT_GIVEN``,
      httpx 兜底 5s; LLM 思考/MCP 调用稍微慢点就会 5s read timeout 断流.
    - timeout / limits 全部从 settings 读
      (opencode_client_timeout_*, opencode_client_max_*):
      * connect 10s 容忍 opencode serve 启动慢
      * read 300s 容忍长 LLM 调用 (含多步工具调用/MCP)
      * write 10s 容忍小 body 上传慢
      * pool 5s 容忍连接池紧张
    - limits 限并发 100 连接 + 100 keepalive, 避免单 agent 占用太多
    """
    s = _settings()
    if s is not None:
        timeout = httpx.Timeout(
            connect=s.opencode_client_timeout_connect,
            read=s.opencode_client_timeout_read,
            write=s.opencode_client_timeout_write,
            pool=s.opencode_client_timeout_pool,
        )
        limits = httpx.Limits(
            max_connections=s.opencode_client_max_connections,
            max_keepalive_connections=s.opencode_client_max_keepalive,
            keepalive_expiry=s.opencode_client_keepalive_expiry,
        )
    else:
        timeout = httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=5.0)
        limits = httpx.Limits(
            max_connections=100,
            max_keepalive_connections=100,
            keepalive_expiry=120.0,
        )
    return httpx.AsyncClient(timeout=timeout, limits=limits)


def get_client(adapter: OpenCodeAdapter, agent_name: str, base_url: str) -> AsyncOpencode:
    """获取或创建指定 Agent+base_url 对应的 AsyncOpencode 客户端。

    以 ``"{agent_name}:{base_url}"`` 为键在适配器内部做缓存，避免重复
    构造底层 HTTP 客户端。

    httpx 客户端**必须**用 ``_build_http_client()`` 注入, 不能用 SDK 默认
    (默认 5s read timeout → 5s 后流式必死). 详细原因见 ``_build_http_client``
    注释。

    Args:
        adapter: 适配器实例，作为客户端缓存宿主。
        agent_name: Agent 名称。
        base_url: opencode serve 的 HTTP 入口。

    Returns:
        缓存或新建的 AsyncOpencode 客户端。
    """
    key = f"{agent_name}:{base_url}"
    if key not in adapter._clients:
        s = _settings()
        if s is not None:
            logger.info(
                "opencode_client_created",
                key=key,
                timeout_connect=s.opencode_client_timeout_connect,
                timeout_read=s.opencode_client_timeout_read,
            )
        else:
            logger.info(
                "opencode_client_created",
                key=key,
                timeout_connect=10.0,
                timeout_read=300.0,
            )
        adapter._clients[key] = AsyncOpencode(
            base_url=base_url,
            http_client=_build_http_client(),
        )
    return adapter._clients[key]


def _resolve_tool_names(adapter: OpenCodeAdapter, tools: Any) -> dict[str, bool] | None:
    """把 caller 传的 tools 列表 (str / MCPTool / 混合) 归一化为 opencode 格式.

    历史 caller 直接传 ``list[str]`` (scenario ``injection.final_tools``);
    也有传 ``MCPTool`` 对象 (历史 test 路径). 这里都兼容, 避免在
    opencode chat 里 ``t.name`` 触发 ``AttributeError``.

    额外 always-add: 框架级工具 ``ask_user`` (AUIP 卡片). 它是 Hub 注册的
    synthetic tool, opencode MCP 也有对应本地 command. 不加到 tool_list 里
    LLM 看不见, 不会调, 流就提前断.
    """
    if not tools:
        return None
    names: list[str] = []
    for t in tools:
        if isinstance(t, str):
            names.append(t)
            if t in _FEIHE_TRAVEL_TOOLS:
                names.append(f"feihe-travel_{t}")
        else:
            name = getattr(t, "name", None)
            if name:
                name_str = str(name)
                names.append(name_str)
                if name_str in _FEIHE_TRAVEL_TOOLS:
                    names.append(f"feihe-travel_{name_str}")
    if not names:
        return None
    # 框架级工具: ask_user (AUIP 卡片). Hub 注册的 synthetic tool,
    # 同时 opencode MCP 也配了对应本地 command (policy.mcp_servers.ask_user).
    # 必须让 LLM 知道有这个 tool 可调, 它才会调, 我们 stream_chat 才能在
    # tool_use 事件里检测到, 转成 card SSE 发前端.
    if "ask_user" not in names:
        names.append("ask_user")
    # opencode-ai SDK 的 chat() 收 tools: Dict[str, bool] (tool_name → 是否启用),
    # 不是 list[ToolDefinition]. 见 site-packages/opencode_ai/resources/session.py:602.
    # 走 Dict 是 opencode 故意为之: tool schema 走 opencode config (provider 段),
    # chat 请求只声明"启用哪些", 跟自带 tool / MCP tool 解耦.
    result = dict.fromkeys(_OPENCODE_BUILTIN_TOOLS, False)
    result.update(dict.fromkeys(names, True))
    logger.debug("opencode_tools_resolved", tools_sent=list(result.keys()))
    return result


def _workspace_query(session_info: SessionInfo) -> dict[str, Any]:
    """构造 opencode SDK 的 ``extra_query`` 参数,把会话工作区传给 server.

    opencode server 的 ``WorkspaceRoutingMiddleware`` 接受
    ``?directory=...``,用于:
      - ``InstanceState`` 按目录做 per-project 状态隔离
      - skill 发现从该目录向上扫描
      - 注入到 LLM 的 env 报告中
      - 限制文件/工具访问

    Returns:
        ``{"directory": "/path"}`` 当 session 绑定了工作区;否则空 dict。
    """
    if session_info.directory:
        return {"directory": session_info.directory}
    return {}


def _build_runtime_context(
    base_system_prompt: str | None,
    mcp_token: str | None,
) -> str | None:
    """Append runtime guidance without exposing auth secrets to the model."""
    if not mcp_token:
        return base_system_prompt
    ctx = (
        "\n\n<runtime-context>\n"
        "MCP_AUTH: 鉴权由 OpenAgent / opencode 运行时配置处理，凭证来自容器环境变量，"
        "不会也不应该出现在对话内容里。\n"
        "MCP_USAGE: 调航班查询时直接使用原生 MCP 工具 queryFlightBasic / filterFlightList；"
        "不要手写 curl，不要使用 Bash 拼 HTTP 请求，不要用 task 子代理代查，"
        "不要向用户索要或解释 token。\n"
        "MCP_SECURITY: 不要在自然语言回复、卡片、工具参数或日志说明里回显任何 token / key / header 值。\n"
        "AUIP_CARD: 如果 scenario 启用了 ask_user 工具 (查 opencode config.mcp "
        "里有 ask_user 节点), LLM 应调 ask_user(card_type=..., body=...) 发卡片, "
        "**不要**塞 Markdown 表格到 text 事件. card 渲染由 Hub→前端 FlightResultCard 接管.\n"
        "</runtime-context>"
    )
    if base_system_prompt:
        return base_system_prompt + ctx
    return ctx.lstrip("\n")


def _log_payload_kwargs(sdk_kwargs: dict[str, Any]) -> dict[str, Any]:
    """把 SDK 调用的 kwargs(用 ``id=``)翻译成 ``build_opencode_payload`` 用的(用 ``session_id=``)。

    ``opencode_payload_kwargs`` 同时服务两个调用:
      - ``client.session.chat(**sdk_kwargs)``    — SDK,参数名是 ``id``
      - ``build_opencode_payload(**sdk_kwargs)`` — 本地 log 辅助,参数名是 ``session_id``

    这两个签名不一致,所以 log 调用前翻译一次。直接 ``**sdk_kwargs`` 会因
    多余的 ``id=`` 或缺失 ``session_id=`` 抛 ``TypeError``。
    """
    out = {k: v for k, v in sdk_kwargs.items() if k != "id"}
    if "id" in sdk_kwargs:
        out["session_id"] = sdk_kwargs["id"]
    return out


def _build_session_prompt_payload(sdk_kwargs: dict[str, Any]) -> dict[str, Any]:
    """Build the current opencode ``POST /session/{id}/message`` body."""
    provider_id = sdk_kwargs["provider_id"]
    model_id = sdk_kwargs["model_id"]
    if isinstance(model_id, str) and "/" in model_id:
        model_provider, _, bare_model_id = model_id.partition("/")
        if model_provider:
            provider_id = model_provider
        if bare_model_id:
            model_id = bare_model_id
    return {
        "model": {
            "providerID": provider_id,
            "modelID": model_id,
        },
        "parts": sdk_kwargs["parts"],
        "system": sdk_kwargs.get("system"),
        "tools": sdk_kwargs.get("tools"),
    }


async def _post_session_message_raw(
    base_url: str,
    sdk_kwargs: dict[str, Any],
) -> dict[str, Any]:
    """POST chat directly and return raw JSON, avoiding SDK response parsing.

    Retries on two transient error classes:
      * connection / reload errors caught by ``_is_transient_opencode_error``
        (waits for ``/global/health`` to recover between attempts)
      * opencode 1.17.0's first-prompt share-subscriber race
        (ProviderModelNotFoundError / 5xx UnknownError) caught by
        ``_is_opencode_session_init_race`` — short backoff so the session's
        internal model binding settles, then retry the same POST.
    """
    payload = _build_session_prompt_payload(sdk_kwargs)
    params = sdk_kwargs.get("extra_query") or {}
    last_error: Exception | None = None
    # Up to 3 attempts total: 1 original + up to 2 retries.
    # Each retry handles a different transient class — one
    # connect/reload class (waits for /global/health) and one
    # session-init race class (short backoff).
    for attempt in range(3):
        try:
            async with _build_http_client() as client:
                response = await client.post(
                    f"{base_url}/session/{sdk_kwargs['id']}/message",
                    params=params,
                    json=payload,
                    timeout=sdk_kwargs.get("timeout"),
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            last_error = e
            if _is_transient_opencode_error(e):
                logger.warning(
                    "opencode_message_post_transient_retry",
                    session_id=sdk_kwargs.get("id"),
                    attempt=attempt,
                    error=str(e),
                )
                await _wait_opencode_health(base_url, timeout_seconds=5.0)
            elif _is_opencode_session_init_race(e):
                logger.warning(
                    "opencode_message_post_init_race_retry",
                    session_id=sdk_kwargs.get("id"),
                    attempt=attempt,
                    error=str(e),
                )
                # Short backoff — model binding usually settles in <500ms.
                await asyncio.sleep(0.4 * (attempt + 1))
            else:
                raise
    raise last_error or RuntimeError("opencode message post failed")


def _tool_part_to_result(part: dict[str, Any]) -> StreamEvent | None:
    """Convert a raw opencode completed tool part into StreamEvent.tool_result."""
    if part.get("type") != "tool":
        return None
    state = part.get("state") if isinstance(part.get("state"), dict) else {}
    if state.get("status") != "completed":
        return None
    return StreamEvent.tool_result(
        tool_name=part.get("tool", "unknown"),
        output=state.get("output", ""),
    )


# ---------------------------------------------------------------------------
# Chat dispatch
# ---------------------------------------------------------------------------


async def blocking_chat(
    adapter: OpenCodeAdapter,
    session_id: str,
    messages: list[ChatMessage],
    *,
    model: str | None = None,
    system_prompt: str | None = None,
    tools: list[Any] | None = None,
    timeout: float | None = None,
    mcp_token: str | None = None,
) -> ChatResult:
    """阻塞式 chat——调用 SDK 并解析最终响应返回 ChatResult。

    Args:
        adapter: 适配器实例。
        session_id: 目标会话 ID。
        messages: 完整消息列表。
        model: 可选模型覆盖。
        system_prompt: 可选系统提示词（本实现未使用）。
        tools: 可选工具列表。
        timeout: 可选超时秒数。

    Returns:
        ChatResult；包含助手回复、工具调用或失败时的错误信息。
    """
    logger.info(
        "opencode_chat_start",
        session_id=session_id,
        message_count=len(messages),
        has_mcp_token=bool(mcp_token),
        mcp_token_len=len(mcp_token) if mcp_token else 0,
    )
    session_info = adapter._sessions.get(session_id)
    if not session_info:
        logger.error("opencode_chat_session_not_found", session_id=session_id)
        return ChatResult(
            success=False,
            message=ChatMessage(role="assistant", content=""),
            error=f"Session '{session_id}' not found",
            session_id=session_id,
            agent_name="",
        )

    agent_name = session_info.agent_name

    # 把 per-request mcp_token 推到 opencode 容器 env, 让 feihe-travel MCP
    # 调外部 HTTP 时带 `token: <value>` 头. 仅在 token 变化时写 + reload,
    # 避免每条 chat 都触发 opencode 重启. 失败仅 warn, 不抛.
    if mcp_token:
        token_changed = await _push_flight_token_to_opencode(
            agent_base_url=session_info.agent_base_url,
            mcp_token=mcp_token,
        )
        if token_changed:
            await _close_cached_opencode_client(
                adapter,
                agent_name,
                session_info.agent_base_url,
            )

    client = get_client(adapter, agent_name, session_info.agent_base_url)

    # Build last user message
    last_content = ""
    for msg in reversed(messages):
        if msg.role == "user":
            last_content = msg.content
            break

    # Build parts
    import uuid
    parts = [{"type": "text", "text": last_content, "id": f"prt_{str(uuid.uuid4())[:20]}"}]

    # Convert tools (callers may pass strings or MCPTool objects)
    tool_list = _resolve_tool_names(adapter, tools)

    opencode_payload_kwargs = {
        "id": session_id,  # SDK param 名是 id,不是 session_id (Python kwarg 校验)
        "model_id": model or session_info.model or "default",
        # providerID 必须是 opencode config.json 里 "provider" 块声明的名字.
        # 当前用 openai-compatible 接口 (OPENAI_BASE_URL 指向 minimax),
        # render_config.py 渲染出来的 config 里 provider 名是 "openai".
        # 早期这里误写成 "opencode" (opencode 自己的 brand), 会被 opencode server
        # 当成查不到的 provider → 400 Bad Request.
        "provider_id": "openai",
        "parts": parts,
        "system": _build_runtime_context(system_prompt, mcp_token),
        "tools": tool_list,
        "timeout": timeout,
        "extra_query": _workspace_query(session_info),
    }

    log_opencode_request(build_opencode_payload(**_log_payload_kwargs(opencode_payload_kwargs)))

    try:
        result = await client.session.chat(**opencode_payload_kwargs)
    except Exception as e:
        if _is_transient_opencode_error(e):
            logger.warning(
                "opencode_chat_transient_retry",
                session_id=session_id,
                error=str(e),
            )
            await _close_cached_opencode_client(
                adapter,
                agent_name,
                session_info.agent_base_url,
            )
            await _wait_opencode_health(session_info.agent_base_url, timeout_seconds=5.0)
            client = get_client(adapter, agent_name, session_info.agent_base_url)
            try:
                result = await client.session.chat(**opencode_payload_kwargs)
            except Exception as retry_err:
                logger.error(
                    "opencode_chat_failed",
                    session_id=session_id,
                    error=str(retry_err),
                )
                return ChatResult(
                    success=False,
                    message=ChatMessage(role="assistant", content=""),
                    error=str(retry_err),
                    session_id=session_id,
                    agent_name=agent_name,
                )
        else:
            logger.error("opencode_chat_failed", session_id=session_id, error=str(e))
            return ChatResult(
                success=False,
                message=ChatMessage(role="assistant", content=""),
                error=str(e),
                session_id=session_id,
                agent_name=agent_name,
            )

    msg_dict = result.model_dump() if hasattr(result, "model_dump") else {}
    reply = ""
    for part in msg_dict.get("parts", []):
        if part.get("type") == "text":
            reply = part.get("text", "")

    tool_calls = []
    for part in msg_dict.get("parts", []):
        if part.get("type") == "tool_use":
            tool_calls.append(ToolCall(
                id=part.get("id", ""),
                name=part.get("name", ""),
                input=part.get("input", {}),
            ))

    chat_msg = ChatMessage(role="assistant", content=reply)
    await adapter._storage.create_message(StorageMessage(
        session_id=session_id,
        role="assistant",
        content=reply,
    ))

    logger.info(
        "opencode_chat_completed",
        session_id=session_id,
        agent_name=agent_name,
        tool_call_count=len(tool_calls),
    )
    return ChatResult(
        success=True,
        message=chat_msg,
        stop_reason=msg_dict.get("stop_reason"),
        session_id=session_id,
        agent_name=agent_name,
        tool_calls=tool_calls,
    )


async def stream_chat(
    adapter: OpenCodeAdapter,
    session_id: str,
    messages: list[ChatMessage],
    *,
    model: str | None = None,
    system_prompt: str | None = None,
    tools: list[Any] | None = None,
    timeout: float | None = None,
    mcp_token: str | None = None,
) -> AsyncIterator[StreamEvent]:
    """Stream chat progress in real time via the opencode-ai event bus.

    Per the official opencode-ai SDK docs, real-time streaming is achieved
    by subscribing to the long-lived ``client.event.list()`` SSE stream
    and filtering events for the target session. We do NOT parse HTTP
    response bodies from ``client.session.chat()`` — that endpoint
    buffers until completion, defeating the purpose of streaming.

    The flow is:
        1. Open ``client.event.list()`` (a typed ``AsyncStream`` of
           ``EventListResponse`` Pydantic models — discriminated union of
           ``message.updated``, ``message.part.updated``, ``session.idle``,
           ``session.error``, etc.).
        2. Fire ``client.session.chat(...)`` as a background task — this
           triggers the model run on the opencode serve side.
        3. Iterate the event stream; map relevant events to ``StreamEvent``
           via ``map_opencode_event``. Filter by ``session_id`` and only
           forward parts whose ``message_id`` belongs to an assistant
           message we've already seen in a ``message.updated`` event.
        4. Break the loop on the ``OPENCODE_STREAM_END`` sentinel, which
           is produced when ``session.idle`` (or ``session.error``) fires
           for our session.
        5. Close the event stream, await the chat task, and persist the
           final assistant text to storage for history retrieval.

    Args:
        adapter: 适配器实例。
        session_id: 目标会话 ID。
        messages: 完整消息列表。
        model: 可选模型覆盖。
        system_prompt: 可选系统提示词（本实现未使用）。
        tools: 可选工具列表。
        timeout: 可选超时秒数。

    Yields:
        StreamEvent 流。
    """
    logger.info(
        "opencode_stream_start",
        session_id=session_id,
        message_count=len(messages),
        has_mcp_token=bool(mcp_token),
        mcp_token_len=len(mcp_token) if mcp_token else 0,
    )
    session_info = adapter._sessions.get(session_id)
    if not session_info:
        logger.error("opencode_stream_session_not_found", session_id=session_id)
        yield StreamEvent.error(message=f"Session '{session_id}' not found")
        return

    agent_name = session_info.agent_name

    # 把 per-request mcp_token 推到 opencode 容器 env, 让 feihe-travel MCP
    # 调外部 HTTP 时带 `token: <value>` 头. 仅在 token 变化时写 + reload,
    # 避免每条 chat 都触发 opencode 重启. 失败仅 warn, 不抛.
    if mcp_token:
        token_changed = await _push_flight_token_to_opencode(
            agent_base_url=session_info.agent_base_url,
            mcp_token=mcp_token,
        )
        if token_changed:
            await _close_cached_opencode_client(
                adapter,
                agent_name,
                session_info.agent_base_url,
            )

    client = get_client(adapter, agent_name, session_info.agent_base_url)

    last_content = ""
    for msg in reversed(messages):
        if msg.role == "user":
            last_content = msg.content
            break

    import uuid
    parts = [{"type": "text", "text": last_content, "id": f"prt_{str(uuid.uuid4())[:20]}"}]

    tool_list = _resolve_tool_names(adapter, tools)

    yield StreamEvent.session(session_id=session_id, agent_name=agent_name)

    # State for event filtering / dedup.
    assistant_message_ids: set[str] = set()
    last_text: str = ""
    accumulated_text: str = ""

    opencode_payload_kwargs = {
        "id": session_id,  # SDK param 名是 id,不是 session_id (Python kwarg 校验)
        "model_id": model or session_info.model or "default",
        # providerID 必须是 opencode config.json 里 "provider" 块声明的名字.
        # 当前用 openai-compatible 接口 (OPENAI_BASE_URL 指向 minimax),
        # render_config.py 渲染出来的 config 里 provider 名是 "openai".
        # 早期这里误写成 "opencode" (opencode 自己的 brand), 会被 opencode server
        # 当成查不到的 provider → 400 Bad Request.
        "provider_id": "openai",
        "parts": parts,
        "system": _build_runtime_context(system_prompt, mcp_token),
        "tools": tool_list,
        "timeout": timeout,
        "extra_query": _workspace_query(session_info),
    }
    log_opencode_request(build_opencode_payload(**_log_payload_kwargs(opencode_payload_kwargs)))

    try:
        # 关键优化: 复用长连接 — OpenCodeEventHub 给每 (agent, base_url) 维护
        # 1 条持久的 client.event.list() SSE, N 个 chat 调用订阅同一流, 通过
        # per-caller queue 扇出. 避免每次 chat 都新建 SSE (50-200ms 握手 + 偶现
        # opencode 服务端 idle timeout 提前断).
        #
        # P0-1 还加了显式 httpx.Timeout(connect=10/read=300/...) 防止 5s 兜底超时.
        from openagent.providers.opencode_event_hub import OpenCodeEventHub

        hub: OpenCodeEventHub = getattr(adapter, "_event_hub", None) or OpenCodeEventHub()
        # 缓存在 adapter 上, 跨 chat 调用复用
        with contextlib.suppress(Exception):
            adapter._event_hub = hub

        chat_task: asyncio.Task | None = None
        try:
            # 1. 先订阅 hub (复用或新建长连接) — 让 share-subscriber race 触发的
            # session.error 事件能先于我们的 POST 看到, 我们可以拦截并屏蔽.
            async with hub.subscription(
                agent_name=agent_name,
                base_url=session_info.agent_base_url,
                client=client,
                session_id=session_id,
            ) as sub_iter:
                # 2. 启动 chat 后台任务 (不等结果, 持续发到 opencode serve)
                # 注意: opencode 1.17.0 在新 session 第一次 POST /message 时
                # share subscriber 阶段会偶发 ProviderModelNotFoundError race,
                # _post_session_message_raw 内部有 retry 兜底. 如果 race 真的
                # 失败了, opencode 会把错误包装成 ``session.error`` 事件
                # (name=UnknownError) 通过 SSE 推到客户端 — 这条事件不能透传给
                # 前端, 否则前端看到 "UnknownError" 就当作 chat 失败, 哪怕
                # 后续重试实际成功了. 所以 background task 的最终结果由 finally
                # 块统一处理, 抑制 race 期间的错误.
                chat_task = asyncio.create_task(
                    _post_session_message_raw(
                        session_info.agent_base_url,
                        opencode_payload_kwargs,
                    )
                )

                async for event in sub_iter:
                    mapped = map_opencode_event(event, session_id, assistant_message_ids)
                    if mapped is OPENCODE_STREAM_END:
                        break
                    if mapped is None:
                        continue
                    # session.error in the first ~1s after POST /message is the
                    # opencode 1.17.0 share-subscriber race fingerprint. Wait
                    # briefly for the background ``chat_task`` to finish its
                    # retry; if it succeeds, the race was transient and we
                    # should NOT surface the synthetic ``UnknownError`` to
                    # the client. If the task already failed (no retry left)
                    # we fall through and let the error flow out normally.
                    if (
                        mapped.type == "error"
                        and chat_task is not None
                        and not chat_task.done()
                    ):
                        with contextlib.suppress(Exception):
                            await asyncio.wait_for(
                                asyncio.shield(chat_task),
                                timeout=3.0,
                            )
                        if chat_task.done() and chat_task.exception() is None:
                            logger.info(
                                "opencode_session_error_swallowed_init_race",
                                session_id=session_id,
                            )
                            continue
                    # Dedup text updates: the SDK sends the full text so far
                    # on every ``message.part.updated`` for a text part.
                    if mapped.type == "text":
                        text = mapped.data.get("content", "") or ""
                        if text == last_text:
                            continue
                        last_text = text
                        accumulated_text = text
                    # ask_user (AUIP 卡片): opencode 把它当 native tool 调本地脚本,
                    # 实际 card 渲染走 SSE 转 — Hub 把 tool_use 翻译成 card 事件.
                    if mapped.type == "tool_use" and mapped.data.get("tool_name") == "ask_user":
                        import uuid
                        card_input = mapped.data.get("input", {}) or {}
                        yield StreamEvent.card(
                            card_id=f"card-{uuid.uuid4().hex[:12]}",
                            card_type=card_input.get("card_type", "CHAT_FALLBACK"),
                            card=card_input,
                        )
                        # 仍然 yield tool_use, 让 LLM 看到 ask_user 被调了 (status=running)
                        yield mapped
                        continue
                    # Hub 端兜底: LLM 调 queryFlightBasic 后, Hub 自动拼 FLIGHT_RESULT
                    # 卡片 (LLM 不需要知道 AUIP 存在). minimax-M3 这类弱模型即使 system
                    # 提示了也倾向把航班塞 text 事件, 不主动调 ask_user — Hub 替它做
                    # 结构化工作, 前端照样收 card 事件渲染 FlightResultCard.
                    if (
                        mapped.type == "tool_result"
                        and mapped.data.get("tool_name") == "feihe-travel_queryFlightBasic"
                    ):
                        if session_id in _FLIGHT_CARD_EMITTED:
                            continue
                        from openagent.auip.flight_card import maybe_assemble_flight_card

                        card = maybe_assemble_flight_card(
                            tool_name=mapped.data["tool_name"],
                            output=mapped.data.get("output"),
                        )
                        if card is not None:
                            _FLIGHT_CARD_EMITTED.add(session_id)
                            logger.info(
                                "flight_card_emitted",
                                session_id=session_id,
                                card_id=card.card_id,
                                plan_count=len(card.body.get("plans", [])),
                            )
                            yield StreamEvent.card(
                                card_id=card.card_id,
                                card_type=card.card_type.value,
                                card={"title": card.title, "body": card.body},
                            )
                            continue
                    yield mapped
        finally:
            # chat_task 在 stream 自然结束后, 我们还需要 await 它 (拿到可能的异常)
            if chat_task is not None:
                try:
                    if chat_task.done():
                        # task.result() 同步取结果 — 若上游 500 抛 HTTPStatusError,
                        # 走下方 except 分支转 SSE error, 不要再让 finally 冒泡,
                        # 否则 GeneratorExit / CancelledError 会跟它叠加成
                        # "During handling of the above exception, another exception"。
                        try:
                            raw_result = chat_task.result()
                        except Exception as task_err:
                            logger.warning(
                                "opencode_chat_task_failed",
                                session_id=session_id,
                                error=str(task_err),
                            )
                            yield StreamEvent.error(
                                message=f"opencode upstream error: {task_err}",
                                code="OPENCODE_UPSTREAM_ERROR",
                                retry=2000,
                            )
                            return
                    else:
                        # 客户端在 stream 还没自然结束时断开 (GeneratorExit 路径) —
                        # 不能 await 未完成的任务, 否则 GeneratorExit 会在 await 之后
                        # 再次抛出, 与 _post_session_message_raw 的 500 异常叠加成
                        # "During handling of the above exception, another exception"。
                        # 这里主动 cancel + swallow, 让 GeneratorExit 正常传播。
                        chat_task.cancel()
                        try:
                            await chat_task
                        except (asyncio.CancelledError, Exception):
                            pass
                        return
                    for part in raw_result.get("parts", []):
                        if not isinstance(part, dict):
                            continue
                        if part.get("type") == "text":
                            text = part.get("text", "") or ""
                            if text and text != accumulated_text:
                                yield StreamEvent.text(content=text)
                                accumulated_text = text
                        mapped_part = _tool_part_to_result(part)
                        if mapped_part is None:
                            continue
                        if mapped_part.data.get("tool_name") == "feihe-travel_queryFlightBasic":
                            if session_id in _FLIGHT_CARD_EMITTED:
                                continue
                            from openagent.auip.flight_card import maybe_assemble_flight_card

                            card = maybe_assemble_flight_card(
                                tool_name=mapped_part.data["tool_name"],
                                output=mapped_part.data.get("output"),
                            )
                            if card is not None:
                                _FLIGHT_CARD_EMITTED.add(session_id)
                                yield StreamEvent.card(
                                    card_id=card.card_id,
                                    card_type=card.card_type.value,
                                    card={"title": card.title, "body": card.body},
                                )
                                continue
                        yield mapped_part
                except Exception as task_err:
                    logger.warning(
                        "opencode_chat_task_failed",
                        session_id=session_id,
                        error=str(task_err),
                        traceback=traceback.format_exc(),
                    )
                    yield StreamEvent.error(message=str(task_err), retry=2000)
    except Exception as e:
        logger.error(
            "opencode_stream_failed",
            session_id=session_id,
            error=str(e),
            traceback=traceback.format_exc(),
        )
        yield StreamEvent.error(message=str(e), retry=2000)
        return

    # Persist the final assistant text for history retrieval.
    if accumulated_text:
        try:
            await adapter._storage.create_message(StorageMessage(
                session_id=session_id,
                role="assistant",
                content=accumulated_text,
            ))
        except Exception as e:
            logger.warning(
                "opencode_stream_persist_failed",
                session_id=session_id,
                error=str(e),
            )
    logger.info("opencode_stream_completed", session_id=session_id, agent_name=agent_name)
