"""SysLogger 门面 — 仿照 fh-ai app/commons/log/sysLogger.

应用/系统级日志 (启动/停止/异常). 当前未在主路径使用, 接口已实现.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from typing import Any

from openagent.audit.log.dto import SysLog
from openagent.audit.log.log_compress import maybe_compress
from openagent.audit.log.log_context import get_request_id
from openagent.audit.log.object_log_writer import ObjectLogWriter
from openagent.audit.log.seq_no import get_date_seq_no, get_instance_id


class SysLogger:
    def __init__(self, log_system_type: str) -> None:
        self._type_prefix = f"APP_LOG_{log_system_type.upper()}"

    @property
    def type_prefix(self) -> str:
        return self._type_prefix

    def _emit(self, level: str, category: str, event: str, kwargs: dict[str, Any]) -> None:
        writer = ObjectLogWriter.get_instance()
        if writer is None:
            return
        payload = {"event": event, **kwargs}
        try:
            log_info_str = json.dumps(payload, ensure_ascii=False, default=str)
        except Exception:
            log_info_str = str(payload)
        info, size, compress = maybe_compress(log_info_str)
        writer.write_sys(
            SysLog(
                type=self._type_prefix,
                level=level,
                instanceId=get_instance_id(),
                logTime=datetime.now(),
                threadId=threading.get_ident(),
                reqSeqNo=get_request_id(),
                category=category,
                threadName=threading.current_thread().name,
                programLine="",
                logInfo=info,
                infoSize=size,
                compress=compress,
                logId=get_date_seq_no("LOG_ID"),
            )
        )

    def info(self, category: str, event: str, **kwargs: Any) -> None:
        self._emit("INFO", category, event, kwargs)

    def warning(self, category: str, event: str, **kwargs: Any) -> None:
        self._emit("WARN", category, event, kwargs)

    def error(self, category: str, event: str, **kwargs: Any) -> None:
        self._emit("ERROR", category, event, kwargs)


_sys_logger: SysLogger | None = None


def get_sys_logger() -> SysLogger | None:
    return _sys_logger


def init_sys_logger(log_system_type: str) -> SysLogger:
    global _sys_logger
    _sys_logger = SysLogger(log_system_type)
    return _sys_logger
