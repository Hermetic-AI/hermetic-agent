"""流水号生成 — 仿照 fh-ai app/commons/utils/seqNoUtils.

两个东西:
- :func:`init_instance_id`  全局唯一实例标识 (HOSTNAME-hash + 启动顺序号)
- :func:`get_date_seq_no`  按 Key + 日期生成单调递增整数 (snowflake-lite)

格式约定 (跟 fh-ai 对齐):
- ``logId``     = ``YYYYMMDD * 10^12 + 12位序号``      20 位 int
- ``reqSeqNo``  = ``T{YYMMDDHHMMSS}{A-Z}{5位序号}``     例 ``T260610182405B00001``
"""
from __future__ import annotations

import hashlib
import os
import socket
import threading
from datetime import datetime

_INSTANCE_ID: str = ""
_INSTANCE_LOCK = threading.Lock()
_SEQ_LOCK = threading.Lock()
_SEQ_COUNTERS: dict[str, int] = {}
_SEQ_DAY: str = ""


def init_instance_id(env_override: str | None = None) -> str:
    """初始化 ``INSTANCE_ID``. 优先级:

    1. ``env_override`` 显式传
    2. ``LOG_INSTANCE_ID`` 环境变量
    3. ``socket.gethostname()`` 截断 + md5 截断 + 启动时间戳
    """
    global _INSTANCE_ID
    with _INSTANCE_LOCK:
        if _INSTANCE_ID:
            return _INSTANCE_ID
        if env_override:
            _INSTANCE_ID = env_override
            return _INSTANCE_ID
        env_id = os.environ.get("LOG_INSTANCE_ID", "").strip()
        if env_id:
            _INSTANCE_ID = env_id
            return _INSTANCE_ID
        hostname = socket.gethostname() or "unknown"
        short = hostname.replace(".", "-")[:8]
        h = hashlib.md5(hostname.encode("utf-8")).hexdigest()[:2].upper()
        stamp = datetime.now().strftime("%H%M%S")[:4]
        _INSTANCE_ID = f"{short}{h}{stamp}"
        return _INSTANCE_ID


def get_instance_id() -> str:
    return _INSTANCE_ID or "UNKNOWN"


def get_date_seq_no(key: str) -> int:
    """按当前日期生成单调递增整数.

    全局单计数器 (不区分 key), 保证 ``logId`` 在一个进程内单调 + 跨天归零.
    ``key`` 参数保留兼容 fh-ai 接口 (LOG_ID / WEB_REQ_NO), 实际不再细分.

    锁内执行, 多线程安全 (structlog + Sanic 线程池共用).
    """
    global _SEQ_DAY, _SEQ_COUNTERS
    day = datetime.now().strftime("%Y%m%d")
    with _SEQ_LOCK:
        if day != _SEQ_DAY:
            _SEQ_DAY = day
            _SEQ_COUNTERS = {"_global": 0}
        _SEQ_COUNTERS["_global"] = _SEQ_COUNTERS.get("_global", 0) + 1
        return int(day) * 10**12 + _SEQ_COUNTERS["_global"]


def reset_for_test() -> None:
    """仅测试用: 重置所有全局状态."""
    global _INSTANCE_ID, _SEQ_DAY
    with _INSTANCE_LOCK:
        _INSTANCE_ID = ""
    with _SEQ_LOCK:
        _SEQ_DAY = ""
        _SEQ_COUNTERS.clear()
