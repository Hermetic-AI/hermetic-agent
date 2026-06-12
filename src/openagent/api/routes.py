"""openagent.api.routes — 历史顶层 shim (双重 compat).

P5 时期 ``openagent.api.routes`` 是 1095 行的主路由文件.
P6 把 endpoints 拆到 ``controllers/`` 之后, ``api/routes.py`` 退化为只 re-export
两个 helper (历史 ``_extract_mcp_token`` / ``_resolve_session_directory``).
P0 架构再调整, helper 物理位置变到 ``openagent.api.http.extractors``, 现有
两个 shim 文件:
  - ``openagent.api.routes`` (本文件) — 顶层 6 行 shim, 转发到
  - ``openagent.api.http.routes`` (26 行) — 真正的 shim, 转发到 extractors

API 100% 兼容, 老 import path 全部仍工作.
**新代码不要再 import 这里**; 直接用 ``openagent.api.http.extractors``.
"""
from openagent.api.http.routes import (  # noqa: F401
    _extract_mcp_token,
    _resolve_session_directory,
    extract_mcp_token,
    resolve_session_directory,
)

__all__ = [
    "_extract_mcp_token",
    "_resolve_session_directory",
    "extract_mcp_token",
    "resolve_session_directory",
]
