"""opencode native Question / Todo 端点的轻量包装 (L4).

opencode-sdk-python v0.x **没有**生成 question / todo resource
(只有 app, config, event, file, find, session, tui). 复用已有的
``AsyncOpencode`` 客户端, 把 4 个原生端点按 SDK 风格包成 4 个函数。

镜像自 opencode 源码:
- ``GET  /question?directory=...``                    -> 列 pending
- ``POST /question/{requestID}/reply?directory=...``  -> 提交 answers
- ``POST /question/{requestID}/reject?directory=...`` -> 忽略/拒绝
- ``GET  /session/{sessionID}/todo?directory=...``    -> 任务清单

使用::

    from openagent.providers.opencode_chat import get_client
    from openagent.providers.opencode_native_sdk import question_list, todo_list

    client = get_client(adapter, agent_name, base_url)
    pending = await question_list(client, directory=session_info.directory)
"""
from __future__ import annotations

from typing import Any

import httpx
import structlog

try:
    from opencode_ai import AsyncOpencode
except ImportError:  # pragma: no cover
    from openagent._vendor.opencode import AsyncOpencode  # type: ignore

logger = structlog.get_logger(__name__)


def _options(*, directory: str | None = None, timeout: float | None = None) -> dict:
    """构造 SDK ``RequestOptions`` 字典, 避免 import 私有 ``_base_client``."""
    out: dict = {}
    if directory:
        out["extra_query"] = {"directory": directory}
    if timeout is not None:
        out["timeout"] = timeout
    return out


async def _do_get(
    client: AsyncOpencode, path: str, *, directory: str | None = None, timeout: float | None = None
) -> Any:
    """GET, ``cast_to=httpx.Response`` 拿原始 Response 自己解析 (跳 Pydantic)."""
    res = await client.get(path, cast_to=httpx.Response, options=_options(directory=directory, timeout=timeout))
    if not res.content:
        return None
    return res.json()


async def _do_post(
    client: AsyncOpencode, path: str, body: dict, *, directory: str | None = None, timeout: float | None = None
) -> httpx.Response:
    """POST, 返回原始 Response. 4xx/5xx 已被 SDK raise_for_status."""
    return await client.post(path, body=body, cast_to=httpx.Response, options=_options(directory=directory, timeout=timeout))


# ---- Question ------------------------------------------------------------

async def question_list(client: AsyncOpencode, *, directory: str | None = None, timeout: float | None = None) -> list[dict]:
    """``GET /question`` — 列出全部 pending question request (opencode 不按 session 过滤)."""
    res = await _do_get(client, "/question", directory=directory, timeout=timeout)
    if res is None:
        return []
    if isinstance(res, list):
        return res
    if isinstance(res, dict):
        return res.get("questions", []) or res.get("data", []) or []
    return []


async def question_reply(client: AsyncOpencode, request_id: str, answers: list[list[str]], *, directory: str | None = None, timeout: float | None = None) -> bool:
    """``POST /question/:id/reply`` — 提交 answers 二维数组."""
    res = await _do_post(client, f"/question/{request_id}/reply", {"answers": answers}, directory=directory, timeout=timeout)
    return res.status_code == 200


async def question_reject(client: AsyncOpencode, request_id: str, *, directory: str | None = None, timeout: float | None = None) -> bool:
    """``POST /question/:id/reject`` — 忽略/拒绝."""
    res = await _do_post(client, f"/question/{request_id}/reject", {}, directory=directory, timeout=timeout)
    return res.status_code == 200


# ---- Todo ----------------------------------------------------------------

async def todo_list(client: AsyncOpencode, session_id: str, *, directory: str | None = None, timeout: float | None = None) -> list[dict]:
    """``GET /session/:id/todo`` — 列出 ``[{content, status, priority}, ...]``."""
    res = await _do_get(client, f"/session/{session_id}/todo", directory=directory, timeout=timeout)
    if res is None:
        return []
    if isinstance(res, list):
        return res
    return []


__all__ = ["question_list", "question_reply", "question_reject", "todo_list"]
