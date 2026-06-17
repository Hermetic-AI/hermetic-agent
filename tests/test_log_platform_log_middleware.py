"""test_log_platform_log_middleware — Sanic request/response 钩子.

用 ``sanic_testing`` 的 ``app.asgi_client`` 跑 in-process HTTP, 验证:
- 跳过路径 (/health, /ready, 静态资源) 不发 RequestLog
- 正常路径发 2 条 (start + end)
- 入口生成 reqSeqNo (放 request.ctx.req_seq_no)
- X-Request-ID header 透传
- 异常响应 result=ERROR, errorMessage 有值
"""
from __future__ import annotations

import json
import os

import pytest
import sanic_testing

from openagent.audit.log import (
    busi_logger as _busi, object_log_writer as _olw, request_logger as _req,
    seq_no as _seq, setup as _setup, sys_logger as _sys,
)
from openagent.audit.log.object_log_writer import ObjectLogWriter
from openagent.audit.log.request_logger import init_request_logger


@pytest.fixture(autouse=True)
def _reset():
    _olw.ObjectLogWriter.reset_for_test()
    _seq.reset_for_test()
    _setup.reset_for_test()
    _busi._busi_logger = None
    _req._request_logger = None
    _sys._sys_logger = None
    yield
    _olw.ObjectLogWriter.reset_for_test()
    _seq.reset_for_test()
    _setup.reset_for_test()
    _busi._busi_logger = None
    _req._request_logger = None
    _sys._sys_logger = None


def _make_app():
    from openagent.api.app.app import create_app
    from openagent.config.settings import Settings
    return create_app(Settings(
        log_use_redis_log=False,
        log_system_type="openagent_test",
        storage_backend="memory",
    ))


@pytest.mark.asyncio
async def test_health_path_skipped():
    app = _make_app()
    init_request_logger("openagent_test")
    ObjectLogWriter.init(use_redis=False, queue_name="t", max_queue_size=10)
    _, response = await app.asgi_client.get("/health")
    assert response.status_code == 200
    items = ObjectLogWriter.get_instance().drain()
    assert items == [], f"健康检查不该发 RequestLog, 实际: {items}"


@pytest.mark.asyncio
async def test_normal_path_emits_start_and_end():
    from sanic.response import text
    app = _make_app()
    init_request_logger("openagent_test")
    ObjectLogWriter.init(use_redis=False, queue_name="t", max_queue_size=10)

    @app.get("/_test_normal")
    async def _h(req):
        return text("ok", status=200)

    _, response = await app.asgi_client.get("/_test_normal")
    assert response.status_code == 200
    items = ObjectLogWriter.get_instance().drain()
    assert len(items) == 2
    start, end = (json.loads(x) for x in items)
    assert start["type"] == "REQUEST_LOG_OPENAGENT_TEST"
    assert start["delay"] == -1
    assert end["delay"] >= 0
    assert end["result"] == "SUCC"


@pytest.mark.asyncio
async def test_x_request_id_header_passthrough():
    from sanic.response import text
    app = _make_app()
    init_request_logger("openagent_test")
    ObjectLogWriter.init(use_redis=False, queue_name="t", max_queue_size=10)

    @app.get("/_test_xid")
    async def _h(req):
        return text("ok", status=200)

    custom_id = "T-CLIENT-PROVIDED-001"
    _, response = await app.asgi_client.get(
        "/_test_xid", headers={"X-Request-ID": custom_id},
    )
    assert response.status_code == 200
    items = ObjectLogWriter.get_instance().drain()
    assert items, "应有 RequestLog"
    start = json.loads(items[0])
    assert start["reqSeqNo"] == custom_id


@pytest.mark.asyncio
async def test_4xx_response_result_error():
    from sanic.response import text
    from sanic.exceptions import NotFound
    app = _make_app()
    init_request_logger("openagent_test")
    ObjectLogWriter.init(use_redis=False, queue_name="t", max_queue_size=10)

    @app.get("/_test_4xx")
    async def _h(req):
        raise NotFound("not found")

    _, response = await app.asgi_client.get("/_test_4xx")
    assert response.status_code == 404
    items = ObjectLogWriter.get_instance().drain()
    end = json.loads(items[-1])
    assert end["result"] == "ERROR"
    assert "404" in end["errorMessage"]
