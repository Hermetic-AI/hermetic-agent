"""test_log_platform_log_context — ContextVar 隔离 + bind/clear."""
from __future__ import annotations

from datetime import datetime

import pytest

from openagent.audit.log import (
    busi_logger as _busi, object_log_writer as _olw, request_logger as _req,
    seq_no as _seq, setup as _setup, sys_logger as _sys,
)
from openagent.audit.log.log_context import (
    REQUEST_ID,
    REQUEST_TIME,
    bind_request_context,
    clear_request_context,
    get_is_log,
    get_request_id,
    get_request_time,
)


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


def test_initial_values_empty():
    assert get_request_id() == ""
    assert get_is_log() is False


def test_bind_and_get():
    now = datetime.now()
    tokens = bind_request_context("T260610182405B00001", now)
    try:
        assert get_request_id() == "T260610182405B00001"
        assert get_request_time() == now
        assert get_is_log() is True
    finally:
        clear_request_context(tokens)


def test_clear_restores_initial():
    tokens = bind_request_context("X", datetime.now())
    clear_request_context(tokens)
    assert get_request_id() == ""
    assert get_is_log() is False


def test_nested_bind():
    """嵌套 bind: 第二次 bind 不应污染第一次的 token, 第一次 clear 应回第一层."""
    now = datetime.now()
    outer = bind_request_context("outer", now)
    inner = bind_request_context("inner", now)
    assert get_request_id() == "inner"
    clear_request_context(inner)
    assert get_request_id() == "outer"
    clear_request_context(outer)
    assert get_request_id() == ""


def test_request_time_default_when_unbound():
    """ContextVar 未 bind 时, get_request_time 兜底 now."""
    REQUEST_TIME.set(None)
    t = get_request_time()
    assert t > datetime(2020, 1, 1)
