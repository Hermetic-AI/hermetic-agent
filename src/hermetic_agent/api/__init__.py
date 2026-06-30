"""API module - REST API 层.

4 个子包, 关注点分离:
  - ``hermetic_agent.api.app``       Sanic app 工厂 + Blueprint 注册
  - ``hermetic_agent.api.http``      HTTP 入口 (controllers / schemas / SSE 拦截器)
  - ``hermetic_agent.api.lifecycle`` 启动期 / 关停期编排
  - ``hermetic_agent.api.shared``    API 层共享类型/常量 (预留)

`create_app` 是装配入口, 由 `hermetic_agent.api.app` 提供.
"""
from hermetic_agent.api.app import create_app

__all__ = ["create_app"]
