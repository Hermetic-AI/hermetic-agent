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
    """构造 Scenario YAML 占位符解析所需的 ctx.

    PROJECT_DIR 兜底路径从 ``settings.project_dir_fallback`` 读
    (默认 ``work/tenants/tenant-A/projects/project-1``, 跟 §4.1 一致).
    相对路径以 work_root 为基准; 绝对路径直接用.
    """
    project_root = find_project_root()
    work_root_rel = getattr(settings, "work_root", "work")
    work_root = project_root / work_root_rel
    project_dir_fallback = getattr(
        settings, "project_dir_fallback", "tenants/tenant-A/projects/project-1"
    )
    fallback_path = Path(project_dir_fallback)
    project_dir = (
        fallback_path if fallback_path.is_absolute() else work_root / fallback_path
    )
    return {
        "WORK_ROOT": str(work_root),
        "WORK_SHARED": str(work_root / "shared"),
        # PROJECT_DIR 兜底: 第一个 tenant 工程的根 (与 §4.1 一致)
        "PROJECT_DIR": str(project_dir),
    }


async def init_scenarios(app: Sanic, settings: Any) -> None:
    """初始化 Scenario 子系统: registry / router / injector / middleware.

    幂等 — 重复调用会清空 registry 后重新加载.

    P0 改进:
    - 失败时把错误状态挂到 ``app.ctx.scenarios_error``, 让 readiness 端点
      能区分"未初始化"与"初始化失败", 而不是仅靠 logger (生产难以排查).
    - scenarios 路径支持递归 (跟 ``ScenarioRegistry.load_from_paths`` 内部
      ``rglob`` 对齐) — 之前只检查根目录, 子目录 scenario 不会加载.
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
            else:
                logger.warning(
                    "scenario_path_missing",
                    path=str(pp),
                    hint="检查 settings.scenario_paths / 挂载 volume",
                )

        # 加载 (registry.load_from_paths 内部 rglob *.scenario.yaml)
        if resolved_paths:
            registry.load_from_paths(*resolved_paths)

        # default_scenario 存在性校验: 启动时显式提示, 避免运行期才发现
        default_name = getattr(settings, "default_scenario", "_default")
        if registry.get(default_name) is None:
            logger.warning(
                "scenario_default_not_registered",
                default=default_name,
                available=registry.list_names(),
            )

        router = ScenarioRouter(
            registry=registry,
            default_scenario=default_name,
        )
        injector = ScenarioInjector(audit=InMemoryAuditLogger())

        # 挂到 app.ctx — controller 与 middleware 都从这里取
        app.ctx.scenario_ctx = ctx
        app.ctx.scenario_registry = registry
        app.ctx.scenario_router = router
        app.ctx.scenario_injector = injector
        # 显式状态标记 (P0: 让 readiness / 中间件能区分"未初始化"vs"失败")
        app.ctx.scenarios_initialized = True
        app.ctx.scenarios_error = None

        # 注意: middleware 在 app.py:create_app 阶段就已经注册了 (早于
        # Sanic finalize_middleware), 这里只挂 ctx 引用, 不再 register.
        # 详见 app.py 注释.

        logger.info(
            "scenarios_initialized",
            total=len(registry.list_all()),
            enabled=len(registry.list_enabled()),
            paths=resolved_paths,
            default=default_name,
        )
    except Exception as e:
        # 失败: 挂 error 状态到 ctx, 让 readiness 端点能 503 + 给出 reason
        app.ctx.scenarios_initialized = False
        app.ctx.scenarios_error = str(e)
        logger.exception(
            "scenarios_init_failed",
            error=str(e),
            hint="scenario 路由将不可用, 全部 chat 请求会返 400",
        )


__all__ = ["init_scenarios"]
