"""Tests for Scheduler"""

import pytest
from hermetic_agent.core import Scheduler


class TestScheduler:
    """Scheduler tests"""

    def test_init(self, scheduler: Scheduler, bridge, skill_registry, mcp_registry) -> None:
        """Test scheduler initialization"""
        assert scheduler._bridge is bridge
        assert scheduler._skill_registry is skill_registry
        assert scheduler._mcp_registry is mcp_registry
        assert scheduler._default_timeout == 120.0

    def test_run_with_custom_timeout(self, scheduler: Scheduler) -> None:
        """Test custom timeout"""
        assert scheduler._default_timeout == 120.0

    @pytest.mark.asyncio
    async def test_run_no_available_agent(self, scheduler: Scheduler) -> None:
        """Test behavior when no agent is available"""
        result = await scheduler.run("test prompt")
        assert result.success is False
        assert result.error is not None
