"""objectLogWriter — 仿照 fh-ai app/commons/log/objectLogWriter.

内存无锁队列 ``queue.SimpleQueue`` + 3 种 sink (互斥 + 可叠加 tee):

- **Redis List** (mode A, 生产推荐): 后台 :class:`RedisWriteTask` 周期 drain
- **本地文件** (mode B, 单机 / 无 Redis 场景): ``_enqueue`` 同步追加 JSON 行,
  跟 Redis 路径互斥
- **stdout tee** (dev / debug): ``_enqueue`` 额外把 JSON 打到 stdout, 可叠加

策略表::

    use_redis | file_path   | tee      | 实际 sink
    ----------+-------------+----------+---------------
    true      | (任意)      | false    | Redis
    true      | (任意)      | true     | Redis + tee
    false     | None        | false    | drop
    false     | None        | true     | tee
    false     | 设了        | false    | file
    false     | 设了        | true     | file + tee

启动期 :func:`init` 写单例; 业务侧拿 :func:`get_object_log_writer`, 没初始化
(单元测试 / 不想接平台) 时返回 ``None``, facade 退化为 no-op.
"""
from __future__ import annotations

import contextlib
import json
import sys
import threading
from dataclasses import asdict, is_dataclass
from datetime import datetime
from queue import Empty, SimpleQueue

import structlog

from openagent.audit.log.dto import BusiLog, RequestLog, SysLog

logger = structlog.get_logger(__name__)


def _serialize(obj: object) -> str:
    """DTO → JSON. ``datetime`` → ``%Y-%m-%d %H:%M:%S.%f`` (毫秒截断)."""
    if is_dataclass(obj) and not isinstance(obj, type):
        obj = asdict(obj)

    def default(o: object) -> str:
        if isinstance(o, datetime):
            return o.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        if is_dataclass(o) and not isinstance(o, type):
            return asdict(o)
        return str(o)

    return json.dumps(obj, ensure_ascii=False, default=default)


class ObjectLogWriter:
    """单例: 内存队列 + 异步分发 (Redis / 文件 / stdout tee)."""

    _instance: ObjectLogWriter | None = None
    _init_lock = threading.Lock()

    def __init__(
        self,
        *,
        use_redis: bool,
        queue_name: str,
        max_queue_size: int,
        file_path: str | None = None,
        tee_to_stdout: bool = False,
    ) -> None:
        self._use_redis = use_redis
        self._queue_name = queue_name
        self._max_queue_size = max_queue_size
        self._file_path = file_path
        self._tee_to_stdout = tee_to_stdout
        self._queue: SimpleQueue[str] = SimpleQueue()
        self._dropped: int = 0
        self._file_lock: threading.Lock | None = None
        self._file_handle = None
        if file_path and not use_redis:
            self._file_lock = threading.Lock()
            try:
                # 不能用 ``with`` — 需要保持 file handle 跨多次 write
                self._file_handle = open(  # noqa: SIM115
                    file_path, "a", encoding="utf-8", buffering=1,
                )
            except OSError as e:
                logger.warning("log_file_open_failed", path=file_path, error=str(e))

    @classmethod
    def init(cls, **kwargs: object) -> ObjectLogWriter:
        with cls._init_lock:
            if cls._instance is None:
                cls._instance = cls(**kwargs)
            return cls._instance

    @classmethod
    def get_instance(cls) -> ObjectLogWriter | None:
        return cls._instance

    @classmethod
    def reset_for_test(cls) -> None:
        """仅测试用."""
        with cls._init_lock:
            if cls._instance is not None:
                cls._instance._close_file()
            cls._instance = None

    def write_busi(self, log: BusiLog) -> None:
        self._enqueue(_serialize(log))

    def write_request(self, log: RequestLog) -> None:
        self._enqueue(_serialize(log))

    def write_sys(self, log: SysLog) -> None:
        self._enqueue(_serialize(log))

    def _enqueue(self, json_str: str) -> None:
        # 1) 文件 sink (mode B, 跟 Redis 互斥). 写失败不抛.
        if self._file_handle is not None and not self._use_redis:
            try:
                with self._file_lock:  # type: ignore[union-attr]
                    self._file_handle.write(json_str + "\n")
            except Exception as e:
                logger.warning("log_file_write_failed", error=str(e))
        # 2) stdout tee. 加 [platform-log] 前缀方便 grep.
        if self._tee_to_stdout:
            try:
                sys.stdout.write(f"[platform-log] {json_str}\n")
                sys.stdout.flush()
            except Exception as e:
                logger.warning("log_stdout_tee_failed", error=str(e))
        # 3) 内存队列 — 永远 push, 让后台消费者能 drain.
        try:
            self._queue.put_nowait(json_str)
        except Exception as e:
            self._dropped += 1
            if self._dropped % 100 == 1:
                logger.warning("log_queue_put_failed", dropped=self._dropped, error=str(e))

    def drain(self, max_items: int | None = None) -> list[str]:
        """排空当前内存队列. ``max_items`` 用于分批."""
        out: list[str] = []
        while True:
            if max_items is not None and len(out) >= max_items:
                break
            try:
                out.append(self._queue.get_nowait())
            except Empty:
                break
        return out

    def _close_file(self) -> None:
        if self._file_handle is not None:
            with contextlib.suppress(Exception):
                self._file_handle.close()
            self._file_handle = None

    def close(self) -> None:
        """关文件句柄, 给 shutdown_log_platform 调."""
        self._close_file()

    @property
    def queue_name(self) -> str:
        return self._queue_name

    @property
    def use_redis(self) -> bool:
        return self._use_redis

    @property
    def max_queue_size(self) -> int:
        return self._max_queue_size

    @property
    def file_path(self) -> str | None:
        return self._file_path

    @property
    def file_lock(self) -> threading.Lock | None:
        return self._file_lock

    @property
    def tee_to_stdout(self) -> bool:
        return self._tee_to_stdout


def get_object_log_writer() -> ObjectLogWriter | None:
    return ObjectLogWriter.get_instance()
