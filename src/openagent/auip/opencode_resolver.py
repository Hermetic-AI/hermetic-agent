"""L3 桥接层: L1 controller 与 L4 providers 的中间桥梁.

opencode-ai Python SDK 还没有 question / todo resource (P7 阶段), OpenAgent
自己包了 ``providers/opencode_native_sdk.py`` (L4). L1 controller 不能
直接 import L4, 也不能被 L4 import. 这里 L3 (auip) 提供纯函数式包装:

- 输入: ``bridge, session_id`` (bridge 来自 L1, 由 caller 提供)
- 输出: ``(client, directory)`` 或调用结果

L3 → L4 (opencode_chat / opencode_native_sdk) **允许**; L1 → L3 **允许**。
本模块不 import L1, 由 caller (L1 controller) 把 bridge 传进来。
"""
from __future__ import annotations

import structlog

from openagent.providers.opencode.chat import get_client
from openagent.providers.opencode.native_sdk import (
    question_list,
    question_reject,
    question_reply,
    todo_list,
)

logger = structlog.get_logger(__name__)


def _is_question_not_found(error: Exception) -> bool:
    text = str(error).lower()
    return "questionnotfounderror" in text or "question request not found" in text or "404" in text


async def resolve_opencode_client(bridge, session_id: str) -> tuple:
    """从 ``bridge`` + ``session_id`` 找 ``AsyncOpencode`` client + directory.

    async: OpenCodeAdapter.get_session 是 async, 必须 await. 早期写成 sync 时
    返回的是 coroutine 不是 SessionInfo, 下游 ``session_info.directory`` 直接
    AttributeError. (踩坑修过: opencode_resolver.py:40)

    Returns:
        ``(client, directory)`` 二元组; 任何一步失败都返回 ``(None, None)``。
    """
    agent_name = bridge.get_agent_for_session(session_id)
    if agent_name is None:
        return None, None
    adapter = bridge.get_provider(agent_name)
    if adapter is None:
        return None, None
    if not hasattr(adapter, "get_session"):
        return None, None
    session_info = await adapter.get_session(session_id)
    if session_info is None:
        return None, None
    directory = session_info.directory
    client = get_client(adapter, agent_name, session_info.agent_base_url)
    return client, directory


async def list_questions_for_session(bridge, session_id: str) -> list[dict]:
    """``GET /question`` 代理, 失败时返空 list, 不抛错给 L1."""
    client, directory = await resolve_opencode_client(bridge, session_id)
    if client is None:
        return []
    try:
        return await question_list(client, directory=directory)
    except Exception as e:
        logger.error("auip_question_list_failed", session_id=session_id, error=str(e))
        return []


async def reply_question(
    bridge, request_id: str, session_id: str, answers: list[list[str]]
) -> tuple[bool, str | None]:
    """``POST /question/:id/reply`` 代理. ``(ok, err_msg)`` 形式返回."""
    client, directory = await resolve_opencode_client(bridge, session_id)
    if client is None:
        return False, f"Session '{session_id}' not found"
    try:
        ok = await question_reply(client, request_id, answers, directory=directory)
        return ok, None
    except Exception as e:
        if directory and _is_question_not_found(e):
            try:
                logger.warning(
                    "auip_question_reply_retry_without_directory",
                    request_id=request_id,
                    session_id=session_id,
                    directory=directory,
                    error=str(e),
                )
                ok = await question_reply(client, request_id, answers, directory=None)
                return ok, None
            except Exception:
                pass
        logger.error("auip_question_reply_failed", request_id=request_id, error=str(e))
        return False, f"opencode /question/:id/reply failed: {e}"


async def reject_question(
    bridge, request_id: str, session_id: str
) -> tuple[bool, str | None]:
    """``POST /question/:id/reject`` 代理."""
    client, directory = await resolve_opencode_client(bridge, session_id)
    if client is None:
        return False, f"Session '{session_id}' not found"
    try:
        ok = await question_reject(client, request_id, directory=directory)
        return ok, None
    except Exception as e:
        if directory and _is_question_not_found(e):
            try:
                logger.warning(
                    "auip_question_reject_retry_without_directory",
                    request_id=request_id,
                    session_id=session_id,
                    directory=directory,
                    error=str(e),
                )
                ok = await question_reject(client, request_id, directory=None)
                return ok, None
            except Exception:
                pass
        logger.error("auip_question_reject_failed", request_id=request_id, error=str(e))
        return False, f"opencode /question/:id/reject failed: {e}"


async def list_todos_for_session(
    bridge, session_id: str
) -> tuple[list[dict] | None, str | None]:
    """``GET /session/:id/todo`` 代理. ``(todos, None)`` 或 ``(None, err)``."""
    client, directory = await resolve_opencode_client(bridge, session_id)
    if client is None:
        return None, f"Session '{session_id}' not found"
    try:
        todos = await todo_list(client, session_id, directory=directory)
        return todos, None
    except Exception as e:
        logger.error("auip_todo_list_failed", session_id=session_id, error=str(e))
        return None, f"opencode /session/:id/todo failed: {e}"


__all__ = [
    "resolve_opencode_client",
    "list_questions_for_session",
    "reply_question",
    "reject_question",
    "list_todos_for_session",
]
