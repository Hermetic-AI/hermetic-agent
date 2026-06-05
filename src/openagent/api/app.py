"""Sanic App Factory - thin shell.

Heavy lifting lives in:
  * `api.lifecycle` — startup/shutdown wiring
  * `api.readiness` — /ready probe
  * `api.schemas`  — Pydantic request/response models
  * `api.controllers.*` — per-resource Blueprints
"""

from __future__ import annotations

import structlog
from sanic import Sanic
from sanic.request import Request
from sanic.response import JSONResponse
from sanic_cors import CORS
from sanic_ext import openapi as sanic_openapi

from openagent.api.controllers.chat_controller import chat_bp
from openagent.api.controllers.pool_controller import pool_bp
from openagent.api.controllers.registry_controller import registry_bp
from openagent.api.controllers.scenario_controller import scenario_bp
from openagent.api.controllers.session_controller import session_bp
from openagent.api.lifecycle import shutdown, startup
from openagent.api.readiness import build_ready_response
from openagent.api.turn_routes import turn_bp
from openagent.config.settings import Settings, get_settings

logger = structlog.get_logger(__name__)

doc_summary = sanic_openapi.summary
doc_description = sanic_openapi.description
doc_tag = sanic_openapi.tag
operation = sanic_openapi.operation


def _configure_logging(settings: Settings) -> None:
    """根据 settings 配置 structlog (JSON 或控制台渲染)。

    三个连环坑一次性治:

    1. ``LoggerFactory()`` 把日志转给 stdlib logger, 但 stdlib root 默认
       无 handler → 日志被静默丢弃。这里强制装一个 ``StreamHandler``。
    2. ``Settings.__init__`` 会在 ``get_settings()`` 时就触发 structlog
       logger (``storage_backend_registered``), 比本函数跑得还早; 一旦
       ``cache_logger_on_first_use=True``, 后续 ``structlog.configure``
       改的处理器全失效 → 先 ``structlog.reset_defaults()`` 抹掉旧 cache。
    3. stdlib root 默认 level=WARNING, INFO 全被过滤 → 按 settings 设。
    """
    import logging
    import sys

    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(handler)
    root.setLevel(log_level)

    # structlog 25.x 没有 force= 参数, 用 reset_defaults() 清掉旧 cache.
    structlog.reset_defaults()
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            # ensure_ascii=False 让中文等内容在 JSON 日志里直接以 UTF-8 字符出现，
            # 而不是 查询... 这种 escape —— 终端、ELK、grep 中文都更友好。
            structlog.processors.JSONRenderer(ensure_ascii=False)
            if settings.log_format == "json"
            else structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _install_error_handler(app: Sanic) -> None:
    """安装全局异常处理器。

    - 真正的 5xx（未预期异常）→ 记录 traceback 并以 JSON 形式返回 500。
    - 4xx（``NotFound`` / ``MethodNotAllowed`` 等客户端错误，例如浏览器请求
      ``/favicon.ico``）→ 让 Sanic 自带的 404/405 响应处理，不当成 500 报错。
    """
    import traceback as _tb

    try:
        from sanic.exceptions import SanicException
    except ImportError:  # pragma: no cover
        SanicException = Exception  # type: ignore[misc,assignment]

    @app.exception(SanicException)
    async def _client_error(request: Request, exception: SanicException) -> JSONResponse:
        """4xx 客户端错误：透传 Sanic 的状态码，不再当成 500。"""
        # 静默 /favicon.ico 这种预期内的探测请求；其它 4xx 记一条 info 即可。
        if request.path == "/favicon.ico":
            return JSONResponse(
                {"success": False, "error": "Not Found", "path": request.path},
                status=exception.status_code,
            )
        logger.info(
            "client_error",
            path=request.path,
            method=request.method,
            status=exception.status_code,
            error=str(exception),
        )
        return JSONResponse(
            {"success": False, "status": exception.status_code, "error": str(exception)},
            status=exception.status_code,
        )

    @app.exception(Exception)
    async def _unhandled(request: Request, exception: Exception) -> JSONResponse:
        """5xx 兜底异常处理：打印结构化日志后返回 500 JSON。"""
        tb = _tb.format_exc()
        logger.exception(
            "unhandled_exception",
            path=request.path,
            method=request.method,
            error=str(exception),
        )
        return JSONResponse(
            {
                "success": False,
                "status": 500,
                "error": f"{type(exception).__name__}: {exception}",
                "traceback": tb,
                "path": request.path,
            },
            status=500,
        )


