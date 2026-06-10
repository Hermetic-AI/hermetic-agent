"""路径规范化 + 拦截 — L5 Infrastructure Layer.

三组硬规则:
  1. BLOCKED_PATTERNS  — 永远不通过（凭据类文件）
  2. deny_dirs         — 用户配置的禁止目录
  3. workspace_dirs    — 用户配置的工作区（白名单前缀）

判断顺序: BLOCKED_PATTERNS > deny_dirs > workspace_dirs.

BLOCKED_PATTERNS 从 ``settings.path_blocked_patterns`` 读, 保留模块级
``BLOCKED_PATTERNS_FALLBACK`` 作为兜底 (settings 不可用场景).
"""

from __future__ import annotations

import fnmatch
import os
import sys
from pathlib import Path

# 这些模式**永远**不允许, 跟用户配置无关.
# 用 POSIX-style 路径模式（forward slashes）匹配, Windows 上也用 posixpath.
BLOCKED_PATTERNS_FALLBACK: list[str] = [
    "**/.env",
    "**/.env.*",
    "**/id_rsa",
    "**/id_ed25519",
    "**/id_*",
    "**/.ssh/**",
    "**/.aws/credentials",
    "**/.config/gcloud/**",
    "**/*.pem",
    "**/*.key",
    "**/*.p12",
    "**/secrets/**",
    "**/credentials/**",
]


def _blocked_patterns() -> list[str]:
    """从 settings 读 blocked patterns. 失败时返回模块常量."""
    try:
        from openagent.config.settings import get_settings

        return list(get_settings().path_blocked_patterns)
    except Exception:  # pragma: no cover
        return list(BLOCKED_PATTERNS_FALLBACK)


# 向后兼容: 老代码 ``from ... import BLOCKED_PATTERNS`` 仍能工作
# (拿到的是兜底值). 真正校验走 ``_blocked_patterns()``.
BLOCKED_PATTERNS: list[str] = list(BLOCKED_PATTERNS_FALLBACK)


def _to_posix(p: str) -> str:
    """把路径里的反斜杠换成正斜杠, 用于 glob 匹配."""
    return p.replace(os.sep, "/")


def normalize(path: str) -> str:
    """规范化路径: 解 `..` 和 symlink, Windows 上大小写归一.

    返回一个**绝对**路径字符串.
    """
    p = Path(path).expanduser()
    try:
        resolved = p.resolve()
    except (OSError, RuntimeError):
        # 路径不存在 / 循环 symlink — 退化到 absolute
        resolved = p.absolute()
    if sys.platform == "win32":
        resolved = Path(os.path.normcase(str(resolved)))
    return str(resolved)


def is_blocked(path: str) -> bool:
    """path 是否命中 BLOCKED_PATTERNS 任一模式."""
    posix = _to_posix(path)
    # 拿 basename 和完整路径都试一下
    basename = posix.rsplit("/", 1)[-1]
    for pattern in _blocked_patterns():
        if fnmatch.fnmatch(posix, pattern):
            return True
        if fnmatch.fnmatch(basename, pattern):
            return True
    return False


def _is_prefix(parent: str, child: str) -> bool:
    """parent 是否是 child 的前缀（路径语义, 非字符串前缀）.

    - Windows 上大小写不敏感
    - 必须以分隔符结尾, 避免 /work/x 匹配 /work/xyz
    """
    if sys.platform == "win32":
        parent_n = os.path.normcase(parent)
        child_n = os.path.normcase(child)
    else:
        parent_n = parent
        child_n = child
    parent_n = parent_n.rstrip(os.sep) or parent_n
    if child_n == parent_n:
        return True
    sep = os.sep
    return child_n.startswith(parent_n + sep)


def is_within(workspace_dirs: list[str], path: str) -> bool:
    """path 是否落在任一 workspace_dir 之下.

    要求:
      1. 解析过的 path 至少满足一个 workspace_dirs 前缀
      2. **不**命中 BLOCKED_PATTERNS
      3. 单独 deny_dirs 列表由调用方在 policy engine 里检查（这里不接收）
    """
    if not workspace_dirs:
        return False
    resolved = normalize(path)
    for ws in workspace_dirs:
        try:
            ws_resolved = normalize(ws)
        except (TypeError, ValueError):
            continue
        if _is_prefix(ws_resolved, resolved):
            return True
    return False


def is_denied(path: str, deny_dirs: list[str]) -> bool:
    """path 是否落在任一 deny_dir 之下（已规范化的前缀匹配）."""
    if not deny_dirs:
        return False
    resolved = normalize(path)
    for d in deny_dirs:
        try:
            d_resolved = normalize(d)
        except (TypeError, ValueError):
            continue
        if _is_prefix(d_resolved, resolved):
            return True
    return False


def check_path(
    workspace_dirs: list[str],
    deny_dirs: list[str],
    path: str,
) -> tuple[bool, str]:
    """综合判定: 返回 (allowed, reason).

    优先级: BLOCKED_PATTERNS > deny_dirs > 不在 workspace_dirs.
    """
    if is_blocked(path):
        return False, "path matches BLOCKED_PATTERNS (credentials / .env / ssh key)"
    if is_denied(path, deny_dirs):
        return False, "path is under deny_dirs"
    if not is_within(workspace_dirs, path):
        return False, "path is not within any workspace_dir"
    return True, "ok"


__all__ = [
    "BLOCKED_PATTERNS",
    "normalize",
    "is_blocked",
    "is_within",
    "is_denied",
    "check_path",
]
