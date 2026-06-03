"""Scenario lifecycle — 启动期初始化 registry/router/injector + middleware.

被 ``lifecycle.startup`` 调用 (在 ``_startup`` 钩子末尾), 不重建 storage / bridge.
失败时记录错误但不抛 — 允许 chat_controller 在 scenario 未就绪时仍可工作.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
from sanic import Sanic

from openagent.scenarios.injector import InMemoryAuditLogger, ScenarioInjector
from openagent.scenarios.middleware import ScenarioMiddleware
from openagent.scenarios.registry import ScenarioRegistry
from openagent.scenarios.router import ScenarioRouter

logger = structlog.get_logger(__name__)


def find_project_root() -> Path:
    """定位项目根(放 ``pyproject.toml`` 的目录).

    Sanic 服务可能以多种方式启动 (``python -m openagent.main`` / 直接执行 main.py /
    IDE 调试器 / 容器),每次 cwd 都不一样。settings 里的 ``scenario_paths`` /
    ``work_root`` 都是相对路径,必须锚到项目根,否则 ``work/scenarios`` 会拼到
    ``src/openagent/work/scenarios`` (不存在)。

    算法: 从本文件位置向上走,第一个含 ``pyproject.toml`` 的目录;
    兜底 ``Path.cwd()`` (用于 monorepo 没 pyproject 的情况)。
    """
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "pyproject.toml").is_file():
            return parent
    return Path.cwd()


def _build_placeholder_ctx(settings: Any) -> dict[str, str]:
    """构造 Scenario YAML 占位符解析所需的 ctx."""
    project_root = find_project_root()
    work_root_rel = getattr(settings, "work_root", "work")
    work_root = project_root / work_root_rel
    return {
        "WORK_ROOT": str(work_root),
        "WORK_SHARED": str(work_root / "shared"),
        # PROJECT_DIR 兜底: 第一个 tenant 工程的根 (与 §4.1 一致)
        "PROJECT_DIR": str(
            work_root / "tenants" / "tenant-A" / "projects" / "project-1"
        ),
    }


async def init_scenarios(app: Sanic, settings: Any) -> None:
    """初始化 Scenario 子系统: registry / router / injector / middleware.

    幂等 — 重复调用会清空 registry 后重新加载.
    """
    try:
        ctx = _build_placeholder_ctx(settings)

        registry = ScenarioRegistry(ctx=ctx)
        paths = list(getattr(settings, "scenario_paths", []) or [])
        if not paths:
            paths = [str(Path(settings.work_root) / "scenarios")]
        # 把相对路径锚到项目根(不是 cwd — 启动方式多变)
        project_root = find_project_root()
        resolved_paths: list[str] = []
        for p in paths:
            pp = Path(p)
            if not pp.is_absolute():
                pp = project_root / pp
            if pp.exists():
                resolved_paths.append(str(pp))
        if resolved_paths:
            registry.load_from_paths(*resolved_paths)

        router = ScenarioRouter(
            registry=registry,
            default_scenario=getattr(settings, "default_scenario", "_default"),
        )
        injector = ScenarioInjector(audit=InMemoryAuditLogger())

        # 挂到 app.ctx — controller 与 middleware 都从这里取
        app.ctx.scenario_ctx = ctx
        app.ctx.scenario_registry = registry
        app.ctx.scenario_router = router
        app.ctx.scenario_injector = injector

        # 注册 middleware (idempotent — 重复 register 会被 Sanic 抛错, 用 try 兜底)
        if not getattr(app.ctx, "scenario_middleware_registered", False):
            try:
                # 注意: register_middleware 需要 callable (instance), 不是 class
                app.register_middleware(ScenarioMiddleware(app), "request")
                app.ctx.scenario_middleware_registered = True
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "scenario_middleware_register_failed",
                    error=str(e),
                )

        logger.info(
            "scenarios_initialized",
            total=len(registry.list_all()),
            enabled=len(registry.list_enabled()),
            paths=resolved_paths,
            default=getattr(settings, "default_scenario", "_default"),
        )
    except Exception as e:
        logger.exception("scenarios_init_failed", error=str(e))


__all__ = ["init_scenarios"]
