"""redisWriteTask — 仿照 fh-ai app/commons/log/redisWriteThread.

用户规范 (见 docs/design/外部日志采集平台接入指南.md §6.1):
- Redis key: ``log:{queueName}`` (List)
- 元素: 原始 DTO JSON 字符串 (BusiLog / RequestLog / SysLog)
- 行为: ``LLEN`` 超限丢弃, ``LPUSH`` 批量写入

实现:
- 0.5s 轮询一次, 排空 :class:`ObjectLogWriter` 的内存队列
- ``LLEN`` check, 超限丢弃 (丢的是**这次**整批, 跟 fh-ai 一致)
- 全部用 ``LPUSH`` 写到 ``log:{queueName}`` Redis List
- 启动期 / 停止期各刷一次, 保证 shutdown 不丢日志

Hub 现有 deps 没 redis, 安装时一并加 (见 ``pyproject.toml``).
"""
from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from hermetic_agent.audit.log.object_log_writer import ObjectLogWriter

logger = structlog.get_logger(__name__)


class RedisWriteTask:
    def __init__(
        self,
        writer: ObjectLogWriter,
        redis_client: Redis,
        *,
        poll_interval: float = 0.5,
    ) -> None:
        self._writer = writer
        self._redis = redis_client
        self._queue_key = f"log:{writer.queue_name}"
        self._poll_interval = poll_interval
        self._task: asyncio.Task[None] | None = None
        self._stopping = False
        self._batch_size = 256

    @property
    def queue_key(self) -> str:
        return self._queue_key

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stopping = False
        self._task = asyncio.create_task(self._run(), name="log-redis-writer")
        logger.info("redis_log_writer_started", key=self._queue_key)

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning("redis_log_writer_stop_error", error=str(e))
            self._task = None
        await self._flush_once()
        with contextlib.suppress(Exception):
            await self._redis.aclose()
        logger.info("redis_log_writer_stopped", key=self._queue_key)

    async def _run(self) -> None:
        try:
            while not self._stopping:
                await self._flush_once()
                await asyncio.sleep(self._poll_interval)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("redis_log_writer_loop_error", error=str(e))

    async def _flush_once(self) -> None:
        try:
            items = self._writer.drain(max_items=self._batch_size)
            if not items:
                return
            current = await self._redis.llen(self._queue_key)
            if current >= self._writer.max_queue_size:
                logger.warning(
                    "redis_log_queue_full_dropping",
                    current=current, max=self._writer.max_queue_size,
                )
                return
            remaining = self._writer.max_queue_size - current
            to_push = items[:remaining]
            if to_push:
                await self._redis.lpush(self._queue_key, *to_push)
            if len(items) > remaining:
                logger.warning(
                    "redis_log_queue_overflow_dropped",
                    dropped=len(items) - remaining,
                )
        except Exception as e:
            logger.warning("redis_log_push_failed", error=str(e), count=0)
