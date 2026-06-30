"""Test configuration - pytest 配置"""

import pytest
from sanic import Sanic

from hermetic_agent.api.app.app import create_app
from hermetic_agent.config.settings import Settings
from hermetic_agent.core import AgentPoolManager, Scheduler
from hermetic_agent.mcp.registry import MCPRegistry
from hermetic_agent.providers.agent_bridge import AgentBridge
from hermetic_agent.skills.registry import SkillRegistry
from hermetic_agent.store.memory import MemoryStorage


@pytest.fixture
def settings() -> Settings:
    """测试配置"""
    return Settings(
        opencode_base_url="http://localhost:4096",
        log_level="DEBUG",
        log_format="text",
    )


@pytest.fixture
def pool() -> AgentPoolManager:
    """Agent 池"""
    return AgentPoolManager()


@pytest.fixture
def scheduler(
    bridge: AgentBridge,
    skill_registry: SkillRegistry,
    mcp_registry: MCPRegistry,
) -> Scheduler:
    """调度服务（基于 Bridge）"""
    return Scheduler(
        bridge=bridge,
        skill_registry=skill_registry,
        mcp_registry=mcp_registry,
    )


@pytest.fixture
def storage() -> MemoryStorage:
    """存储后端（内存）"""
    return MemoryStorage()


@pytest.fixture
def skill_registry() -> SkillRegistry:
    """技能注册中心"""
    return SkillRegistry()


@pytest.fixture
def mcp_registry() -> MCPRegistry:
    """MCP 注册中心"""
    return MCPRegistry()


@pytest.fixture
def bridge(
    skill_registry: SkillRegistry,
    mcp_registry: MCPRegistry,
    storage: MemoryStorage,
) -> AgentBridge:
    """Agent Bridge"""
    return AgentBridge(
        skill_registry=skill_registry,
        mcp_registry=mcp_registry,
        storage=storage,
    )


@pytest.fixture
def app(
    settings: Settings,
    bridge: AgentBridge,
    skill_registry: SkillRegistry,
    mcp_registry: MCPRegistry,
    scheduler: Scheduler,
) -> Sanic:
    """Sanic 测试应用"""
    app = create_app(settings)
    app.ctx.bridge = bridge
    app.ctx.skill_registry = skill_registry
    app.ctx.mcp_registry = mcp_registry
    app.ctx.scheduler = scheduler
    return app
