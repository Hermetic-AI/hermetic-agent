"""Lifecycle operations for the Claude Code adapter.

Module-level functions take the adapter instance as the first arg so they
can read its state (clients, sessions, storage). The adapter class in
``claude_code_adapter.py`` is a thin shell that delegates to these
functions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from openagent.providers.base import (
    AgentConfig,
    ChatMessage,
    SessionInfo,
)
from openagent.providers.claude_code.chat import get_or_create_client
from openagent.store.base import Session as StorageSession

try:
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
except ImportError:  # pragma: no cover
    ClaudeAgentOptions = None  # type: ignore
    ClaudeSDKClient = None  # type: ignore

if TYPE_CHECKING:
    from openagent.providers.claude_code.adapter import ClaudeCodeAdapter

logger = structlog.get_logger(__name__)


async def create_session(
    adapter: ClaudeCodeAdapter,
    agent_name: str,
    model: str | None = None,
    system_prompt: str | None = None,
    *,
    base_url: str | None = None,  # ignored for local SDK
    session_id: str | None = None,
) -> SessionInfo:
    """为指定 Agent 分配会话 ID 并建立本地跟踪。

    Claude SDK 内部自行管理会话状态，本层仅跟踪一个外部 ID 用于索引
    历史消息与会话到 Agent 的映射。若提供 ``session_id`` 则复用（resume）；
    否则生成 UUID。

    Args:
        adapter: 适配器实例。
        agent_name: Agent 名称。
        model: 可选模型标识。
        system_prompt: 可选系统提示词（当前未透传，预留扩展）。
        base_url: 本地 SDK 不使用，保留以满足接口。
        session_id: 可选；提供时复用该 ID。

    Returns:
        新建或复用的 SessionInfo。
    """
    logger.info(
        "claude_code_session_create_start",
        agent_name=agent_name,
        has_session_id=bool(session_id),
    )
    try:
        await get_or_create_client(
            adapter,
            AgentConfig(
                name=agent_name,
                base_url=base_url or "local",
                sdk_type="claude_code",
                default_model=model,
            ),
        )
    except Exception as e:
        logger.error("claude_code_client_init_failed", agent_name=agent_name, error=str(e))
        raise

    # The SDK uses a session_id from options or generates one internally.
    # We create a local ID to track this session in our storage.
    if session_id is None:
        import uuid
        session_id = str(uuid.uuid4())

    # Store session info
    session_info = SessionInfo(
        session_id=session_id,
        agent_name=agent_name,
        agent_base_url="local",  # SDK is local
        model=model,
    )
    adapter._sessions[session_id] = session_info
    adapter._session_to_agent[session_id] = agent_name

    # Persist to storage
    session = StorageSession(
        session_id=session_id,
        title="New Session",
        model=model,
        agent_name=agent_name,
    )
    await adapter._storage.create_session(session)

    logger.info(
        "claude_code_session_created",
        session_id=session_id,
        agent_name=agent_name,
    )
    return session_info


async def abort(adapter: ClaudeCodeAdapter, session_id: str) -> bool:
    """中断指定会话的运行任务。

    Args:
        adapter: 适配器实例。
        session_id: 目标会话 ID。

    Returns:
        True 表示中断已下发；会话或客户端不存在时返回 False。
    """
    session_info = adapter._sessions.get(session_id)
    if not session_info:
        return False
    agent_name = session_info.agent_name
    client = adapter._clients.get(agent_name)
    if not client:
        return False
    try:
        await client.interrupt()
        logger.info("claude_code_session_aborted", session_id=session_id)
        return True
    except Exception as e:
        logger.error("claude_code_abort_failed", session_id=session_id, error=str(e))
        return False


async def delete(adapter: ClaudeCodeAdapter, session_id: str) -> bool:
    """删除会话并清理本地跟踪与持久化记录。

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
    try:
        await adapter._storage.delete_session(session_id)
        logger.info("claude_code_session_deleted", session_id=session_id)
        return True
    except Exception as e:
        logger.error("claude_code_delete_failed", session_id=session_id, error=str(e))
        return False


async def get_messages(
    adapter: ClaudeCodeAdapter,
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
    return [
        ChatMessage(role=m.role, content=m.content)
        for m in msgs
    ]


async def get_session(
    adapter: ClaudeCodeAdapter,
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
    """检查本地 Claude Code CLI 是否可用。

    通过启动一个 ``max_turns=1`` 的最小客户端并发送一次 query 验证。
    ``base_url`` 仅作为接口占位参数，本地 SDK 不使用。

    Args:
        base_url: 接口占位参数，忽略。

    Returns:
        True 表示 CLI 可用且能完成一次最小交互。
    """
    if ClaudeSDKClient is None:
        logger.warning("claude_code_health_check_skipped", reason="sdk_not_imported")
        return False
    try:
        opts = ClaudeAgentOptions(max_turns=1)
        test_client = ClaudeSDKClient(options=opts)
        await test_client.connect()
        await test_client.query(prompt="hi", session_id="health-check")
        async for _ in test_client.receive_response():
            pass
        logger.info("claude_code_health_check_ok")
        return True
    except Exception as e:
        logger.warning("claude_code_health_check_failed", error=str(e))
        return False
