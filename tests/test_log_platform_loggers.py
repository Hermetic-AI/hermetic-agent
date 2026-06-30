"""test_log_platform_loggers — BusiLogger / RequestLogger / SysLogger 门面."""
from __future__ import annotations

import json

import pytest

from hermetic_agent.audit.log import (
    busi_logger as _busi, object_log_writer as _olw, request_logger as _req,
    seq_no as _seq, setup as _setup, sys_logger as _sys,
)
from hermetic_agent.audit.log.busi_logger import BusiLogger, init_busi_logger
from hermetic_agent.audit.log.dto import BusiLog
from hermetic_agent.audit.log.log_context import bind_request_context, clear_request_context
from hermetic_agent.audit.log.object_log_writer import ObjectLogWriter
from hermetic_agent.audit.log.request_logger import RequestLogger, init_request_logger
from hermetic_agent.audit.log.sys_logger import SysLogger, init_sys_logger


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


def test_busi_logger_type_prefix():
    b = init_busi_logger("HERMETIC_AGENT")
    assert b.type_prefix == "BUSI_LOG_HERMETIC_AGENT"


def test_busi_logger_emits_when_writer_initialized():
    ObjectLogWriter.init(use_redis=False, queue_name="t", max_queue_size=10)
    b = init_busi_logger("HERMETIC_AGENT")
    b.info("test_event", key="value")
    items = ObjectLogWriter.get_instance().drain()
    assert len(items) == 1
    parsed = json.loads(items[0])
    assert parsed["type"] == "BUSI_LOG_HERMETIC_AGENT"
    assert parsed["level"] == "INFO"
    assert '"event"' in parsed["logInfo"]
    assert parsed["memo"]


def test_busi_logger_noop_without_writer():
    b = init_busi_logger("HERMETIC_AGENT")
    b.info("test_event")
    assert ObjectLogWriter.get_instance() is None


def test_busi_logger_picks_context_request_id():
    ObjectLogWriter.init(use_redis=False, queue_name="t", max_queue_size=10)
    b = init_busi_logger("HERMETIC_AGENT")
    tokens = bind_request_context("T_TEST_001", __import__("datetime").datetime.now())
    try:
        b.info("inside_request")
        items = ObjectLogWriter.get_instance().drain()
        parsed = json.loads(items[0])
        assert parsed["reqSeqNo"] == "T_TEST_001"
    finally:
        clear_request_context(tokens)


def test_busi_logger_levels():
    ObjectLogWriter.init(use_redis=False, queue_name="t", max_queue_size=10)
    b = init_busi_logger("HERMETIC_AGENT")
    b.warning("w")
    b.error("e")
    b.debug("d")
    items = ObjectLogWriter.get_instance().drain()
    assert len(items) == 3
    levels = [json.loads(x)["level"] for x in items]
    assert levels == ["WARN", "ERROR", "DEBUG"]


def test_request_logger_type_prefix():
    r = init_request_logger("HERMETIC_AGENT")
    assert r.type_prefix == "REQUEST_LOG_HERMETIC_AGENT"


def test_request_logger_start_end():
    ObjectLogWriter.init(use_redis=False, queue_name="t", max_queue_size=10)
    r = init_request_logger("HERMETIC_AGENT")
    r.write_start("T001", "/chat", "127.0.0.1", main_req_seq_no="MAIN", biz_no="B1")
    r.write_end("T001", "/chat", "127.0.0.1", delay_ms=120, result="SUCC")
    items = ObjectLogWriter.get_instance().drain()
    assert len(items) == 2
    start, end = (json.loads(x) for x in items)
    assert start["type"] == "REQUEST_LOG_HERMETIC_AGENT"
    assert start["delay"] == -1
    assert start["mainReqSeqNo"] == "MAIN"
    assert start["bizNo"] == "B1"
    assert end["delay"] == 120
    assert end["result"] == "SUCC"


def test_request_logger_noop_without_writer():
    r = init_request_logger("HERMETIC_AGENT")
    r.write_start("T001", "/chat", "127.0.0.1")
    r.write_end("T001", "/chat", "127.0.0.1", delay_ms=0, result="SUCC")
    assert ObjectLogWriter.get_instance() is None


def test_sys_logger_emits():
    ObjectLogWriter.init(use_redis=False, queue_name="t", max_queue_size=10)
    s = init_sys_logger("HERMETIC_AGENT")
    s.info("startup", "service_started", port=8000)
    s.error("runtime", "init_failed", error="timeout")
    items = ObjectLogWriter.get_instance().drain()
    assert len(items) == 2
    parsed = [json.loads(x) for x in items]
    assert parsed[0]["type"] == "APP_LOG_HERMETIC_AGENT"
    assert parsed[0]["level"] == "INFO"
    assert parsed[0]["category"] == "startup"
    assert parsed[1]["level"] == "ERROR"
    assert parsed[1]["category"] == "runtime"
