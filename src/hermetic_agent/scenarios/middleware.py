"""ScenarioMiddleware — 拦截 /agent/chat* + /agent/scenarios/*/chat 路径.

行为:
1. 跳过非 chat 路径 (e.g. /health, /ready, /agent/skills, /agent/pool).
2. 调用 ScenarioRouter.route() → 失败时挂 request.ctx.scenario_error.
3. 调用 ScenarioInjector.inject() → 失败时挂 request.ctx.scenario_error.
4. 成功时挂 request.ctx.{scenario, routing_context, injection}.

Controller 在入口检查 ``request.ctx.scenario_error``, 若存在直接返回 400 JSON.
简化版: middleware **不** 主动短路返回 response — 让 controller 负责响应格式化.
"""

from __future__ import annotations

import structlog
from sanic import Sanic
from sanic.request import Request

from hermetic_agent.audit.log.log_markers import LM
from hermetic_agent.scenarios.errors import ScenarioError

logger = structlog.get_logger(__name__)


class ScenarioMiddleware:
    """Sanic request middleware: 把请求路由到 scenario + 注入 caller 参数.

    用法::

        app.register_middleware(ScenarioMiddleware(app), "request")

    依赖 (启动时由 scenario_lifecycle.init_scenarios 注入到 app.ctx):
    - ``app.ctx.scenario_router``: ScenarioRouter
    - ``app.ctx.scenario_injector``: ScenarioInjector
    - ``app.ctx.scenario_registry``: ScenarioRegistry (用于 router 内部引用)
    """

    # Sanic 在 response 阶段也会调 request middleware, CORS 扩展会检查 self.headers
    # 这里暴露一个空 dict 属性来避免 AttributeError
    headers: dict = {}

    def __init__(self, app: Sanic) -> None:
        # P0 重构: 不再在 __init__ 缓存 router/injector 引用.
        # 旧实现会在 reload 后 _router 仍指向旧对象, ``scenario_reload``
        # 端点替换 app.ctx.scenario_router 后, middleware 内部依然用旧
        # 引用 (fallthrough 路径), 导致 reload 不生效.
        #
        # 现在每次 __call__ 都从 ``self._app.ctx`` 现读, 保证 reload 透明.
        self._app = app

    async def __call__(self, request: Request) -> None:
        if not self._is_chat_path(request.path):
            return
        # 每次都从 app.ctx 重新读 — 支持 scenario_reload 热替换
        router = getattr(self._app.ctx, "scenario_router", None)
        injector = getattr(self._app.ctx, "scenario_injector", None)
        if router is None or injector is None:
            request.ctx.scenario_error = ScenarioError(
                "Scenario router/injector not initialized; "
                "scenario_lifecycle.init_scenarios may have failed."
            )
            return

        body = request.json if request.body else None
        if not isinstance(body, dict):
            body = {}
        headers = dict(request.headers)

        # 1. 路由 (router.route() 是同步方法, 不 await)
        try:
            ctx = router.route(
                request_path=request.path,
                headers=headers,
                body=body,
            )
        except ScenarioError as e:
            logger.warning(
                "scenario_routing_failed",
                path=request.path,
                code=getattr(e, "code", "ROUTING_FAILED"),
                error=str(e),
            )
            request.ctx.scenario_error = e
            return
        except Exception as e:  # noqa: BLE001 - 兜底
            logger.exception("scenario_routing_unexpected", path=request.path)
            request.ctx.scenario_error = ScenarioError(
                f"Internal routing error: {e}"
            )
            return

        # 2. 注入
        try:
            injection = injector.inject(
                scenario=ctx.scenario,
                user_message=str(body.get("message", "")),
                caller_skills=body.get("skills"),
                caller_tools=body.get("tools"),
                caller_system_prompt=body.get("system_prompt"),
            )
        except ScenarioError as e:
            logger.warning(
                "scenario_injection_failed",
                scenario=ctx.scenario.name,
                code=getattr(e, "code", "INJECTION_FAILED"),
                error=str(e),
            )
            request.ctx.scenario_error = e
            return

        # 3. 挂到 ctx — controller 后续可直接读取
        request.ctx.scenario = ctx.scenario
        request.ctx.routing_context = ctx
        request.ctx.injection = injection
        logger.info(
            LM.SCENARIO_ROUTE,
            scenario=ctx.scenario.name,
            matched_by=ctx.matched_by,
        )

    @staticmethod
    def _is_chat_path(path: str) -> bool:
        """判断是否需要走 scenario 路由.

        命中规则:
        - ``/agent/chat`` 或 ``/agent/chat/stream``
        - ``/agent/scenarios/<name>/chat`` 或 ``.../chat/stream``
        """
        if not path.startswith("/agent/"):
            return False
        if path == "/agent/chat" or path.startswith("/agent/chat/"):
            return True
        return path.startswith("/agent/scenarios/") and "/chat" in path


__all__ = ["ScenarioMiddleware"]
