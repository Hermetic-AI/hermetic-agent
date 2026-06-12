"""API module - REST API 层.

4 个子包, 关注点分离:
  - ``openagent.api.app``       Sanic app 工厂 + Blueprint 注册
  - ``openagent.api.http``      HTTP 入口 (controllers / schemas / SSE 拦截器)
  - ``openagent.api.lifecycle`` 启动期 / 关停期编排
  - ``openagent.api.shared``    API 层共享类型/常量 (预留)

`create_app` 是装配入口, 由 `openagent.api.app` 提供.
"""
from openagent.api.app import create_app

__all__ = ["create_app"]
