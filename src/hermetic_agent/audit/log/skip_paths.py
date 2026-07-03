"""skip_paths — 中间件跳过的路径 / 文件扩展名.

跟 fh-ai ``logMiddleware._skip`` 对齐:

- 路径: ``/-`` / ``/healthcheck`` / 静态资源 / 非标方法
- 扩展名: ``.map .ico .js .css .html ...`` (Hub 多了 ``.svg``/``.webp`` 等,
  Sanic 静态文件可能返)

按需调整 (新增 / 删除) 都不会破坏既有调用, 走 :func:`build_skip_predicate` 工厂.
"""
from __future__ import annotations

from collections.abc import Callable

DEFAULT_SKIP_PATHS: frozenset[str] = frozenset(
    {
        "/-",
        "/healthcheck",
        "/health",
        "/ready",
        "/favicon.ico",
    }
)

DEFAULT_SKIP_FILE_EXT: frozenset[str] = frozenset(
    {
        ".map",
        ".ico",
        ".js",
        ".css",
        ".html",
        ".htm",
        ".jpeg",
        ".jpg",
        ".png",
        ".gif",
        ".svg",
        ".webp",
        ".ttf",
        ".woff",
        ".woff2",
        ".eot",
        ".otf",
        ".ttc",
        ".pkg",
    }
)

DEFAULT_SKIP_METHODS: frozenset[str] = frozenset({"GET", "POST", "PUT", "DELETE"})


def build_skip_predicate(
    skip_paths: frozenset[str] | None = None,
    skip_file_ext: frozenset[str] | None = None,
    skip_methods: frozenset[str] | None = None,
) -> Callable[[str, str], bool]:
    """返回一个 ``(path, method) -> bool`` 判定函数."""
    sp = skip_paths or DEFAULT_SKIP_PATHS
    se = skip_file_ext or DEFAULT_SKIP_FILE_EXT
    sm = skip_methods or DEFAULT_SKIP_METHODS

    def _should_skip(path: str, method: str) -> bool:
        if method not in sm:
            return True
        if path in sp:
            return True
        return any(path.endswith(ext) for ext in se)

    return _should_skip
