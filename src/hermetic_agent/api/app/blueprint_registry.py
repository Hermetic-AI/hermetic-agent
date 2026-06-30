"""api/blueprint_registry.py — 所有 Blueprint 注册集中点.

把 ``app.blueprint(...)`` 调用从 ``create_app`` 抽到独立函数,
方便:
  - 在 tests / dev script 里**只挂部分** blueprint (e.g. 单元测试只挂 chat_bp)
  - 一次性 grep 看清整个 Hub 暴露的路由面
  - 加新 controller 时**单一**插入点 (避免漏改 ``create_app``)
"""
from __future__ import annotations

from sanic import Sanic

# 路由注册顺序: 跟历史 ``create_app`` 里的顺序保持一致 — 调换顺序可能影响
# (1) 路由匹配的优先级 (Sanic 按注册顺序查表, 前面的优先)
# (2) OpenAPI 文档里端点的展示顺序
# (3) 调试日志里 middleware 看到的端点列表顺序
# 所以新加 controller 时**只能 append 到末尾**, 不要插队.
from hermetic_agent.api.http.controllers.chat_controller import chat_bp
from hermetic_agent.api.http.controllers.mcp_controller import mcp_config_bp
from hermetic_agent.api.http.controllers.pool_controller import pool_bp
from hermetic_agent.api.http.controllers.question_controller import question_bp
from hermetic_agent.api.http.controllers.registry_controller import registry_bp
from hermetic_agent.api.http.controllers.scenario_controller import scenario_bp
from hermetic_agent.api.http.controllers.session_controller import session_bp
from hermetic_agent.api.http.controllers.skill_controller import skill_bp
from hermetic_agent.api.http.controllers.todo_controller import todo_bp
from hermetic_agent.api.http.turn_routes import turn_bp


def register_all_blueprints(app: Sanic) -> None:
    """专门用于注册所有蓝图的函数.

    调用 ``app.blueprint(<bp>)`` 把所有 controller 挂到 Sanic app.
    任何**新增 controller** 都应该在上面的 import 段加一行, 然后在
    本函数末尾 ``app.blueprint(<bp>)`` 一行, 不要往 ``create_app`` 里散.

    P0 改进: 把注册逻辑从 ``create_app`` 抽离, 单一职责, 方便测试子集启动.

    Args:
        app: 当前 Sanic 应用实例.
    """
    # 主业务 (L1 controllers/) — chat/session/registry/pool/scenario
    app.blueprint(chat_bp)
    app.blueprint(session_bp)
    app.blueprint(registry_bp)
    app.blueprint(pool_bp)

    # F3: HITL turn 生命周期端点 (/agent/turn/...)
    app.blueprint(turn_bp)

    # Scenario CRUD 端点 (/agent/scenarios/...)
    app.blueprint(scenario_bp)

    # P7: opencode 原生 question / todo 端点 (代理 /question + /session/:id/todo)
    app.blueprint(question_bp)
    app.blueprint(todo_bp)

    # DB-backed Skill / MCP Config CRUD 端点 (/agent/skills/... / /agent/mcp-configs/...)
    app.blueprint(skill_bp)
    app.blueprint(mcp_config_bp)

    # 业务 auth 代理 (登录 / 验证码) 由业务 SKILL 通过 GenericAuthProxy 注册,
    # 不在基座硬编码. 详见 docs/core-skill-boundary.md §4.5.


__all__ = ["register_all_blueprints"]
