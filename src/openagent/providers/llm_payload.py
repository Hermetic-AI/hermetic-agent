"""LLM 请求体序列化与日志工具.

把即将发往下层 SDK 的完整请求体打成 JSON 友好的 dict, 屏蔽敏感字段
(MCP token / Bearer / token: xxx), 然后通过 structlog 以 ``llm_request``
事件写出 — 默认 INFO 级别, 与其它 chat_* 事件一致.

设计要点:
  * 单一入口 ``log_*_request()`` 由各适配器在 SDK 调用前调用一次;
  * 不修改任何已有 adapter / bridge 的签名, 只加新模块 + 在 hot path
    里多一行 ``log_*(payload)``;
  * token 屏蔽只针对 ``system`` 字符串与 dict 里 str 值, 其它字段原样
    透传 (e.g. ``parts`` / ``tools`` / ``messages`` 都可能很大, 留
    出来给运维看);
  * 由 ``Settings.log_llm_payload`` 统一控制开关, 关闭时直接 no-op
    (而不是打 DEBUG) — 避免无谓字符串构造。
"""
from __future__ import annotations

import re
from typing import Any

import structlog

from openagent.config.settings import Settings, get_settings

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# 敏感字段屏蔽
# ---------------------------------------------------------------------------

# system_prompt 里可能出现的 token 形式. 注意: 顺序敏感, 更具体的先匹配.
_TOKEN_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"MCP_TOKEN:\s*\S+"), "MCP_TOKEN: ***MASKED***"),
    (re.compile(r"Bearer\s+[A-Za-z0-9._\-]+"), "Bearer ***MASKED***"),
    (re.compile(r"(?i)token:\s*[A-Za-z0-9._\-]+"), "token: ***MASKED***"),
)


def mask_sensitive_text(text: str | None) -> str | None:
    """对字符串做 token 屏蔽; 命中即替换, 未命中原样返回."""
    if not text:
        return text
    out = text
    for pat, repl in _TOKEN_PATTERNS:
        out = pat.sub(repl, out)
    return out


def _mask_dict_values(d: dict[str, Any] | None) -> dict[str, Any] | None:
    """递归把 dict 里所有 str 值过一遍 ``mask_sensitive_text``."""
    if d is None:
        return None
    out: dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, str):
            out[k] = mask_sensitive_text(v)
        elif isinstance(v, dict):
            out[k] = _mask_dict_values(v)
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# 开关解析
# ---------------------------------------------------------------------------


def _is_enabled(settings: Settings | None) -> bool:
    """检查 settings.log_llm_payload; settings=None 时按默认 True 处理."""
    if settings is None:
        settings = get_settings()
    return bool(getattr(settings, "log_llm_payload", True))


# ---------------------------------------------------------------------------
# OpenCode
# ---------------------------------------------------------------------------


def build_opencode_payload(
    *,
    session_id: str,
    model_id: str,
    provider_id: str,
    parts: list[dict[str, Any]],
    system: str | None,
    tools: list[dict[str, Any]] | None,
    timeout: float | None,
    extra_query: dict[str, Any] | None,
) -> dict[str, Any]:
    """构造 opencode ``client.session.chat()`` 的完整入参 dict.

    顺序与字段名刻意贴近 SDK, 便于和 opencode serve 抓包对账.
    """
    return {
        "endpoint": "opencode.session.chat",
        "session_id": session_id,
        "model_id": model_id,
        "provider_id": provider_id,
        "parts": parts,
        "system": mask_sensitive_text(system),
        "tools": tools,
        "timeout": timeout,
        "extra_query": extra_query or {},
    }


def log_opencode_request(
    payload: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> None:
    """以 ``llm_request`` 事件把 payload 写入 structlog.

    关闭时 (settings.log_llm_payload=False) 直接 return, 不构造任何
    字符串 — 减少 hot path 开销.
    """
    if not _is_enabled(settings):
        return
    logger.info("llm_request", **payload)


# ---------------------------------------------------------------------------
# Claude Code
# ---------------------------------------------------------------------------


def build_claude_payload(
    *,
    session_id: str,
    prompt: str,
    options: dict[str, Any] | None,
) -> dict[str, Any]:
    """构造 claude-agent-sdk ``client.query()`` 的完整入参 dict."""
    return {
        "endpoint": "claude.query",
        "session_id": session_id,
        "prompt": mask_sensitive_text(prompt),
        "options": _mask_dict_values(options),
    }


def log_claude_request(
    payload: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> None:
    """以 ``llm_request`` 事件把 payload 写入 structlog."""
    if not _is_enabled(settings):
        return
    logger.info("llm_request", **payload)
