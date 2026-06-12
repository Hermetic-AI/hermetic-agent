"""openagent.api.http — HTTP 入口层.

职责 (本子包):
  - ``schemas.py``        Pydantic request/response models
  - ``routes.py``         历史兼容 shim (re-export extractors; P6 后 routes.py
                          1095 行 endpoint 拆分到 controllers/)
  - ``extractors.py``     request-side helpers (token / directory)
  - ``logging_setup.py``  structlog + Rich 双模式配置
  - ``turn_routes.py``    HITL turn 生命周期 5 个端点
  - ``streaming/``        SSE 拦截器子包: keepalive / ask_user / done_gate /
                          turn_bridge / route_hints
  - ``controllers/``     所有 Sanic Blueprint (auth / chat / pool / question /
                          registry / scenario / session / todo)

不放在这里的东西:
  - app 工厂 (见 openagent.api.app)
  - 启动期 lifecycle (见 openagent.api.lifecycle)
"""
