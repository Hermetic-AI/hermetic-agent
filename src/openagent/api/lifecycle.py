"""Application startup and shutdown logic — extracted from app.py."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Iterable

import structlog
from sanic import Sanic

from openagent.api.controllers.chat_controller import chat_bp
from openagent.api.controllers.pool_controller import pool_bp
from openagent.api.controllers.registry_controller import registry_bp
from openagent.api.controllers.session_controller import session_bp
from openagent.mcp.registry import MCPRegistry
from openagent.providers.agent_bridge import AgentBridge
from openagent.providers.base import AgentConfig
from openagent.skills.registry import SkillRegistry
from openagent.store import SessionRepositoryFactory

logger = structlog.get_logger(__name__)


def _default_agent_configs(settings: Any) -> list[AgentConfig]:
    """根据 settings 构建一组启动时自动注册的默认 Agent 列表。

    默认行为：注册一个 ``opencode-core`` 实例，指向 ``opencode_base_url``；
    后续可在 ``.env`` 的 ``AGENT_SCHEDULER_DEFAULT_AGENTS_JSON`` 里覆盖。
    """
    overrides: Iterable[dict] = getattr(settings, "default_agents_json", []) or []
    if overrides:
        out: list[AgentConfig] = []
        for raw in overrides:
            try:
                out.append(
                    AgentConfig(
                        name=raw["name"],
                        base_url=raw["base_url"],
                        sdk_type=raw.get("sdk_type", "opencode"),
                        default_model=raw.get("default_model"),
                    )
                )
            except (KeyError, TypeError) as e:
                logger.warning(
                    "default_agent_config_invalid",
                    raw=raw,
                    error=str(e),
                )
        if out:
            return out
    return [
        AgentConfig(
            name="opencode-core",
            base_url=settings.opencode_base_url,
            sdk_type="opencode",
        ),
    ]


def _auto_register_defaults(bridge: AgentBridge, settings: Any) -> list[str]:
    """如果 ``auto_register_default_agents`` 开启则注册默认 Agent；返回已注册名。"""
    if not getattr(settings, "auto_register_default_agents", False):
        logger.info("auto_register_skipped", reason="setting_disabled")
        return []
    configs = _default_agent_configs(settings)
    registered: list[str] = []
    for cfg in configs:
        try:
            bridge.register(cfg)
            registered.append(cfg.name)
        except ValueError as e:
            # Already-registered is the expected "idempotent" case during a
            # hot reload. Log at info, not error.
            logger.info(
                "default_agent_already_registered",
                name=cfg.name,
                detail=str(e),
            )
    logger.info(
        "default_agents_auto_registered",
        count=len(registered),
        names=registered,
    )
    return registered


async def startup(app: Sanic, settings: Any) -> None:
    """把 storage / registries / bridge / scheduler 注入 app.ctx。

    Args:
        app: 当前 Sanic 应用。
        settings: 应用配置。
    """
    logger.info("application_startup", host=settings.host, port=settings.port)

    try:
        storage = SessionRepositoryFactory.create(settings.storage_backend, settings=settings)
        await storage.connect()
        await storage.init_schema()
    except Exception as e:
        logger.error(
            "storage_init_failed",
            backend=settings.storage_backend,
            error=str(e),
        )
        raise

    skill_registry = SkillRegistry()
    if settings.skill_paths:
        skill_registry.load_from_paths(*settings.skill_paths)
    logger.info(
        "skills_loaded",
        skills_count=len(skill_registry.list_all()),
        skill_paths=list(settings.skill_paths or []),
    )

    try:
        mcp_registry = MCPRegistry.from_config(settings.mcp_tools_config)
    except Exception as e:
        logger.error("mcp_registry_init_failed", error=str(e))
        raise
    logger.info("mcp_registry_ready", tools_count=len(mcp_registry.list_all()))

    bridge = AgentBridge(
        skill_registry=skill_registry,
        mcp_registry=mcp_registry,
        storage=storage,
    )
    logger.info("agent_bridge_ready")

    # 启动时自动注册默认 Agent（除非显式关闭）
    _auto_register_defaults(bridge, settings)
    logger.info(
        "bridge_agents_after_startup",
        count=len(bridge.list_agents()),
        names=list(bridge.list_agents().keys()),
    )

    # Lazy import to avoid circular dep with core.scheduler.
    from openagent.core.scheduler import SchedulerService

    scheduler = SchedulerService(
        bridge=bridge,
        skill_registry=skill_registry,
        mcp_registry=mcp_registry,
        default_timeout=settings.default_timeout,
    )
    logger.info("scheduler_ready", default_timeout=settings.default_timeout)

    app.ctx.storage = storage
    app.ctx.bridge = bridge
    app.ctx.skill_registry = skill_registry
    app.ctx.mcp_registry = mcp_registry
    app.ctx.scheduler = scheduler
    app.ctx.settings = settings  # P6: 让 controller 能取到 settings

    # P6: 初始化 Scenario 子系统 (registry / router / injector / middleware)
    from openagent.api.scenario_lifecycle import init_scenarios
    await init_scenarios(app, settings)

    # F4: 初始化 Turn 子系统 (HITL 挂起 / 恢复 / 事件持久化)
    _init_turn_subsystem(app, settings)

    logger.info(
        "application_ready",
        skills_count=len(skill_registry.list_all()),
        tools_count=len(mcp_registry.list_all()),
        agents_count=len(bridge.list_agents()),
    )


async def shutdown(app: Sanic) -> None:
    """释放 storage 与需要显式清理的资源（按相反顺序）。

    Args:
        app: 当前 Sanic 应用。
    """
    logger.info("application_shutdown")
    storage = getattr(app.ctx, "storage", None)
    if storage is not None:
        try:
            await storage.close()
        except Exception as e:
            logger.error("storage_close_failed", error=str(e))
    mcp_registry = getattr(app.ctx, "mcp_registry", None)
    if mcp_registry is not None and hasattr(mcp_registry, "close"):
        try:
            await mcp_registry.close()
        except Exception as e:
            logger.error("mcp_registry_close_failed", error=str(e))
    logger.info("application_shutdown_completed")


# ---------------------------------------------------------------------------
# F4: Turn subsystem (HITL)
# ---------------------------------------------------------------------------


def _init_turn_subsystem(app: Sanic, settings: Any) -> None:
    """挂 InMemoryTurnStore + SuspendableScheduler 工厂.

    每个 scenario 独立一个 manifest (P5 简化版: 全部用 default manifest).
    """
    from openagent.core.suspendable_scheduler import SuspendableScheduler
    from openagent.core.turn_store import InMemoryTurnStore
    from openagent.skill_runtime.manifest import SkillManifest, StateSpec

    store = InMemoryTurnStore()
    app.ctx.turn_store = store
    logger.info("turn_store_ready", backend="in_memory")

    # F4: 默认 manifest - 允许所有状态调所有工具, 让 P5 mock 模式可工作
    # 真实生产中应从 scenario.a2ui.state_machine 加载
    def _default_manifest(scenario: Any) -> SkillManifest:
        manifest = SkillManifest(name=scenario.name, version=scenario.version, initial_state="S01")
        # 给所有 book-flight 13 状态 + 3 终态配 allowed_tools
        all_tool_names = [
            "ask_user",  # 框架级, 任何状态都允许
            "query_flight_basic", "choose_flight", "choose_cabin",
            "fill_passenger", "validate_booking_info", "build_order_preview",
            "submit_order", "confirm_order", "reset_booking_session",
        ]
        for state_id in [
            "S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08", "S09",
            "S10", "S11", "S12", "S13", "F1", "F2", "F3",
        ]:
            manifest.states[state_id] = StateSpec(
                description=state_id,
                allowed_tools=all_tool_names,
            )
        return manifest

    def _hitl_factory(scenario: Any) -> SuspendableScheduler:
        manifest = _default_manifest(scenario)
        return SuspendableScheduler(
            turn_store=store,
            manifest=manifest,
        )

    app.ctx.hitl_factory = _hitl_factory
    logger.info("hitl_factory_ready", strategy="default_manifest_all_states_all_tools")
