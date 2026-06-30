"""api/streaming/keepalive.py — SSE 心跳包装.

SSE 协议下, 中间代理 (Vite / Nginx / Cloud LB) 与浏览器 EventSource 都会
在 30-60s 空闲后关闭连接. 长 LLM 思考 + 多步工具调用经常超过这个阈值,
导致前端看到"流断"但没收到 error/done.

做法: 业务事件空闲超过 ``keepalive_interval`` 秒时, yield ``: keepalive\\n\\n``
(SSE 注释行, 客户端会忽略内容, 但能重置对端 keep-alive 计时器).

行为:
- 业务事件 (text/reasoning/tool/card/...) → 原样 yield
- 业务事件空闲超阈值 → yield SSE 注释行
- ``done`` / ``error`` 事件 → 原样 yield 然后退出 (不再 heartbeat)
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hermetic_agent.providers.streaming import StreamEvent

# 心跳注释行的标准 SSE 格式 (RFC: "comment lines start with ':'")
KEEPALIVE_SSE_LINE = ": keepalive\n\n"

# 默认心跳间隔 (秒). 短了浪费带宽, 长了对端可能误判 idle.
# settings.sse_keepalive_interval 优先, 这里作为兜底.
DEFAULT_KEEPALIVE_INTERVAL = 15.0


def _sse_keepalive_interval() -> float:
    """从 settings 读 keepalive 间隔, 失败时返回模块默认值."""
    try:
        from hermetic_agent.config.settings import get_settings
        return float(get_settings().sse_keepalive_interval)
    except Exception:  # pragma: no cover
        return DEFAULT_KEEPALIVE_INTERVAL


async def stream_with_keepalive(
    iterator: AsyncIterator[StreamEvent | str],
    *,
    keepalive_interval: float | None = None,
) -> AsyncIterator[StreamEvent | str]:
    """SSE 心跳包装 — 业务事件空闲时插入 SSE 注释行, 防止中间代理断连.

    Args:
        iterator: 业务事件流; 元素可以是 ``StreamEvent`` (走 ``.to_sse()``)
            或纯字符串 (心跳注释行已经拼好的情况, 由 caller 直接写 resp).
        keepalive_interval: 心跳间隔 (秒); None 时从 settings 读.

    Yields:
        - ``StreamEvent`` 实例, 由 caller 调 ``.to_sse()`` 后写给客户端
        - 字符串 (心跳注释行) — caller 直接写 resp 不再处理
    """
    if keepalive_interval is None:
        keepalive_interval = _sse_keepalive_interval()

    loop = asyncio.get_event_loop()
    last_yield = loop.time()

    async for event in iterator:
        yield event
        # done / error 事件之后不再发心跳, 让流自然结束
        if hasattr(event, "type") and event.type in ("done", "error"):
            return
        now = loop.time()
        if now - last_yield >= keepalive_interval:
            yield KEEPALIVE_SSE_LINE
        last_yield = now
