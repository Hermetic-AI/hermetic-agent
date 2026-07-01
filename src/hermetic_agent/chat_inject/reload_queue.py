from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ReloadTask:
    """reload 任务: 把 (node_id, paths) 写到 admin_server /admin/policy + /admin/reload."""
    node_id: str
    paths: list[str]
    enqueue_ts: float = 0.0


ReloadApplier = Callable[[ReloadTask], Awaitable[bool]]


class ReloadQueue:
    """单消费者 + 10s 防抖队列, SkillOverlayManager 通过它触发 /admin/reload.

    enqueue 在 (node_id, paths, debounce_window) 内幂等:
    同一个 (node_id, paths) 在同一 debounce 时间桶内只入队一次, 后续重复请求直接跳过.

    注意: ``_seen`` dict 永不清理, 长时间运行进程会单调增长.
    如需有界, 由调用方周期性重建 ReloadQueue 或外部清理.
    """

    def __init__(self, *, apply: ReloadApplier,
                 debounce_seconds: float = 10.0) -> None:
        self._apply = apply
        self._debounce = debounce_seconds
        self._queue: asyncio.Queue[ReloadTask] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._stopping = False
        self._seen: dict[tuple[str, frozenset[str], int], bool] = {}

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            await self._queue.put(
                ReloadTask(node_id="__stop__", paths=[]))
            await self._task
            self._task = None

    async def enqueue(self, task: ReloadTask) -> None:
        task.enqueue_ts = time.time()
        bucket = int(task.enqueue_ts // self._debounce)
        key = (task.node_id, frozenset(task.paths), bucket)
        if self._seen.get(key):
            logger.debug("reload_debounced", node_id=task.node_id,
                         paths=task.paths)
            return
        self._seen[key] = True
        await self._queue.put(task)

    async def _worker(self) -> None:
        while True:
            task = await self._queue.get()
            if task.node_id == "__stop__":
                break
            try:
                await self._apply(task)
            except Exception as e:  # noqa: BLE001
                logger.error("reload_apply_failed", error=str(e),
                             node_id=task.node_id)


__all__ = ["ReloadQueue", "ReloadTask"]