def create_app(settings: Settings | None = None) -> Sanic:
    """创建并配置 Sanic 应用。

    负责：
      - 初始化 structlog；
      - 挂载所有 controller Blueprint；
      - 注册 `/health`、`/ready` 系统路由；
      - 绑定 `after_server_start` / `before_server_stop` 到 lifecycle。

    Args:
        settings: 可选配置；为 None 时从环境变量加载。

    Returns:
        配置完成的 Sanic 应用实例。
    """
    if settings is None:
        settings = get_settings()
    logger.info("application_create_start", app_name="agent-scheduler-hub")
    _configure_logging(settings)

    app = Sanic("agent-scheduler-hub")
    app.config.FALLBACK_ERROR_FORMAT = "json"
    app.config.DEBUG = settings.debug

    CORS(app, resources={r"/*": {"origins": settings.cors_origins}}, automatic_options=True)

    app.config.API_TITLE = "Agent Scheduler Hub"
    app.config.API_VERSION = "0.1.0"
    app.config.API_DESCRIPTION = (
        "OpenCode Agent Scheduler Hub — 统一调度 OpenCode / Claude Code Agent 的 REST API。\n\n"
        "支持会话管理、SSE 流式聊天、Skill 注册、MCP 工具管理、Agent Pool 注册。"
    )
    app.config.API_TERMS_OF_SERVICE = ""
    app.config.API_CONTACT_EMAIL = "dev@openagent.local"
    app.config.API_LICENSE_NAME = "MIT"

    # Mount per-resource controllers.
    app.blueprint(chat_bp)
    app.blueprint(session_bp)
    app.blueprint(registry_bp)
    app.blueprint(pool_bp)
    app.blueprint(turn_bp)  # F3: HITL turn 生命周期端点
    app.blueprint(scenario_bp)

    _install_error_handler(app)

    # 注册 scenario middleware — **必须在 finalize_middleware 之前**,
    # 否则 Sanic 25 的 startup 顺序下, 启动后注册的 middleware 会被
    # 已经 finalize 的列表覆盖, 永远不调用. 把它放 create_app 阶段
    # (跟路由注册同一时机) 解决. middleware 内部从 app.ctx 读
    # router/injector, 所以注册早于 scenarios 加载也 OK.
    from openagent.scenarios.middleware import ScenarioMiddleware

    app.register_middleware(ScenarioMiddleware(app), "request")

    @app.get("/health")
    @doc_summary("健康检查")
    @doc_description("用于负载均衡 / 探针，返回 200 表示进程存活。")
    @doc_tag("System")
    @operation("health")
    async def health(request: Request) -> JSONResponse:
        """健康检查：进程存活即返回 200。"""
        return JSONResponse({"status": "ok"})

    @app.get("/ready")
    @doc_summary("就绪检查")
    @doc_description(
        "检查存储、桥接器、技能/工具注册表是否全部就绪。\n\n"
        "返回 200 表示全部就绪；返回 503 时 `missing` 数组列出未就绪项。"
    )
    @doc_tag("System")
    @operation("ready")
    async def ready(request: Request) -> JSONResponse:
        """就绪检查：聚合所有子组件的就绪状态并返回。"""
        return build_ready_response(request)

    @app.after_server_start
    async def _startup(app: Sanic) -> None:
        """Sanic 启动后钩子：委托给 lifecycle.startup。"""
        await startup(app, settings)

    @app.before_server_stop
    async def _shutdown(app: Sanic) -> None:
        """Sanic 停止前钩子：委托给 lifecycle.shutdown。"""
        await shutdown(app)

    logger.info("application_create_completed", app_name="agent-scheduler-hub")
    return app
