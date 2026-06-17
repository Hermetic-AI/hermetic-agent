"""Application startup and shutdown logic — extracted from app.py."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import structlog
from sanic import Sanic

from openagent.mcp.registry import MCPRegistry
from openagent.providers.agent_bridge import AgentBridge
from openagent.providers.base import AgentConfig
from openagent.skills.registry import SkillRegistry
from openagent.store import SessionRepositoryFactory

logger = structlog.get_logger(__name__)


def _skill_paths_with_fallbacks(settings: Any) -> list[str]:
    """Return configured skill paths plus existing repo/work shared fallbacks.

    Fallback 候选目录全部从 ``settings.skill_path_fallbacks`` 读
    (默认 4 个: 源码内 / work_shared / 容器内 / 容器内 work_shared).

    行为契约:
    - configured ``skill_paths`` 永远保留 (即使不存在, 让 SkillRegistry
      自己打 warning — 配置了却不存在的目录是用户错误, 应当被看到)
    - fallback 候选仅保留**存在**的 (fallback 本就是"探测哪个有", 不存在
      的不浪费一次 ``rglob``)

    P0 优化: 用 ``dict.fromkeys`` 单次 O(N) 去重保序, 替代
    set+list 双容器, 跟 Python idiom "dict keys 是有序 set" 对齐.
    """
    def _key(path: Path) -> str:
        try:
            return str(path.resolve()) if path.exists() else str(path)
        except OSError:
            return str(path)

    raw_paths = [Path(str(p)) for p in (getattr(settings, "skill_paths", None) or [])]
    raw_fallbacks = [
        Path(c) for c in (getattr(settings, "skill_path_fallbacks", None) or [])
    ]

    # 1. configured paths 全部保留 (resolve 后字符串做去重 key)
    configured_keys = dict.fromkeys(_key(p) for p in raw_paths)

    # 2. fallback 候选仅保留存在的, 然后去重 (防止 fallback 跟 configured 重)
    fallback_existing = [_key(p) for p in raw_fallbacks if p.exists()]
    fallback_keys = dict.fromkeys(fallback_existing)

    # 3. 合并: configured 优先, 然后 fallback 不重复的
    merged = {**configured_keys, **fallback_keys}
    return list(merged.keys())


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
        logger.debug("auto_register_skipped", reason="setting_disabled")
        return []
    configs = _default_agent_configs(settings)
    registered: list[str] = []
    for cfg in configs:
        try:
            bridge.register(cfg)
            registered.append(cfg.name)
        except ValueError as e:
            # 区分两种 ValueError:
            # 1) "already registered" — 热重载场景的正常幂等行为, debug
            # 2) 其它 (e.g. 不支持的 sdk_type) — 真正的配置错误, 必须 warn
            #    让运维/监控能感知. 之前一律 debug 容易让"配错 sdk_type"
            #    默默上线, 业务请求过来才报"agent not found".
            err_msg = str(e).lower()
            if "already registered" in err_msg or "already" in err_msg:
                logger.debug(
                    "default_agent_already_registered",
                    name=cfg.name,
                    detail=str(e),
                )
            else:
                logger.warning(
                    "default_agent_register_failed",
                    name=cfg.name,
                    sdk_type=getattr(cfg, "sdk_type", "?"),
                    error=str(e),
                )
    logger.debug(
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
    logger.debug("application_startup", host=settings.host, port=settings.port)

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
    skill_paths = _skill_paths_with_fallbacks(settings)
    if skill_paths:
        skill_registry.load_from_paths(*skill_paths)
    logger.debug(
        "skills_loaded",
        skills_count=len(skill_registry.list_all()),
        skill_paths=skill_paths,
    )

    # P0-1: 渐进式 SKILL 加载器. PromptBuilder 持有 FragmentLoader, 由
    # chat_controller 透传给 bridge.chat, 让 scenario.progressive_skill
    # 真正生效 (之前 bridge.chat 走的是 skills/registry.py 全量内联路径,
    # progressive_skill 配了等于没配).
    from openagent.skills.runtime import FragmentLoader, PromptBuilder

    fragment_loader = FragmentLoader(
        skill_registry,
        budget=settings.fragment_budget_tokens,
        policy=settings.fragment_budget_policy,
    )
    prompt_builder = PromptBuilder(fragment_loader=fragment_loader)
    logger.debug(
        "prompt_builder_ready",
        budget_tokens=fragment_loader.budget,
        policy=fragment_loader.policy,
    )

    try:
        mcp_registry = MCPRegistry.from_config(settings.mcp_tools_config)
    except Exception as e:
        logger.error("mcp_registry_init_failed", error=str(e))
        raise
    logger.debug("mcp_registry_ready", tools_count=len(mcp_registry.list_all()))

    # AUIP: 注册合成工具 ask_user (LLM 用它推 UI 卡片, 框架在 stream 中拦截)
    # 必须放在 mcp_registry 初始化之后, 所有 scenario 共享
    from openagent.auip.cards import CARD_TYPES_SET
    ask_user_schema = {
        "type": "object",
        "required": ["card_type"],
        "properties": {
            "card_type": {
                "type": "string",
                "enum": sorted(CARD_TYPES_SET),
                "description": (
                    "Which kind of UI card to show the user. "
                    "Frontend (FlightResultCard / SelectionListCard / etc.) renders by card_type."
                ),
            },
            "title": {"type": "string"},
            "body": {"type": "object", "description": "Card body (free-form dict)."},
            "options": {"type": "array"},
            "decision_buttons": {"type": "array", "description": "Alias for actions."},
            "actions": {"type": "array"},
            "fields": {"type": "array", "description": "Form fields (OD_INPUT / PASSENGER_FORM)."},
            "metadata": {"type": "object"},
        },
    }
    mcp_registry.register_synthetic_tool(
        name="ask_user",
        description=(
            "Emit a structured UI card to the user. The framework intercepts "
            "this call and converts it to a `card` SSE event. DO NOT call this "
            "in HITL mode (use CHAT_FALLBACK with `_text` body instead). "
            "For data presentation, use card_type=FLIGHT_RESULT and put the "
            "structured flight data in body.{summary, plans}."
        ),
        input_schema=ask_user_schema,
    )
    logger.debug("auip_ask_user_tool_registered", card_types=sorted(CARD_TYPES_SET))

    # P0-2: read_skill 工具 — 渐进式 SKILL 加载的 LLM 入口.
    # Anthropic Skills 协议要求 LLM 能"按需加载"子 skill 片段, 否则
    # 全部 skill 内容塞进 system prompt 会爆 context window.
    # 实现: 接受 ``{"name": "<skill>", "fragment": "<frag_id>"}``;
    # 找到 SkillRegistry 里注册的 skill, 返回它的 SKILL.md 全文
    # 或 ``fragments/<frag_id>.md`` 子片段. 找不到抛 4xx 让 LLM 知道.
    read_skill_schema = {
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {
                "type": "string",
                "description": "Skill name (matches SKILL.md frontmatter name).",
            },
            "fragment": {
                "type": "string",
                "description": (
                    "Optional fragment id. If omitted, returns the full SKILL.md body. "
                    "If set, looks up <skill_dir>/fragments/<fragment>.md."
                ),
            },
        },
    }

    async def _read_skill_handler(name: str, fragment: str | None = None, **_: Any) -> dict:
        """read_skill tool handler — 读 SKILL.md 或 fragments/<id>.md."""
        skill = skill_registry.get(name)
        if skill is None:
            return {
                "ok": False,
                "error_code": "SKILL_NOT_FOUND",
                "name": name,
                "available": [s.name for s in skill_registry.list_all()],
            }
        # 1. fragment 路径: <skill.source dir>/fragments/<fragment>.md
        if fragment:
            if not skill.source:
                return {
                    "ok": False,
                    "error_code": "FRAGMENT_NOT_FOUND",
                    "name": name,
                    "fragment": fragment,
                    "reason": "skill has no source file",
                }
            from pathlib import Path
            skill_dir = Path(skill.source).parent
            frag_path = skill_dir / "fragments" / f"{fragment}.md"
            if not frag_path.exists():
                return {
                    "ok": False,
                    "error_code": "FRAGMENT_NOT_FOUND",
                    "name": name,
                    "fragment": fragment,
                    "expected_path": str(frag_path),
                }
            text = frag_path.read_text(encoding="utf-8")
            return {
                "ok": True,
                "name": name,
                "version": skill.version,
                "fragment": fragment,
                "content": text,
            }
        # 2. 全文: 优先从 skill.source 读, 退到 prompt_template
        from pathlib import Path
        if skill.source:
            p = Path(skill.source)
            if p.is_file() and p.exists():
                text = p.read_text(encoding="utf-8")
                return {
                    "ok": True,
                    "name": name,
                    "version": skill.version,
                    "description": skill.description,
                    "content": text,
                }
        return {
            "ok": True,
            "name": name,
            "version": skill.version,
            "description": skill.description,
            "content": skill.prompt_template or "",
        }

    mcp_registry.register(
        name="read_skill",
        description=(
            "Load a SKILL.md (or a fragments/<id>.md) on demand. "
            "Use this when the system prompt only advertised the skill's name "
            "and you need the full instructions. Anthropic Skills progressive "
            "loading protocol."
        ),
        input_schema=read_skill_schema,
        handler=_read_skill_handler,
    )
    logger.debug("read_skill_tool_registered", skills_count=len(skill_registry.list_all()))

    bridge = AgentBridge(
        skill_registry=skill_registry,
        mcp_registry=mcp_registry,
        storage=storage,
    )
    logger.debug("agent_bridge_ready")

    # 启动时自动注册默认 Agent（除非显式关闭）
    _auto_register_defaults(bridge, settings)
    logger.debug(
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
    logger.debug("scheduler_ready", default_timeout=settings.default_timeout)

    app.ctx.storage = storage
    app.ctx.bridge = bridge
    app.ctx.skill_registry = skill_registry
    app.ctx.mcp_registry = mcp_registry
    app.ctx.scheduler = scheduler
    app.ctx.settings = settings  # P6: 让 controller 能取到 settings
    app.ctx.prompt_builder = prompt_builder  # P0-1: 渐进式 SKILL 加载

    # P-Feb-2026: 挂上新的 ServiceContainer, 让 controller 用它持久化
    # user message / chat_turn / parts / assistant message. 旧 ``storage`` shim
    # 只写 sessions + assistant message, 新 container 写完整 6 实体 + audit_log.
    from openagent.store.services.container import build_container_from_settings
    try:
        services = await build_container_from_settings(settings)
        app.ctx.services = services
        logger.info(
            "service_container_ready",
            backend=settings.storage_backend,
            backends={
                "session": type(services.session._repo).__name__,
                "message": type(services.message._repo).__name__,
                "part": type(services.part._repo).__name__,
                "chat_turn": type(services.chat_turn._repo).__name__,
                "audit_log": type(services.audit_log._repo).__name__,
            },
        )
    except Exception as e:
        logger.error(
            "service_container_init_failed",
            backend=settings.storage_backend,
            error_type=type(e).__name__,
            error=str(e),
            exc_info=_tb.format_exc(),
        )
        # 不 raise — 旧 ``MySQLStorage`` shim 仍可用, controller 优雅降级
        # (chat 仍可走, 只是 user message / chat_turn / parts 不存)
        app.ctx.services = None

    # P6: 初始化 Scenario 子系统 (registry / router / injector / middleware)
    from openagent.api.lifecycle.scenario_lifecycle import init_scenarios
    await init_scenarios(app, settings)

    # F4: 初始化 Turn 子系统 (HITL 挂起 / 恢复 / 事件持久化)
    _init_turn_subsystem(app, settings)

    # 平台日志 (仿照 fh-ai app/commons/log) — 在最后调, 失败快速失败
    from openagent.audit.log.setup import setup_log_platform

    await setup_log_platform(settings)
    logger.info("log_platform_ready")

    logger.info(
        "application_ready",
        skills=len(skill_registry.list_all()),
        tools=len(mcp_registry.list_all()),
        agents=len(bridge.list_agents()),
    )


async def shutdown(app: Sanic) -> None:
    """释放 storage 与需要显式清理的资源（按相反顺序）。

    Args:
        app: 当前 Sanic 应用。
    """
    logger.info("application_shutdown")
    from openagent.audit.log.setup import shutdown_log_platform

    try:
        await shutdown_log_platform()
    except Exception as e:
        logger.error("log_platform_shutdown_failed", error=str(e))
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
    from openagent.skills.runtime.manifest import SkillManifest, StateSpec

    store = InMemoryTurnStore()
    app.ctx.turn_store = store
    logger.debug("turn_store_ready", backend="in_memory")

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
    logger.debug("hitl_factory_ready", strategy="default_manifest_all_states_all_tools")
