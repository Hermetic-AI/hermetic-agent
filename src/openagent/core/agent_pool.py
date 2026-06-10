"""Agent Instance Pool Manager - Agent 实例池管理

管理和调度多个 opencode serve 实例，支持：
- 注册/注销 Agent 实例
- 维护实例状态：空闲（idle）、忙碌（busy）、离线（offline）
- 调度时自动分配空闲实例，任务完成后释放
- 支持动态扩缩容
"""

from __future__ import annotations

import asyncio
import enum
from dataclasses import dataclass, field
from typing import Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)


class AgentStatus(enum.Enum):
    """Agent 实例状态枚举。

    描述一个 Agent 实例在生命周期内所处的三种状态：空闲、忙碌、离线。
    """

    IDLE = "idle"  # 空闲，可分配
    BUSY = "busy"  # 忙碌，已被占用
    OFFLINE = "offline"  # 离线，不可用的


@dataclass
class AgentInstance:
    """Agent 实例的运行时元数据。

    保存单个 opencode serve 实例的连接信息、状态以及健康检查相关字段。
    """

    name: str
    base_url: str
    status: AgentStatus = AgentStatus.IDLE
    current_session_id: Optional[str] = None
    last_health_check: Optional[float] = None
    health_check_failures: int = 0

    @property
    def is_available(self) -> bool:
        """检查实例是否空闲且已经至少通过过一次健康检查。"""
        return self.status == AgentStatus.IDLE and self.last_health_check is not None


