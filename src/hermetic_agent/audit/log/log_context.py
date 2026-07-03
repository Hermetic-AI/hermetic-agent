"""LogContext — 仿照 fh-ai app/commons/log/logContext.

3 个 ContextVar:
- :data:`REQUEST_ID`   当前请求的 reqSeqNo (busilogger 自动注入)
- :data:`REQUEST_TIME` 当前请求的开始时间
- :data:`IS_LOG`       是否需要记录 (middleware 设 True, 业务代码无需关心)

异步任务 (``asyncio.create_task``) 会丢失 ContextVar 上下文, 这点跟
fh-ai 一致 — 平台追踪会断链, 后台任务入口需重新
:func:`bind_request_context`.
"""
from __future__ import annotations

from contextvars import ContextVar, Token
from datetime import datetime
from typing import NamedTuple

REQUEST_ID: ContextVar[str] = ContextVar("log_request_id", default="")
REQUEST_TIME: ContextVar[datetime | None] = ContextVar(
    "log_request_time", default=None,
)
IS_LOG: ContextVar[bool] = ContextVar("log_is_log", default=False)


def get_request_id() -> str:
    return REQUEST_ID.get()


def get_request_time() -> datetime:
    t = REQUEST_TIME.get()
    if t is None:
        return datetime.now()
    return t


def get_is_log() -> bool:
    return IS_LOG.get()


class _Tokens(NamedTuple):
    req_id: Token[str]
    req_time: Token[datetime | None]
    is_log: Token[bool]


def bind_request_context(req_id: str, start_time: datetime) -> _Tokens:
    """绑定当前请求的 req_id + start_time, 返回 tokens 用于后续 reset."""
    return _Tokens(
        req_id=REQUEST_ID.set(req_id),
        req_time=REQUEST_TIME.set(start_time),
        is_log=IS_LOG.set(True),
    )


def clear_request_context(tokens: _Tokens) -> None:
    """``bind_request_context`` 的反向操作, 必须在 ``finally`` 块调用."""
    REQUEST_ID.reset(tokens.req_id)
    REQUEST_TIME.reset(tokens.req_time)
    IS_LOG.reset(tokens.is_log)


class LogContext:
    """对外暴露的 namespace 形式, 让 ``from hermetic_agent.audit.log import
    LogContext`` 也能拿到上下文工具 (跟 fh-ai ``LogContext`` 类对位)."""

    get_request_id = staticmethod(get_request_id)
    get_request_time = staticmethod(get_request_time)
    get_is_log = staticmethod(get_is_log)
    bind_request_context = staticmethod(bind_request_context)
    clear_request_context = staticmethod(clear_request_context)
