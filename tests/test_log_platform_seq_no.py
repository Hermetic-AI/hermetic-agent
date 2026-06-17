"""test_log_platform_seq_no — INSTANCE_ID + get_date_seq_no."""
from __future__ import annotations

import os

import pytest

from openagent.audit.log import (
    busi_logger as _busi, object_log_writer as _olw, request_logger as _req,
    seq_no as _seq, setup as _setup, sys_logger as _sys,
)
from openagent.audit.log.seq_no import (
    get_date_seq_no,
    get_instance_id,
    init_instance_id,
    reset_for_test,
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


def test_init_instance_id_explicit():
    assert init_instance_id(env_override="hub-A") == "hub-A"
    assert get_instance_id() == "hub-A"


def test_init_instance_id_env(monkeypatch):
    monkeypatch.setenv("AGENT_SCHEDULER_LOG_INSTANCE_ID", "env-B")
    assert init_instance_id() == "env-B"
    assert get_instance_id() == "env-B"


def test_init_instance_id_auto():
    if os.environ.get("AGENT_SCHEDULER_LOG_INSTANCE_ID"):
        del os.environ["AGENT_SCHEDULER_LOG_INSTANCE_ID"]
    reset_for_test()
    iid = init_instance_id()
    assert iid
    assert iid != "UNKNOWN"
    assert get_instance_id() == iid


def test_get_date_seq_no_monotonic():
    reset_for_test()
    s1 = get_date_seq_no("LOG_ID")
    s2 = get_date_seq_no("LOG_ID")
    s3 = get_date_seq_no("LOG_ID")
    assert s2 > s1
    assert s3 > s2


def test_get_date_seq_no_separate_keys():
    reset_for_test()
    a = get_date_seq_no("KEY_A")
    b = get_date_seq_no("KEY_B")
    assert a != b
    assert a > 0 and b > 0


def test_get_date_seq_no_format_20_digits():
    reset_for_test()
    s = get_date_seq_no("LOG_ID")
    assert s > 10**19
    assert s < 10**20
