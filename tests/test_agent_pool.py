"""Tests for AgentPoolManager"""

import pytest
from openagent.core.agent_pool import AgentPoolManager, AgentStatus


class TestAgentPoolManager:
    """AgentPoolManager 测试"""

    def test_register(self) -> None:
        """测试注册 Agent 实例"""
        pool = AgentPoolManager()
        instance = pool.register("test-agent", "http://localhost:4096")

        assert instance.name == "test-agent"
        assert instance.base_url == "http://localhost:4096"
        assert instance.status == AgentStatus.IDLE

    def test_register_duplicate_raises(self) -> None:
        """测试重复注册会抛出异常"""
        pool = AgentPoolManager()
        pool.register("test-agent", "http://localhost:4096")

        with pytest.raises(ValueError, match="already registered"):
            pool.register("test-agent", "http://localhost:4097")

    def test_unregister(self) -> None:
        """测试注销 Agent 实例"""
        pool = AgentPoolManager()
        pool.register("test-agent", "http://localhost:4096")

        assert pool.unregister("test-agent") is True
        assert pool.get_instance("test-agent") is None

    def test_unregister_unknown_returns_false(self) -> None:
        """测试注销未知实例返回 False"""
        pool = AgentPoolManager()
        assert pool.unregister("unknown") is False

    @pytest.mark.asyncio
    async def test_acquire_idle_instance(self) -> None:
        """测试获取空闲实例"""
        pool = AgentPoolManager()
        pool.register("agent-1", "http://localhost:4091")
        pool.register("agent-2", "http://localhost:4092")

        instance = await pool.acquire_idle_instance()

        assert instance is not None
        assert instance.name in ["agent-1", "agent-2"]
        assert instance.status == AgentStatus.BUSY

    @pytest.mark.asyncio
    async def test_acquire_idle_instance_no_available(self) -> None:
        """测试没有可用实例时返回 None"""
        pool = AgentPoolManager()
        # 不注册任何实例

        instance = await pool.acquire_idle_instance()

        assert instance is None

    @pytest.mark.asyncio
    async def test_acquire_all_busy(self) -> None:
        """测试所有实例都忙碌时返回 None"""
        pool = AgentPoolManager()
        pool.register("agent-1", "http://localhost:4091")
        pool.register("agent-2", "http://localhost:4092")

        # 获取所有空闲实例
        await pool.acquire_idle_instance()
        await pool.acquire_idle_instance()

        # 再获取应该返回 None
        assert await pool.acquire_idle_instance() is None

    @pytest.mark.asyncio
    async def test_release(self) -> None:
        """测试释放实例"""
        pool = AgentPoolManager()
        pool.register("test-agent", "http://localhost:4096")

        instance = await pool.acquire_idle_instance()
        assert instance is not None
        assert instance.status == AgentStatus.BUSY

        pool.release("test-agent")
        assert instance.status == AgentStatus.IDLE

    def test_release_not_busy(self) -> None:
        """测试释放未忙碌的实例返回 False"""
        pool = AgentPoolManager()
        pool.register("test-agent", "http://localhost:4096")

        assert pool.release("test-agent") is False

    def test_release_unknown(self) -> None:
        """测试释放未知实例返回 False"""
        pool = AgentPoolManager()
        assert pool.release("unknown") is False

    @pytest.mark.asyncio
    async def test_get_stats(self) -> None:
        """测试获取统计信息"""
        pool = AgentPoolManager()
        pool.register("agent-1", "http://localhost:4091")
        pool.register("agent-2", "http://localhost:4092")

        stats = pool.get_stats()

        assert stats["total"] == 2
        assert stats["idle"] == 2
        assert stats["busy"] == 0
        assert stats["offline"] == 0

        # 占用一个实例
        await pool.acquire_idle_instance()
        stats = pool.get_stats()

        assert stats["idle"] == 1
        assert stats["busy"] == 1
