"""Lifecycle operations for the OpenCode adapter.

Module-level functions take the adapter instance as the first arg so they
can read its state (clients, sessions, storage). The adapter class in
``opencode_adapter.py`` is a thin shell that delegates to these functions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from openagent.providers.base import (
    AgentConfig,
    ChatMessage,
    SessionInfo,
)
from openagent.store.base import Session as StorageSession

from openagent.providers.opencode_chat import get_client

if TYPE_CHECKING:
    from openagent.providers.opencode_adapter import OpenCodeAdapter

logger = structlog.get_logger(__name__)


def _parse_opencode_model_id(model: str | None) -> dict[str, str] | None:
    """把 ``"MiniMax-M2.7-highspeed"`` 解析成 opencode session 接受的
    ``{"providerID": "openai", "id": "MiniMax-M2.7-highspeed"}``.

    Opencode session.create 端点的 body schema 把 model 字段定义为嵌套对象
    ``{providerID, id, variant?}``. 关键: 它的 ``id`` 字段接受
    ``"<providerID>/<modelID>"`` 拼接字符串 — opencode 内部 share subscriber
    在准备 session-level model 时会按这个拼接格式去查 LLM, 如果只写裸 modelID
    (``"MiniMax-M2.7-highspeed"``) 它会自己再加 ``"openai/"`` 前缀变成
    ``"MiniMax-M2.7-highspeed"`` 存回去, 之后 ``SessionPrompt.getModel``
    拿着这个拼接后的字符串去 provider 注册表查就报 ProviderModelNotFoundError.
    显式在 id 字段里就带 ``<providerID>/`` 前缀能避免 opencode 二次拼接后
    出现找不到的 model.

    Hub 端一直用 ``<provider>/<id>`` 形式 (跟 scenario yaml 和 policy.json
    对齐), 这里在 create 时拆出 provider_id 后**保持 id 字段拼接形式**.

    解析失败 (没斜杠, 空白 model 等) 返回 None, 调用方跳过 model 字段.
    """
    if not model:
        return None
    text = str(model).strip()
    if not text or "/" not in text:
        return None
    provider_id, _, model_id = text.partition("/")
    provider_id = provider_id.strip()
    model_id = model_id.strip()
    if not provider_id or not model_id:
        return None
    return {"providerID": provider_id, "id": f"{provider_id}/{model_id}"}


async def _post_session_create_raw(
    base_url: str,
    *,
    body: dict[str, Any],
    params: dict[str, Any] | None = None,
) -> str:
    """Direct ``POST /session`` to opencode, bypassing the SDK.

    The opencode-ai SDK ``client.session.create()`` does not expose a
    ``body=`` argument and silently drops ``extra_body`` because the
    internal ``FinalRequestOptions`` model does not declare that field.
    We need to send ``{"agent": "build", "model": {...}}`` to lock the
    session-level agent/model at create time, so we have to hit the HTTP
    endpoint directly with httpx.

    Args:
        base_url: opencode serve base URL.
        body: JSON body, e.g. ``{"agent": "build", "model": {...}}``.
        params: Query string, e.g. ``{"directory": "..."}``.

    Returns:
        New session id.

    Raises:
        httpx.HTTPStatusError: Non-2xx response from opencode.
        RuntimeError: Response body missing the session id.
    """
    from openagent.providers.opencode_chat import _build_http_client

    async with _build_http_client() as http:
        resp = await http.post(
            f"{base_url}/session",
            params=params or None,
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
    sid = data.get("id") if isinstance(data, dict) else None
    if not sid:
        raise RuntimeError(f"opencode /session returned no id: {data!r}")
    return str(sid)


async def create_session(
    adapter: "OpenCodeAdapter",
    agent_name: str,
    model: str | None = None,
    system_prompt: str | None = None,
    *,
    base_url: str | None = None,
    session_id: str | None = None,
    directory: str | None = None,
) -> SessionInfo:
    """创建或恢复 OpenCode 会话。

    当未提供 ``session_id`` 时调用 opencode serve 的 session.create
    分配新会话；提供时直接复用。

    当提供 ``directory`` 时,opencode serve 会把会话绑定到该工作区
    (skill 发现、env 报告、文件访问都以此为基准) — 通过 SDK 的
    ``extra_query={"directory": ...}`` 传递,opencode server 的
    ``WorkspaceRoutingMiddleware`` 会接管。

    Args:
        adapter: 适配器实例。
        agent_name: Agent 名称。
        model: 可选模型标识。
        system_prompt: 可选系统提示词（当前未透传）。
        base_url: opencode serve 的 HTTP 入口。
        session_id: 可选；提供时复用该 ID。
        directory: 可选；会话绑定的项目工作区路径(由 scenario 提供)。

    Returns:
        新建或复用的 SessionInfo。

    Raises:
        RuntimeError: 调用 opencode serve 创建会话失败时。
    """
    logger.info(
        "opencode_session_create_start",
        agent_name=agent_name,
        base_url=base_url,
        has_session_id=bool(session_id),
        has_directory=bool(directory),
        has_model=bool(model),
        model=model,
    )
    base_url = base_url or "http://localhost:4096"
    # Warm the SDK client cache even on the raw-HTTP path; abort/delete later
    # in this module still go through the SDK, so they need a cached client.
    get_client(adapter, agent_name, base_url)
    if session_id:
        sid = session_id
    else:
        # session.create 必传 agent+model: opencode 1.17.0 在新会话第一次
        # prompt 时会自动跑内置的 ``title`` agent 生成 session 标题, 它的
        # model 完全继承 session-level. 如果 session-level 没绑, title
        # agent 的 SessionPrompt.getModel 会抛 ProviderModelNotFoundError,
        # share subscriber 阶段先于主 prompt 失败, opencode server 整体
        # 返回 500. 显式把 agent="build" + model={providerID, id} 写在
        # POST /session body 里能消除这个 race.
        #
        # 注意: opencode-ai SDK 的 ``client.session.create()`` 签名只接受
        # extra_headers/extra_query/extra_body/timeout, 内部 base_client.post
        # 把 extra_body 走 ``FinalRequestOptions.construct(**options)`` (这个
        # model 没有 extra_body 字段 → pydantic construct 静默丢弃), 所以
        # extra_body 在 session.create 这种 body=None 场景下其实没发出去.
        # 这里直接走 httpx 发 POST /session 绕开 SDK 限制.
        session_create_body: dict[str, Any] = {
            "agent": "build",
        }
        parsed_model = _parse_opencode_model_id(model)
        if parsed_model is not None:
            session_create_body["model"] = parsed_model
        params: dict[str, Any] = {}
        if directory:
            params["directory"] = directory
        try:
            sid = await _post_session_create_raw(
                base_url, body=session_create_body, params=params,
            )
        except Exception as e:
            logger.error("opencode_session_create_failed", agent_name=agent_name, error=str(e))
            raise RuntimeError(f"Failed to create session: {e}") from e

    session_info = SessionInfo(
        session_id=sid,
        agent_name=agent_name,
        agent_base_url=base_url,
        model=model,
        directory=directory,
    )
    adapter._sessions[sid] = session_info
    adapter._session_to_agent[sid] = agent_name

    session_meta: dict[str, Any] = {}
    if directory:
        session_meta["directory"] = directory
    session = StorageSession(
        session_id=sid,
        title="New Session",
        model=model,
        agent_name=agent_name,
        metadata=session_meta,
    )
    await adapter._storage.create_session(session)

    logger.info(
        "opencode_session_created",
        session_id=sid,
        agent_name=agent_name,
        directory=directory,
    )
    return session_info


async def abort(adapter: "OpenCodeAdapter", session_id: str) -> bool:
    """中断指定会话的运行任务。

    Args:
        adapter: 适配器实例。
        session_id: 目标会话 ID。

    Returns:
        True 表示中断已下发；会话不存在时返回 False。
    """
    session_info = adapter._sessions.get(session_id)
    if not session_info:
        return False
    client = get_client(adapter, session_info.agent_name, session_info.agent_base_url)
    try:
        await client.session.abort(session_id=session_id)
        logger.info("opencode_session_aborted", session_id=session_id)
        return True
    except Exception as e:
        logger.error("opencode_abort_failed", session_id=session_id, error=str(e))
        return False


async def delete(adapter: "OpenCodeAdapter", session_id: str) -> bool:
    """删除会话并清理 opencode serve 端与本地存储。

    Args:
        adapter: 适配器实例。
        session_id: 目标会话 ID。

    Returns:
        True 表示删除成功；会话不存在时返回 False。
    """
    session_info = adapter._sessions.pop(session_id, None)
    if not session_info:
        return False
    adapter._session_to_agent.pop(session_id, None)
    client = get_client(adapter, session_info.agent_name, session_info.agent_base_url)
    try:
        await client.session.delete(session_id=session_id)
        await adapter._storage.delete_session(session_id)
        logger.info("opencode_session_deleted", session_id=session_id)
        return True
    except Exception as e:
        logger.error("opencode_delete_failed", session_id=session_id, error=str(e))
        return False


async def get_messages(
    adapter: "OpenCodeAdapter",
    session_id: str,
) -> list[ChatMessage]:
    """从持久化层读取并转换会话历史消息。

    Args:
        adapter: 适配器实例。
        session_id: 目标会话 ID。

    Returns:
        转换后的 ChatMessage 列表。
    """
    msgs = await adapter._storage.get_messages(session_id)
    return [ChatMessage(role=m.role, content=m.content) for m in msgs]


async def get_session(
    adapter: "OpenCodeAdapter",
    session_id: str,
) -> SessionInfo | None:
    """查询本地跟踪的会话元数据。

    Args:
        adapter: 适配器实例。
        session_id: 目标会话 ID。

    Returns:
        SessionInfo 或 None。
    """
    return adapter._sessions.get(session_id)


async def health_check(base_url: str) -> bool:
    """探测 opencode serve 的 ``/global/health`` 端点.

    跟 opencode 上游 server.mdx 对齐:
        GET /global/health → {"healthy": true, "version": "..."}

    旧版本用 ``/health`` 跟 opencode 内置 healthz 撞名 (那个是 health_server
    启的, 监听 7777), 实际测 :14096/health 永远 404. 改成
    ``/global/health`` 才打到 opencode 真正的 readiness 端点.

    Args:
        base_url: opencode serve 的 HTTP 入口。

    Returns:
        状态码为 200 时返回 True；网络或服务异常时返回 False。
    """
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as http:
            resp = await http.get(f"{base_url}/global/health")
            ok = resp.status_code == 200
            if ok:
                logger.info("opencode_health_check_ok", url=base_url)
            else:
                logger.warning(
                    "opencode_health_check_failed",
                    url=base_url,
                    status_code=resp.status_code,
                )
            return ok
    except Exception as e:
        logger.warning("opencode_health_check_failed", url=base_url, error=str(e))
        return False
