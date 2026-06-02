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


async def create_session(
    adapter: "OpenCodeAdapter",
    agent_name: str,
    model: str | None = None,
    system_prompt: str | None = None,
    *,
    base_url: str | None = None,
    session_id: str | None = None,
) -> SessionInfo:
    """创建或恢复 OpenCode 会话。

    当未提供 ``session_id`` 时调用 opencode serve 的 session.create
    分配新会话；提供时直接复用。

    Args:
        adapter: 适配器实例。
        agent_name: Agent 名称。
        model: 可选模型标识。
        system_prompt: 可选系统提示词（当前未透传）。
        base_url: opencode serve 的 HTTP 入口。
        session_id: 可选；提供时复用该 ID。

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
    )
    base_url = base_url or "http://localhost:4096"
    client = get_client(adapter, agent_name, base_url)
    if session_id:
        sid = session_id
    else:
        try:
            result = await client.session.create()
            sid = result.id if hasattr(result, "id") else str(result)
        except Exception as e:
            logger.error("opencode_session_create_failed", agent_name=agent_name, error=str(e))
            raise RuntimeError(f"Failed to create session: {e}") from e

    session_info = SessionInfo(
        session_id=sid,
        agent_name=agent_name,
        agent_base_url=base_url,
        model=model,
    )
    adapter._sessions[sid] = session_info
    adapter._session_to_agent[sid] = agent_name

    session = StorageSession(
        session_id=sid,
        title="New Session",
        model=model,
        agent_name=agent_name,
    )
    await adapter._storage.create_session(session)

    logger.info("opencode_session_created", session_id=sid, agent_name=agent_name)
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
    """探测 opencode serve 的 ``/health`` 端点。

    Args:
        base_url: opencode serve 的 HTTP 入口。

    Returns:
        状态码为 200 时返回 True；网络或服务异常时返回 False。
    """
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as http:
            resp = await http.get(f"{base_url}/health")
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
