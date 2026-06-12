"""openagent.api.lifecycle — 启动期 / 关停期编排.

职责 (本子包):
  - ``lifecycle.py``            startup / shutdown — 装配 + 释放各子系统
  - ``scenario_lifecycle.py``    init_scenarios — 启动期 scenario 加载
  - ``readiness.py``             /ready 端点的健康检查逻辑
  - ``scenario_models.py``       Pydantic models for /agent/scenarios/* endpoints

不放在这里的东西:
  - app 工厂 (见 openagent.api.app)
  - 任何 controller / HTTP routing (见 openagent.api.http)

注: 严格说 ``scenario_models.py`` 是 Pydantic schema, 跟 ``http/schemas.py``
同类, 但它仅被 scenario CRUD 端点用, 且依赖 lifecycle 状态
(app.ctx.scenario_registry), 归 lifecycle 更准确.
"""
from openagent.api.lifecycle.lifecycle import shutdown, startup
from openagent.api.lifecycle.readiness import build_ready_response
from openagent.api.lifecycle.scenario_lifecycle import find_project_root, init_scenarios

__all__ = [
    "build_ready_response",
    "find_project_root",
    "init_scenarios",
    "shutdown",
    "startup",
]
