"""Sanic App Factory - thin shell.

Heavy lifting lives in:
  * `api.lifecycle` — startup/shutdown wiring
  * `api.readiness` — /ready probe
  * `api.schemas`  — Pydantic request/response models
  * `api.controllers.*` — per-resource Blueprints
  * `api.logging_setup` — structlog + Rich 配置
"""

from __future__ import annotations

import structlog
from sanic import Sanic
from sanic.request import Request
from sanic.response import JSONResponse
from sanic_cors import CORS
from sanic_ext import openapi as sanic_openapi

from openagent.api.controllers.auth_controller import auth_bp
from openagent.api.controllers.chat_controller import chat_bp
from openagent.api.controllers.pool_controller import pool_bp
from openagent.api.controllers.question_controller import question_bp
from openagent.api.controllers.registry_controller import registry_bp
from openagent.api.controllers.scenario_controller import scenario_bp
from openagent.api.controllers.session_controller import session_bp
from openagent.api.controllers.todo_controller import todo_bp
from openagent.api.lifecycle import shutdown, startup
from openagent.api.logging_setup import configure_logging
from openagent.api.readiness import build_ready_response
from openagent.api.turn_routes import turn_bp
from openagent.config.settings import Settings, get_settings

logger = structlog.get_logger(__name__)

doc_summary = sanic_openapi.summary
doc_description = sanic_openapi.description
doc_tag = sanic_openapi.tag
operation = sanic_openapi.operation


def _configure_logging(settings: Settings) -> None:
    """薄壳: 委托给 ``openagent.api.logging_setup.configure_logging``。

    保留这个函数是为了不让外部 import 站点失效; 实际配置逻辑在
    ``logging_setup`` 模块里, 加 Rich 主题 / 字段过滤都在那里。
    """
    configure_logging(settings)


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
    _configure_logging(settings)
    logger.debug("application_create_start", app_name="agent-scheduler-hub")

    app = Sanic("agent-scheduler-hub")
    app.config.FALLBACK_ERROR_FORMAT = "json"
    app.config.DEBUG = settings.debug

    # P8: SSE 长连接超时 (P0 流式断流修复) — 全部从 settings 读
    # ------------------------------------------------------------------
    # Sanic 默认 10s RequestTimeout / 5s KEEP_ALIVE, 任何 < 1min 的 LLM
    # 调用都会被打断. settings.* 已抬到 10min, 让 chat/stream 和 turn/resume
    # 端点能撑过长 LLM 思考 + 多步工具调用.
    #
    # 这些是**上限**而不是**真实等待时间**: 业务流自然结束
    # (LLM done / 客户端断开) 会立即释放资源, 不会浪费.
    # ------------------------------------------------------------------
    app.config.REQUEST_TIMEOUT = settings.sanic_request_timeout
    app.config.REQUEST_MAX_SIZE = settings.sanic_request_max_size
    app.config.KEEP_ALIVE_TIMEOUT = settings.sanic_keep_alive_timeout
    app.config.KEEP_ALIVE = True
    app.config.WEBSOCKET_PING_TIMEOUT = settings.sanic_websocket_ping_timeout
    app.config.WEBSOCKET_PONG_TIMEOUT = settings.sanic_websocket_pong_timeout
    logger.debug(
        "sanic_timeouts_configured",
        request_timeout=settings.sanic_request_timeout,
        keep_alive_timeout=settings.sanic_keep_alive_timeout,
        max_request_size=settings.sanic_request_max_size,
    )

    CORS(app, resources={r"/*": {"origins": settings.cors_origins}}, automatic_options=True)

    app.config.API_TITLE = settings.app_title
    app.config.API_VERSION = settings.app_version
    app.config.API_DESCRIPTION = settings.app_description
    app.config.API_TERMS_OF_SERVICE = ""
    app.config.API_CONTACT_EMAIL = settings.app_contact_email
    app.config.API_LICENSE_NAME = settings.app_license_name

    # Mount per-resource controllers.
    app.blueprint(chat_bp)
    app.blueprint(session_bp)
    app.blueprint(registry_bp)
    app.blueprint(pool_bp)
    app.blueprint(turn_bp)  # F3: HITL turn 生命周期端点
    app.blueprint(scenario_bp)
    # P7: opencode 原生 question / todo 端点 (代理 /question + /session/:id/todo)
    app.blueprint(question_bp)
    app.blueprint(todo_bp)
    # 飞鹤正式系统登录代理 (前端 → Hub → traveldev.feiheair.com)
    app.blueprint(auth_bp)

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

    logger.debug("application_create_completed", app_name="agent-scheduler-hub")
    return app
