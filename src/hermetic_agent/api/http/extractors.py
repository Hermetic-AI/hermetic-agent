"""api/extractors.py — request-side helpers 集中点.

从历史 ``api/routes.py`` 拆分出来的纯函数模块. 原本``routes.py`` 整段被
P6 重构的 controllers/* 取代, 但里面两个 helper（``_extract_mcp_token`` /
``_resolve_session_directory``）仍被 chat_controller 与 tests 引用.

集中放这里, 避免 controllers 之间重复定义, 也避免给 controllers 增加
过多私有函数降低可读性.
"""
from __future__ import annotations

import os
from typing import Any

import structlog
from sanic.request import Request

logger = structlog.get_logger(__name__)


def extract_mcp_token(request: Request) -> str | None:
    """从请求 header 提取 MCP 认证 token (per-request, 不持久化).

    支持的 header 写法 (按优先级):
    - ``X-MCP-Token: yyyy``        hermetic_agent 推荐形式, 显式
    - ``Authorization: Bearer yyyy``  标准 OAuth 形式, 兜底
    - ``token: yyyy``              业务 SKILL 自定义 header 兜底
                                   (老前端透传时也叫这个名, 单 `token` 头)

    返回 ``None`` 时: 当前请求不带 token, 下游走 token-less 路径
    (MCP 工具调用会 401, SKILL.md 错误处理有兜底话术).

    日志只记 token_present / token_len, **绝不记 token 原文**.
    """
    # 1. X-MCP-Token 优先
    direct = request.headers.get("X-MCP-Token")
    if direct:
        token = direct.strip() or None
        logger.debug(
            "mcp_token_extracted",
            source="X-MCP-Token",
            token_present=bool(token),
            token_len=len(token) if token else 0,
        )
        return token
    # 2. Authorization: Bearer
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip() or None
        logger.debug(
            "mcp_token_extracted",
            source="Authorization-Bearer",
            token_present=bool(token),
            token_len=len(token) if token else 0,
        )
        return token
    # 3. 业务 SKILL 自定义: 单 `token` header (老前端透传, 跟某些 BFF 响应头同名)
    legacy = request.headers.get("token")
    if legacy:
        token = legacy.strip() or None
        logger.debug(
            "mcp_token_extracted",
            source="token",
            token_present=bool(token),
            token_len=len(token) if token else 0,
        )
        return token
    logger.debug("mcp_token_extracted", source="none", token_present=False)
    return None


def resolve_session_directory(request: Request, scenario: Any = None) -> str | None:
    """从 ScenarioMiddleware 注入的 ``request.ctx.scenario`` 提取工作区.

    ScenarioConfig.workspace.workspace_dirs 在 ``loader.py`` 加载 YAML 时
    已经过 placeholder 解析(``${PROJECT_DIR}`` → 实际路径), 直接取
    ``[0]`` 即可.

    Docker 部署时 Hub 看到 ``/app/work`` (ro bind), sandbox 看到
    ``WORKSPACE_PATH``. 因为目录查询是给 opencode 用的, 必须给
    **sandbox 视角**的路径, 优先 env ``WORKSPACE_PATH``, 再退回
    scenario 配置.

    未命中 scenario 时返回 ``None`` — opencode serve 会回落到启动时的
    ``--cwd``, 与 launcher.py 行为一致.
    """
    # 1. 容器内 env 优先 (sandbox 看到的真实路径)
    workspace_path = os.environ.get("WORKSPACE_PATH")
    if workspace_path:
        return workspace_path
    # 2. 退回 scenario.workspace.workspace_dirs[0]
    if scenario is None:
        scenario = getattr(request.ctx, "scenario", None)
    if scenario is None:
        return None
    dirs = getattr(scenario.workspace, "workspace_dirs", None) or []
    return dirs[0] if dirs else None
