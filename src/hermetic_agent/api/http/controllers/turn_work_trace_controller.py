"""TurnWorkTrace Controller — 4 只读 GET endpoints.

路径前缀: ``/agent``.

Endpoints:
- GET /agent/turns/{turn_id}/work-trace              → 完整 trace JSON
- GET /agent/turns/{turn_id}/work-trace/stream      → SSE 实时跟踪 (重放历史)
- GET /agent/turns/{turn_id}/work-trace/products/{product_id}
- GET /agent/sessions/{session_id}/work-traces?limit=N

设计文档: ``docs/superpowers/specs/2026-06-30-persistent-work-trace-design.md §5``.
"""
from __future__ import annotations

import json
from typing import Any

import structlog
from sanic import Blueprint
from sanic.request import Request
from sanic.response import JSONResponse, ResponseStream

from hermetic_agent.store.dto.work_trace import ProductContentResponse

logger = structlog.get_logger(__name__)

trace_bp = Blueprint("turn_work_trace", url_prefix="/agent")


def _services(request: Request) -> Any:
    """从 ``app.ctx.services`` 取 ServiceContainer."""
    return getattr(request.app.ctx, "services", None)


@trace_bp.get("/turns/<turn_id:str>/work-trace")
async def get_trace(request: Request, turn_id: str) -> JSONResponse:
    """完整 trace JSON 出参."""
    svc = _services(request)
    if svc is None or not hasattr(svc, "work_trace"):
        return JSONResponse(
            {"error": "work_trace service not ready"}, status=503,
        )
    resp = await svc.work_trace.get_response(turn_id)
    if resp is None:
        return JSONResponse(
            {"error": f"trace not found: {turn_id}", "code": "TRACE_NOT_FOUND"},
            status=404,
        )
    return JSONResponse(resp.model_dump())


@trace_bp.get("/turns/<turn_id:str>/work-trace/stream")
async def stream_trace(request: Request, turn_id: str) -> ResponseStream:
    """SSE 流式回放 trace (前端 usePastTrace / replay 用)."""
    svc = _services(request)
    if svc is None or not hasattr(svc, "work_trace"):
        async def _err(resp: ResponseStream) -> None:
            await resp.write(
                f"data: {json.dumps({'type': 'error', 'data': {'message': 'work_trace service not ready'}})}\n\n".encode()
            )
            await resp.eof()
        return ResponseStream(_err, content_type="text/event-stream", status=503)

    async def _stream(resp: ResponseStream) -> None:
        trace = await svc.work_trace.get_response(turn_id)
        if trace is None:
            await resp.write(
                f"data: {json.dumps({'type': 'error', 'data': {'code': 'TRACE_NOT_FOUND', 'message': 'trace not found'}})}\n\n".encode()
            )
            await resp.eof()
            return
        for ev in trace.events:
            line = json.dumps(
                {"type": ev.kind, "data": ev.payload},
                ensure_ascii=False,
            )
            await resp.write(f"data: {line}\n\n".encode())
        await resp.write(b"data: {\"type\": \"done\", \"data\": {}}\n\n")
        await resp.eof()

    return ResponseStream(_stream, content_type="text/event-stream")


@trace_bp.get("/turns/<turn_id:str>/work-trace/products/<product_id:str>")
async def get_product(
    request: Request, turn_id: str, product_id: str,
) -> JSONResponse:
    """拉单个产物内容.

    v1: 只回 product 元信息 (path / url / mime), 不 inline 文件内容.
    真实内容按需走 storage / object store (后续 Phase).
    """
    svc = _services(request)
    if svc is None or not hasattr(svc, "work_trace"):
        return JSONResponse(
            {"error": "work_trace service not ready"}, status=503,
        )
    trace = await svc.work_trace.get_response(turn_id)
    if trace is None:
        return JSONResponse(
            {"error": f"trace not found: {turn_id}", "code": "TRACE_NOT_FOUND"},
            status=404,
        )
    for ev in trace.events:
        if ev.kind == "product" and ev.payload.get("product_id") == product_id:
            return JSONResponse(
                ProductContentResponse(
                    product_id=product_id,
                    turn_id=turn_id,
                    kind=ev.payload.get("kind", "text"),
                    path=ev.payload.get("path"),
                    url=ev.payload.get("url"),
                    mime=ev.payload.get("mime"),
                    size_bytes=ev.payload.get("size_bytes"),
                ).model_dump()
            )
    return JSONResponse(
        {"error": f"product {product_id} not found", "code": "PRODUCT_NOT_FOUND"},
        status=404,
    )


@trace_bp.get("/sessions/<session_id:str>/work-traces")
async def list_session_traces(request: Request, session_id: str) -> JSONResponse:
    """session 下最近 N 个 turn trace 索引 (不带完整 events)."""
    svc = _services(request)
    if svc is None or not hasattr(svc, "work_trace"):
        return JSONResponse(
            {"error": "work_trace service not ready"}, status=503,
        )
    try:
        limit = int(request.args.get("limit", "20"))
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, 100))
    items = await svc.work_trace.list_by_session(session_id, limit=limit)
    return JSONResponse(
        {"items": [i.model_dump() for i in items], "total": len(items)},
    )


__all__ = ["trace_bp"]
