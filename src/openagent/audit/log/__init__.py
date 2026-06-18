"""L5 平台日志子系统 (仿照 fh-ai app/commons/log).

跟 Hub 现有 structlog 体系**并行**:
- structlog 走 stdout (Rich/JSON), 给开发期 / docker logs / Loki 直抓
- busiLogger / requestLogger 走 in-memory queue → 异步 Redis / 文件,
  给外部日志采集平台订阅消费

公开 API:
- :func:`setup_log_platform`  在 ``lifecycle.startup`` 调, 初始化
  ObjectLogWriter + RedisWriteTask + facade 单例
- :func:`shutdown_log_platform`  在 ``lifecycle.shutdown`` 调, 优雅停写
- :class:`BusiLogger`  业务日志门面
- :class:`RequestLogger`  请求日志门面 (由 LogMiddleware 内部调)
- :class:`SysLogger`  系统/应用日志门面 (启动/停止/异常)
- :class:`LogMiddleware`  Sanic request middleware
- :func:`get_object_log_writer`  测试/外部用
- :func:`get_request_logger`  测试/外部用
- :func:`get_busi_logger`  测试/外部用

DTO 字段 + 规范参见 ``docs/design/外部日志采集平台接入指南.md`` (本仓版).
"""
from __future__ import annotations

from openagent.audit.log.busi_logger import BusiLogger, get_busi_logger
from openagent.audit.log.dto import BusiLog, LogType, RequestLog, SysLog
from openagent.audit.log.log_context import (
    LogContext,
    bind_request_context,
    clear_request_context,
    get_is_log,
    get_request_id,
    get_request_time,
)
from openagent.audit.log.log_markers import LM
from openagent.audit.log.log_middleware import LogMiddleware
from openagent.audit.log.object_log_writer import (
    ObjectLogWriter,
    get_object_log_writer,
)
from openagent.audit.log.request_logger import RequestLogger, get_request_logger
from openagent.audit.log.setup import setup_log_platform, shutdown_log_platform
from openagent.audit.log.sys_logger import SysLogger, get_sys_logger

__all__ = [
    "BusiLog",
    "BusiLogger",
    "LM",
    "LogContext",
    "LogMiddleware",
    "LogType",
    "ObjectLogWriter",
    "RequestLog",
    "RequestLogger",
    "SysLog",
    "SysLogger",
    "bind_request_context",
    "clear_request_context",
    "get_busi_logger",
    "get_is_log",
    "get_object_log_writer",
    "get_request_id",
    "get_request_logger",
    "get_request_time",
    "get_sys_logger",
    "setup_log_platform",
    "shutdown_log_platform",
]
