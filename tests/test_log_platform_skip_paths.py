"""test_log_platform_skip_paths — 跳过规则."""
from __future__ import annotations

import pytest

from hermetic_agent.audit.log import (
    busi_logger as _busi, object_log_writer as _olw, request_logger as _req,
    seq_no as _seq, setup as _setup, sys_logger as _sys,
)
from hermetic_agent.audit.log.skip_paths import build_skip_predicate


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


def test_skip_health_path():
    p = build_skip_predicate()
    assert p("/health", "GET") is True
    assert p("/ready", "GET") is True
    assert p("/favicon.ico", "GET") is True


def test_skip_static_ext():
    p = build_skip_predicate()
    assert p("/static/foo.js", "GET") is True
    assert p("/assets/main.css", "GET") is True
    assert p("/img/logo.png", "GET") is True


def test_skip_unsupported_method():
    p = build_skip_predicate()
    assert p("/api/x", "OPTIONS") is True
    assert p("/api/x", "HEAD") is True


def test_keep_normal_path():
    p = build_skip_predicate()
    assert p("/agent/chat", "POST") is False
    assert p("/health", "POST") is True


def test_custom_skip_set():
    p = build_skip_predicate(skip_paths=frozenset({"/custom"}))
    assert p("/custom", "GET") is True
    assert p("/health", "GET") is False
