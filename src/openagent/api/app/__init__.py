"""openagent.api.app — Sanic app 工厂 + Blueprint 注册.

职责 (本子包):
  - ``app.py``            create_app(settings) — 整个 Sanic app 的装配入口
  - ``blueprint_registry`` register_all_blueprints(app) — 集中所有
                                controller blueprint 的挂载, 避免散落在
                                create_app 里
  - ``_install_error_handler`` (in app.py) — 全局 4xx/5xx 处理

不放在这里的东西:
  - controller 实现 (见 openagent.api.http.controllers)
  - 中间件 / ScenarioMiddleware 挂载 (见 openagent.api.http.app, 内部用)
  - Pydantic schema (见 openagent.api.http.schemas)
  - readiness / 启动期 scenario 加载 (见 openagent.api.lifecycle)
"""
from openagent.api.app.app import create_app
from openagent.api.app.blueprint_registry import register_all_blueprints

__all__ = ["create_app", "register_all_blueprints"]
