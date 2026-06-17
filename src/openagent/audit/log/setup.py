"""setup_log_platform — 启动期编排 + 优雅 shutdown.

调用顺序:

1. ``setup_log_platform(settings)``  在 ``lifecycle.startup`` 里
   - ``init_instance_id()``           写 ``INSTANCE_ID``
   - ``ObjectLogWriter.init(...)``    建内存队列
   - ``init_busi_logger / request_logger / sys_logger``  facade 单例
   - ``RedisWriteTask.start()``       起后台任务 (use_redis=True 时)
   写入 Redis List ``log:{queueName}``,
   元素为原始 DTO JSON 字符串.
2. ``shutdown_log_platform()``       在 ``lifecycle.shutdown`` 里
   - ``RedisWriteTask.stop()``        flush + 取消 Task
   - ``ObjectLogWriter.reset_for_test()`` 仅测试

退路: 任意 init 步骤失败 → 整个 setup 抛 ``LogPlatformSetupError``, 让
``lifecycle.startup`` 走快速失败路径 (跟 Hub 现有 ``Fatal startup error``
模式一致).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from openagent.audit.log.busi_logger import init_busi_logger
from openagent.audit.log.log_middleware import LogMiddleware
from openagent.audit.log.object_log_writer import ObjectLogWriter
from openagent.audit.log.redis_write_task import RedisWriteTask
from openagent.audit.log.request_logger import init_request_logger
from openagent.audit.log.seq_no import init_instance_id
from openagent.audit.log.sys_logger import init_sys_logger

if TYPE_CHECKING:
    from openagent.config.settings import Settings

logger = structlog.get_logger(__name__)


class LogPlatformSetupError(RuntimeError):
    """setup_log_platform 初始化失败, 上层应快速失败."""


@dataclass
class _State:
    redis_task: RedisWriteTask | None = None
    middleware: LogMiddleware | None = None
    use_redis: bool = False


_state = _State()


def _build_redis_client(settings: Settings):
    import redis.asyncio as redis_async

    kwargs: dict = {
        "host": settings.log_redis_host,
        "port": settings.log_redis_port,
        "db": settings.log_redis_database,
        "socket_timeout": settings.log_redis_timeout,
    }
    if settings.log_redis_password:
        kwargs["password"] = settings.log_redis_password
    return redis_async.Redis(**kwargs)


async def setup_log_platform(settings: Settings) -> LogMiddleware:
    """初始化日志平台 + 返回 LogMiddleware (供 :func:`app.register_middleware`).

    Raises:
        LogPlatformSetupError: 初始化失败 (例如 Redis 不可达).
    """
    try:
        init_instance_id()
        busi = init_busi_logger(settings.log_system_type)
        request = init_request_logger(settings.log_system_type)
        init_sys_logger(settings.log_system_type)
        _state.use_redis = settings.log_use_redis_log

        writer = ObjectLogWriter.init(
            use_redis=settings.log_use_redis_log,
            queue_name=settings.log_queue_name,
            max_queue_size=settings.log_max_queue_size,
            file_path=settings.log_file_path,
            tee_to_stdout=settings.log_tee_to_stdout,
        )
        logger.info(
            "log_platform_initialized",
            use_redis=writer.use_redis,
            queue_name=writer.queue_name,
            max_queue_size=writer.max_queue_size,
            file_path=writer.file_path,
            tee_to_stdout=writer.tee_to_stdout,
            instance_id=init_instance_id(),
            busi_type=busi.type_prefix,
            request_type=request.type_prefix,
        )

        if settings.log_use_redis_log:
            redis_client = _build_redis_client(settings)
            task = RedisWriteTask(
                writer=writer,
                redis_client=redis_client,
                poll_interval=settings.log_redis_poll_interval,
            )
            await task.start()
            _state.redis_task = task
        _state.middleware = LogMiddleware(request)
        return _state.middleware
    except Exception as e:
        raise LogPlatformSetupError(f"Failed to setup log platform: {e}") from e


async def shutdown_log_platform() -> None:
    """停止 Redis 任务, flush 剩余日志, 关文件句柄."""
    if _state.redis_task is not None:
        try:
            await _state.redis_task.stop()
        except Exception as e:
            logger.warning("log_platform_shutdown_error", error=str(e))
        _state.redis_task = None
    writer = ObjectLogWriter.get_instance()
    if writer is not None:
        writer.close()
    _state.middleware = None


def get_log_middleware() -> LogMiddleware | None:
    return _state.middleware


def get_redis_write_task() -> RedisWriteTask | None:
    return _state.redis_task


def reset_for_test() -> None:
    """仅测试用: 把全局状态清干净."""
    global _state
    _state = _State()
    ObjectLogWriter.reset_for_test()
