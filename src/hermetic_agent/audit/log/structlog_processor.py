"""structlog 处理器钩子 — 用户选了「替换」: 把 ``logger.info(...)`` 自动转 BusiLog.

策略: 在 structlog processor chain 末尾 (renderer 之前) 插一个
:func:`platform_log_processor`, 把 event_dict 包成 :class:`BusiLog` 推到
:class:`ObjectLogWriter`. ``renderer`` 之后照常跑 (stdout 照旧输出 Rich / JSON).

关键约束:
- 必须放在 ``structlog.contextvars.merge_contextvars`` **之后**, 这样
  ContextVar 里的 ``request_id`` 已经被 merge 进 event_dict
- 不能抛异常 — 写日志失败绝不能影响主业务
- ``IS_LOG=False`` 时不写 (LogMiddleware 没启用)
- ``programLine`` 不从 structlog event 里取 (没有现成的 call site), 留空
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from typing import Any

from hermetic_agent.audit.log.busi_logger import BusiLogger
from hermetic_agent.audit.log.dto import BusiLog
from hermetic_agent.audit.log.log_compress import maybe_compress
from hermetic_agent.audit.log.log_context import get_is_log, get_request_id, get_request_time
from hermetic_agent.audit.log.object_log_writer import ObjectLogWriter
from hermetic_agent.audit.log.seq_no import get_date_seq_no, get_instance_id

_processor_logger: BusiLogger | None = None
_processor_lock = threading.Lock()


def _get_processor_logger() -> BusiLogger | None:
    global _processor_logger
    if _processor_logger is not None:
        return _processor_logger
    with _processor_lock:
        if _processor_logger is not None:
            return _processor_logger
        from hermetic_agent.audit.log.busi_logger import init_busi_logger

        try:
            _processor_logger = init_busi_logger("hermetic_agent")
        except Exception:
            return None
    return _processor_logger


def platform_log_processor(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """structlog Processor: 推 BusiLog 到 ObjectLogWriter.

    Returns:
        原样返回 event_dict (不破坏后续 renderer).
    """
    if not get_is_log():
        return event_dict
    busi = _get_processor_logger()
    if busi is None:
        return event_dict
    writer = ObjectLogWriter.get_instance()
    if writer is None:
        return event_dict
    try:
        payload = {
            k: v
            for k, v in event_dict.items()
            if k not in ("timestamp", "level", "_record", "_from_structlog")
        }
        event = str(payload.pop("event", ""))
        try:
            log_info_str = json.dumps(
                {"event": event, **payload}, ensure_ascii=False, default=str,
            )
        except Exception:
            log_info_str = str({"event": event, **payload})
        info, size, compress = maybe_compress(log_info_str)
        writer.write_busi(
            BusiLog(
                type=busi.type_prefix,
                instanceId=get_instance_id(),
                reqSeqNo=get_request_id(),
                logTime=datetime.now(),
                startTime=get_request_time(),
                level=str(event_dict.get("level", "info")).upper(),
                programLine="",
                threadName=threading.current_thread().name,
                memo=log_info_str[:200],
                logInfo=info,
                infoSize=size,
                compress=compress,
                logId=get_date_seq_no("LOG_ID"),
            )
        )
    except Exception:
        pass
    return event_dict
