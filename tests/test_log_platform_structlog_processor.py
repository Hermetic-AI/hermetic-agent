"""test_log_platform_structlog_processor — structlog processor 钩子.

覆盖:
- ``IS_LOG=False`` 时不写
- ObjectLogWriter 未 init 时不写
- ``IS_LOG=True`` + writer 已 init → 写 BusiLog, ``type`` 字段正确, ``logInfo``
  包含 event + kwargs
"""
from __future__ import annotations

import json

import pytest
import structlog

from openagent.audit.log import (
    busi_logger as _busi, object_log_writer as _olw, request_logger as _req,
    seq_no as _seq, setup as _setup, sys_logger as _sys,
)
from openagent.audit.log.log_context import (
    bind_request_context,
    clear_request_context,
)
from openagent.audit.log.object_log_writer import ObjectLogWriter
from openagent.audit.log.structlog_processor import platform_log_processor


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


def test_processor_noop_when_is_log_false():
    ObjectLogWriter.init(use_redis=False, queue_name="t", max_queue_size=10)
    out = platform_log_processor(None, "info", {"event": "x", "level": "info"})
    assert out == {"event": "x", "level": "info"}
    assert ObjectLogWriter.get_instance().drain() == []


def test_processor_noop_when_no_writer():
    out = platform_log_processor(None, "info", {"event": "x", "level": "info"})
    assert out == {"event": "x", "level": "info"}


def test_processor_emits_busi_log():
    ObjectLogWriter.init(use_redis=False, queue_name="t", max_queue_size=10)
    tokens = bind_request_context("T001", __import__("datetime").datetime.now())
    try:
        out = platform_log_processor(
            None,
            "info",
            {
                "event": "chat_request",
                "level": "info",
                "session_id": "S1",
                "user_id": "U1",
            },
        )
        assert out["event"] == "chat_request"
        items = ObjectLogWriter.get_instance().drain()
        assert len(items) == 1
        parsed = json.loads(items[0])
        assert parsed["type"] == "BUSI_LOG_OPENAGENT"
        assert parsed["reqSeqNo"] == "T001"
        assert parsed["level"] == "INFO"
        assert "chat_request" in parsed["logInfo"]
        assert "session_id" in parsed["logInfo"]
    finally:
        clear_request_context(tokens)


def test_processor_drops_internal_keys():
    ObjectLogWriter.init(use_redis=False, queue_name="t", max_queue_size=10)
    tokens = bind_request_context("T001", __import__("datetime").datetime.now())
    try:
        platform_log_processor(
            None, "info",
            {
                "event": "x", "level": "info",
                "timestamp": "2026-06-10",
                "_record": "should_not_serialize",
            },
        )
        items = ObjectLogWriter.get_instance().drain()
        parsed = json.loads(items[0])
        assert "timestamp" not in parsed["logInfo"]
        assert "_record" not in parsed["logInfo"]
    finally:
        clear_request_context(tokens)


def test_processor_swallows_exceptions():
    """processor 自身不能抛异常 — 写日志失败绝不能影响主业务."""
    ObjectLogWriter.init(use_redis=False, queue_name="t", max_queue_size=10)
    out = platform_log_processor(
        None, "info", {"event": "x", "level": "info", "unserializable": object()},
    )
    assert out["event"] == "x"
