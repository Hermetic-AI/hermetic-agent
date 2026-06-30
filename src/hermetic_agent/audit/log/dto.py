"""平台日志 DTO — 仿照 fh-ai app/commons/log/dto.

3 类 DTO, 每类拼上 ``logSystemType`` 后才是最终 ``type`` 字段::

    type = base_prefix + LOG_SYSTEM_TYPE.upper()
    例: "BUSI_LOG_" + "hermetic_agent" → "BUSI_LOG_hermetic_agent"

公共字段:
- ``type`` (str)  分桶主键, 平台按 ``BUSI_LOG_*`` / ``REQUEST_LOG_*`` / ``APP_LOG_*`` 前缀路由
- ``instanceId`` (str)  实例标识, 多实例切片
- ``reqSeqNo`` (str)  请求流水号, 跨模块追踪主键 (BusiLog 中由 ContextVar 注入)
- ``logId`` (int)  平台 logId, 去重主键

压缩约定 (跟 fh-ai 一致): ``logInfo > 20KB`` → gzip+base64, 置
``compress=True``, ``infoSize`` 保留原始字节数. 消费侧: ``base64.b64decode →
gzip.decompress → utf-8``.

字段名故意保持 camelCase (跟 fh-ai wire format 对齐), 平台消费侧按
原始 key 解析, 不要 snake_case 化. ruff N815 在本文件禁用.
"""
# ruff: noqa: N815

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class LogType(str, Enum):
    """日志类型枚举. value 是小写前缀, 拼接 ``logSystemType`` 后再 .upper()."""

    BUSI = "busi_log_"
    REQUEST = "request_log_"
    APP = "app_log_"


@dataclass
class BusiLog:
    """业务日志 — 来自 ``logger.info(...)`` / ``busiLogger.info(...)``."""

    type: str = ""
    instanceId: str = ""
    reqSeqNo: str = ""
    logTime: datetime | None = None
    startTime: datetime | None = None
    level: str = "INFO"
    programLine: str = ""
    threadName: str = ""
    memo: str = ""
    logInfo: str | None = None
    infoSize: int = 0
    compress: bool = False
    logId: int = 0


@dataclass
class RequestLog:
    """请求日志 — LogMiddleware 每次请求发 2 条 (start + end)."""

    type: str = ""
    requestTime: datetime | None = None
    reqSeqNo: str = ""
    serviceName: str = ""
    instanceId: str = ""
    ip: str = ""
    delay: int = -1
    result: str = "SUCC"
    errorMessage: str = ""
    mainReqSeqNo: str = ""
    bizNo: str = ""
    userCode: str = ""
    clientId: str = ""
    memo: str = ""
    logId: int = 0


@dataclass
class SysLog:
    """系统/应用日志 — 启动/停止/异常. 当前未在主路径使用, 接口已实现."""

    type: str = ""
    level: str = "INFO"
    instanceId: str = ""
    logTime: datetime | None = None
    threadId: int = 0
    reqSeqNo: str = ""
    category: str = ""
    threadName: str = ""
    programLine: str = ""
    logInfo: str | None = None
    infoSize: int = 0
    compress: bool = False
    logId: int = 0
