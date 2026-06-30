"""LogMiddleware — Sanic request/response middleware, 仿照 fh-ai ``logMiddleware``.

职责:
1. 入口生成 ``reqSeqNo`` (请求头 ``X-Request-ID`` 优先, 兜底自生成) + 绑定 ContextVar
2. 跳过不需要日志的路径 (``/health`` / ``/ready`` / 静态资源)
3. 发 ``RequestLog`` start (``delay=-1``)
4. 响应阶段发 ``RequestLog`` end (``delay`` / ``result`` / ``errorMessage``)
5. 跨服务主链 / 业务流水号从请求头读 (``main_request_seq_no`` / ``bizNo``)
6. ``finally`` 清 ContextVar (跨请求不污染)

Sanic 25 行为: ``request`` middleware 也能注册 ``response`` 钩子 (同实例, 不同 method),
让 start + end 共用 ``self._tokens`` 状态. ``ScenarioMiddleware`` 注释里也提了这点.
"""
from __future__ import annotations

from datetime import datetime

from sanic.request import Request
from sanic.response import BaseHTTPResponse

from hermetic_agent.audit.log.log_context import (
    bind_request_context,
    clear_request_context,
)
from hermetic_agent.audit.log.request_logger import RequestLogger
from hermetic_agent.audit.log.seq_no import get_date_seq_no
from hermetic_agent.audit.log.skip_paths import build_skip_predicate


def _generate_req_seq_no() -> str:
    """生成 reqSeqNo. 格式: ``T<YYMMDDHHMMSS><A-Z><5位序号>``.

    例: ``T260610182405B00001``.
    """
    now = datetime.now()
    ts = now.strftime("%y%m%d%H%M%S")
    seq = get_date_seq_no("WEB_REQ_NO") % 100000
    letter = chr(ord("A") + (seq % 26))
    return f"T{ts}{letter}{seq:05d}"


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    if request.ip:
        return request.ip
    return ""


class LogMiddleware:
    """Sanic request/response middleware.

    用法::

        m = LogMiddleware(request_logger)
        app.register_middleware(m, "request")
        app.register_middleware(m, "response")

    依赖:
    - :class:`RequestLogger`  由 :func:`setup_log_platform` 启动期注入
    - :func:`bind_request_context`  跨 logger 共享 req_id
    """

    def __init__(self, request_logger: RequestLogger) -> None:
        self._request_logger = request_logger
        self._should_skip = build_skip_predicate()
        self._tokens = None

    async def __call__(
        self, request: Request, response: BaseHTTPResponse | None = None,
    ) -> None:
        """Sanic request/response middleware 钩子.

        同一个实例, 用 ``register_middleware(log_mw, "request")`` 和
        ``register_middleware(log_mw, "response")`` 各注册一次. Sanic
        response 阶段 ``response`` 参数有值, request 阶段为 None.
        """
        if response is None:
            await self._on_request(request)
        else:
            await self._on_response(request, response)

    async def _on_request(self, request: Request) -> None:
        if self._should_skip(request.path, request.method):
            request.ctx.log_skip = True
            return
        req_seq_no = (
            request.headers.get("x-request-id", "").strip() or _generate_req_seq_no()
        )
        start_time = datetime.now()
        request.ctx.req_seq_no = req_seq_no
        request.ctx.req_start_time = start_time
        request.ctx.log_done = False
        self._tokens = bind_request_context(req_seq_no, start_time)
        self._request_logger.write_start(
            req_seq_no=req_seq_no,
            service_name=request.path,
            ip=_client_ip(request),
            main_req_seq_no=request.headers.get("main_request_seq_no", "").strip(),
            biz_no=request.headers.get("bizNo", "").strip(),
        )

    async def _on_response(
        self, request: Request, response: BaseHTTPResponse,
    ) -> None:
        if getattr(request.ctx, "log_skip", False):
            return
        if getattr(request.ctx, "log_done", False):
            return
        request.ctx.log_done = True
        start = getattr(request.ctx, "req_start_time", None) or datetime.now()
        delay_ms = int((datetime.now() - start).total_seconds() * 1000)
        status = getattr(response, "status", 200) or 200
        result = "ERROR" if status >= 400 else "SUCC"
        err_msg = ""
        if status >= 400:
            err_msg = f"HTTP {status}"
        self._request_logger.write_end(
            req_seq_no=getattr(request.ctx, "req_seq_no", ""),
            service_name=request.path,
            ip=_client_ip(request),
            delay_ms=delay_ms,
            result=result,
            error_message=err_msg,
        )
        if self._tokens is not None:
            clear_request_context(self._tokens)
            self._tokens = None
