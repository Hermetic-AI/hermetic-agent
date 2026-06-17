"""BusiLogger 门面 — 仿照 fh-ai app/commons/log/busiLogger.

业务日志: ``busiLogger.info("chat_request", session_id=...)`` 走这条路.

字段填充规则:
- ``type = "BUSI_LOG_" + logSystemType.upper()``  (例 ``BUSI_LOG_OPENAGENT``)
- ``instanceId / reqSeqNo / startTime`` 从 ContextVar / ``seq_no`` 取
- ``logTime = datetime.now()``
- ``level`` 来自 ``info/warning/error/debug``
- ``programLine = "类:方法(行号)"`` 形态 (从调用栈取)
- ``threadName = threading.current_thread().name``
- ``logInfo = 整个 event + kwargs`` 序列化成 str
- ``memo = logInfo 前 200 字符`` (脱敏后展示用)
- ``logId = get_date_seq_no("LOG_ID")``

**退路**: ``ObjectLogWriter`` 未初始化 (单元测试 / 不接平台) 时所有调用 no-op.
"""
from __future__ import annotations

import inspect
import json
import threading
from datetime import datetime
from typing import Any

from openagent.audit.log.dto import BusiLog
from openagent.audit.log.log_compress import maybe_compress
from openagent.audit.log.log_context import get_request_id, get_request_time
from openagent.audit.log.object_log_writer import ObjectLogWriter
from openagent.audit.log.seq_no import get_date_seq_no, get_instance_id

_PROGRAM_LINE_DEPTH = 8
_SKIP_MODULES = ("openagent.audit.log.",)


def _program_line() -> str:
    """从调用栈取最近的业务调用点 (``文件:函数(行号)`` 形态)."""
    try:
        frame = inspect.currentframe()
        for _ in range(_PROGRAM_LINE_DEPTH):
            if frame is None:
                break
            frame = frame.f_back
        if frame is None:
            return ""
        co = frame.f_code
        return f"{co.co_filename.rsplit('/', 1)[-1]}:{co.co_name}({frame.f_lineno})"
    except Exception:
        return ""


def _build_log_info(event: str, kwargs: dict[str, Any]) -> str:
    payload = {"event": event, **kwargs}
    try:
        return json.dumps(payload, ensure_ascii=False, default=str)
    except Exception:
        return str(payload)


class BusiLogger:
    def __init__(self, log_system_type: str) -> None:
        self._type_prefix = f"BUSI_LOG_{log_system_type.upper()}"

    @property
    def type_prefix(self) -> str:
        return self._type_prefix

    def _build(self, level: str, event: str, kwargs: dict[str, Any]) -> BusiLog:
        log_info_str = _build_log_info(event, kwargs)
        info, size, compress = maybe_compress(log_info_str)
        memo = log_info_str[:200]
        return BusiLog(
            type=self._type_prefix,
            instanceId=get_instance_id(),
            reqSeqNo=get_request_id(),
            logTime=datetime.now(),
            startTime=get_request_time(),
            level=level,
            programLine=_program_line(),
            threadName=threading.current_thread().name,
            memo=memo,
            logInfo=info,
            infoSize=size,
            compress=compress,
            logId=get_date_seq_no("LOG_ID"),
        )

    def _emit(self, level: str, event: str, kwargs: dict[str, Any]) -> None:
        writer = ObjectLogWriter.get_instance()
        if writer is None:
            return
        writer.write_busi(self._build(level, event, kwargs))

    def info(self, event: str, **kwargs: Any) -> None:
        self._emit("INFO", event, kwargs)

    def warning(self, event: str, **kwargs: Any) -> None:
        self._emit("WARN", event, kwargs)

    def error(self, event: str, **kwargs: Any) -> None:
        self._emit("ERROR", event, kwargs)

    def debug(self, event: str, **kwargs: Any) -> None:
        self._emit("DEBUG", event, kwargs)


_busi_logger: BusiLogger | None = None


def get_busi_logger() -> BusiLogger | None:
    return _busi_logger


def init_busi_logger(log_system_type: str) -> BusiLogger:
    global _busi_logger
    _busi_logger = BusiLogger(log_system_type)
    return _busi_logger
