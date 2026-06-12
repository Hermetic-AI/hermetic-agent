"""api/streaming/done_gate.py — SSE done 事件单写哨兵.

修复 P0 报告 #3: ``done`` 事件多次写会导致前端 EventSource 收到多个
``data: {...} done`` 触发 reconnect 风暴. 集中一个 ``DoneGate`` 工具,
业务侧只需要 ``await gate.write_done()``, 内部保证 done 全程只写一次.
"""
from __future__ import annotations

from openagent.providers.streaming import StreamEvent


class DoneGate:
    """``done`` 哨兵: 内部维护一个 ``written`` 布尔, 多次 ``write_done()``
    只生效一次.

    用法::

        gate = DoneGate()
        async for chunk in stream:
            if chunk.type == "done":
                await gate.write_done(resp, chunk)
            else:
                await resp.write(chunk.to_sse())
        # 兜底: 流自然结束但还没写 done, 在 finally 里再写
        await gate.write_done_if_pending(resp)
    """

    __slots__ = ("_written",)

    def __init__(self) -> None:
        self._written = False

    @property
    def written(self) -> bool:
        """是否已写过 done (只读)."""
        return self._written

    async def write_done(
        self, resp, event: StreamEvent | None = None
    ) -> bool:
        """写入 done 事件 (如果还没写过).

        Returns:
            True = 这次写入了; False = 已经被写过, 跳过.
        """
        if self._written:
            return False
        evt = event if event is not None else StreamEvent.done()
        await resp.write(evt.to_sse())
        self._written = True
        return True

    async def write_done_if_pending(self, resp) -> bool:
        """如果还没写过 done, 写一次默认 done 事件.

        用于流末尾的兜底 (keepalive 拦截器在 done/error 时停止心跳, 但
        如果流因为异常路径退出, 业务侧需要保证前端拿到一个 done 哨兵).

        Returns:
            True = 这次写入了; False = 已被写过.
        """
        if self._written:
            return False
        return await self.write_done(resp, StreamEvent.done())

    async def write_error_if_pending(self, resp, *, message: str, code: str = "", retry: int | None = None) -> bool:
        """如果还没写过 done/error, 写一个 error 事件.

        用于 catch 块: 让前端拿到 error 信号而不是空流.
        写完 error 后**不**把 ``_written`` 设为 True — caller 通常还会
        在 finally 里写 done 收尾. 如果 caller 想用 error 作为流的结束,
        自行 ``await self.write_done()`` 紧跟.
        """
        if self._written:
            return False
        await resp.write(
            StreamEvent.error(message=message, code=code, retry=retry).to_sse()
        )
        return True
