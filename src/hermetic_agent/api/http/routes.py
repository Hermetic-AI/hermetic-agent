"""api/http/routes.py — 历史 P5/P6 阶段兼容 shim.

P6 重构把 endpoint 拆分到 ``controllers/*.py`` 后, 老的
``hermetic_agent.api.routes`` (原最外层) 模块里仍有两个 helper 公开函数:
  - ``_extract_mcp_token``
  - ``_resolve_session_directory``

P0 架构调整后:
  - 物理位置: ``hermetic_agent.api.http.extractors``
  - 兼容 shim: 仍保留 ``hermetic_agent.api.routes`` (顶层, 6 行) + 本文件
    (历史 P5 写过的, 后来又从 controllers 中重定向过来). 双重 shim 维持
    100% 兼容.

旧 import path 在 tests 里仍使用:
  - ``from hermetic_agent.api.routes import _extract_mcp_token`` (test_mcp_token_config)
  - ``from hermetic_agent.api.http.routes import _resolve_session_directory`` (test_chat_stream_integration)

**新代码不要再 import 这里**; 直接用 ``hermetic_agent.api.http.extractors``.
"""
from hermetic_agent.api.http.extractors import extract_mcp_token, resolve_session_directory

# 兼容旧名字 (前导下划线)
_extract_mcp_token = extract_mcp_token
_resolve_session_directory = resolve_session_directory

__all__ = [
    "_extract_mcp_token",
    "_resolve_session_directory",
    "extract_mcp_token",
    "resolve_session_directory",
]