class AgentPoolService:
    """Agent 实例池管理器。

    管理多个 opencode serve 实例的生命周期和调度。
    内部以字典存储所有实例，并用 asyncio.Lock 保护并发分配。

    Usage:
        pool = AgentPoolManager()
        pool.register("agent-shanghai", "http://192.168.1.101:4096")
        pool.register("agent-beijing", "http://192.168.1.102:4096")

        instance = await pool.acquire_idle_instance()
        # 使用实例...
        pool.release("agent-shanghai")
    """

    def __init__(self) -> None:
        """初始化实例池，状态为空。

        健康检查间隔 / HTTP 探活超时 / 连续失败阈值 全部从 settings 读
        (health_check_interval / agent_pool_health_check_http_timeout /
        max_retries). 保留字面量默认作为兜底 (settings 不可用场景).
        """
        self._instances: dict[str, AgentInstance] = {}
        self._lock = asyncio.Lock()
        try:
            from openagent.config.settings import get_settings

            s = get_settings()
            self._health_check_interval: float = float(s.health_check_interval)
            self._health_check_http_timeout: float = float(
                s.agent_pool_health_check_http_timeout
            )
            self._max_health_check_failures: int = int(s.max_retries)
        except Exception:  # pragma: no cover
            self._health_check_interval = 30.0
            self._health_check_http_timeout = 5.0
            self._max_health_check_failures = 3
        self._health_check_task: Optional[asyncio.Task[None]] = None

    @property
    def instances(self) -> dict[str, AgentInstance]:
        """获取所有实例的只读视图。"""
        return self._instances.copy()

    def register(self, name: str, base_url: str) -> AgentInstance:
        """注册一个新的 Agent 实例到池中。

        Args:
            name: 实例名称，需全局唯一。
            base_url: opencode serve 的地址，如 http://192.168.1.101:4096。

        Returns:
            注册成功的 AgentInstance 对象。

        Raises:
            ValueError: 当同名实例已经存在时抛出。
        """
        logger.info("agent_register_start", name=name, base_url=base_url)
        if name in self._instances:
            logger.error("agent_register_failed", name=name, reason="duplicate_name")
            raise ValueError(f"Agent instance '{name}' already registered")

        instance = AgentInstance(name=name, base_url=base_url.rstrip("/"))
        self._instances[name] = instance
        logger.info("agent_registered", name=name, base_url=base_url)
        return instance

    def unregister(self, name: str) -> bool:
        """注销一个 Agent 实例。

        Args:
            name: 实例名称。

        Returns:
            成功注销返回 True，实例不存在返回 False。
        """
        logger.info("agent_unregister_start", name=name)
        if name not in self._instances:
            logger.warning("agent_unregister_failed", name=name, reason="not_found")
            return False

        instance = self._instances[name]
        if instance.status == AgentStatus.BUSY:
            logger.warning(
                "unregister_busy_agent",
                name=name,
                session_id=instance.current_session_id,
            )

        del self._instances[name]
        logger.info("agent_unregistered", name=name)
        return True

    async def acquire_idle_instance(self) -> Optional[AgentInstance]:
        """获取一个空闲的 Agent 实例。

        使用简单的轮询策略，从所有 IDLE 实例中返回第一个并把状态置为 BUSY。

        Returns:
            空闲的 AgentInstance，如果没有可用实例则返回 None。
        """
        logger.info("agent_acquire_start")
        async with self._lock:
            for instance in self._instances.values():
                if instance.status == AgentStatus.IDLE:
                    instance.status = AgentStatus.BUSY
                    logger.info(
                        "agent_acquired",
                        name=instance.name,
                        base_url=instance.base_url,
                    )
                    return instance
            logger.warning("agent_acquire_failed", reason="no_idle_instance")
            return None

    def release(self, name: str) -> bool:
        """释放一个 Agent 实例回池。

        Args:
            name: 实例名称。

        Returns:
            成功释放返回 True，实例不存在或状态非 BUSY 返回 False。
        """
        logger.info("agent_release_start", name=name)
        if name not in self._instances:
            logger.warning("release_unknown_agent", name=name)
            return False

        instance = self._instances[name]
        if instance.status != AgentStatus.BUSY:
            logger.warning(
                "release_not_busy_agent",
                name=name,
                status=instance.status.value,
            )
            return False

        instance.status = AgentStatus.IDLE
        instance.current_session_id = None
        logger.info("agent_released", name=name)
        return True

    def get_instance(self, name: str) -> Optional[AgentInstance]:
        """按名称获取实例；不存在则返回 None。"""
        return self._instances.get(name)

    def mark_offline(self, name: str) -> None:
        """将指定实例标记为离线。

        通常在健康检查连续失败时调用，让调度器不再分配该实例。
        """
        if name not in self._instances:
            return

        instance = self._instances[name]
        instance.status = AgentStatus.OFFLINE
        logger.warning("agent_marked_offline", name=name)

    async def health_check(self, name: str) -> bool:
        """对指定实例执行一次健康检查。

        通过 HTTP GET `/health` 判断实例是否在线；成功时刷新最近检查时间，
        失败时累加失败次数并在达到阈值后自动标记离线。

        Args:
            name: 实例名称。

        Returns:
            实例健康返回 True，否则返回 False。
        """
        logger.info("health_check_start", name=name)
        if name not in self._instances:
            logger.warning("health_check_failed", name=name, reason="not_found")
            return False

        instance = self._instances[name]

        try:
            async with httpx.AsyncClient(
                timeout=self._health_check_http_timeout
            ) as client:
                response = await client.get(f"{instance.base_url}/health")

                if response.status_code == 200:
                    instance.last_health_check = asyncio.get_event_loop().time()
                    instance.health_check_failures = 0
                    logger.debug("health_check_ok", name=name)
                    if instance.status == AgentStatus.OFFLINE:
                        instance.status = AgentStatus.IDLE
                        logger.info("agent_back_online", name=name)
                    return True
                else:
                    instance.health_check_failures += 1
                    logger.warning(
                        "health_check_failed",
                        name=name,
                        status_code=response.status_code,
                    )
                    return False

        except Exception as e:
            instance.health_check_failures += 1
            logger.warning(
                "health_check_error",
                name=name,
                error=str(e),
                failures=instance.health_check_failures,
            )

            if instance.health_check_failures >= self._max_health_check_failures:
                self.mark_offline(name)

            return False

    async def _health_check_loop(self) -> None:
        """健康检查循环后台任务，周期性遍历所有实例。"""
        while True:
            try:
                await asyncio.sleep(self._health_check_interval)
                for name in list(self._instances.keys()):
                    await self.health_check(name)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("health_check_loop_error", error=str(e))

    async def start_health_checks(self) -> None:
        """启动周期性的健康检查后台任务。"""
        if self._health_check_task is not None:
            return
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info("health_check_started")

    async def stop_health_checks(self) -> None:
        """停止周期性的健康检查后台任务。"""
        if self._health_check_task is not None:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None
            logger.info("health_check_stopped")

    def get_stats(self) -> dict:
        """获取实例池的聚合统计信息与每个实例的摘要。"""
        stats = {
            "total": len(self._instances),
            "idle": sum(1 for i in self._instances.values() if i.status == AgentStatus.IDLE),
            "busy": sum(1 for i in self._instances.values() if i.status == AgentStatus.BUSY),
            "offline": sum(1 for i in self._instances.values() if i.status == AgentStatus.OFFLINE),
            "instances": {},
        }
        for name, instance in self._instances.items():
            stats["instances"][name] = {
                "base_url": instance.base_url,
                "status": instance.status.value,
                "current_session_id": instance.current_session_id,
                "last_health_check": instance.last_health_check,
            }
        return stats
