"""test_log_platform_dto — DTO 字段构造 + 默认值."""
from __future__ import annotations

from datetime import datetime

import pytest

from hermetic_agent.audit.log.dto import BusiLog, LogType, RequestLog, SysLog
from hermetic_agent.audit.log import (
    busi_logger as _busi, object_log_writer as _olw, request_logger as _req,
    seq_no as _seq, setup as _setup, sys_logger as _sys,
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


def test_log_type_enum_values():
    assert LogType.BUSI.value == "busi_log_"
    assert LogType.REQUEST.value == "request_log_"
    assert LogType.APP.value == "app_log_"


def test_busi_log_defaults():
    log = BusiLog()
    assert log.type == ""
    assert log.instanceId == ""
    assert log.reqSeqNo == ""
    assert log.level == "INFO"
    assert log.compress is False
    assert log.infoSize == 0
    assert log.logInfo is None


def test_request_log_defaults():
    log = RequestLog()
    assert log.delay == -1
    assert log.result == "SUCC"
    assert log.mainReqSeqNo == ""
    assert log.bizNo == ""


def test_sys_log_defaults():
    log = SysLog()
    assert log.level == "INFO"
    assert log.threadId == 0
    assert log.category == ""


def test_busi_log_constructed_fields():
    now = datetime.now()
    log = BusiLog(
        type="BUSI_LOG_hermetic_agent",
        instanceId="hub-A",
        reqSeqNo="T260610182405B00001",
        logTime=now,
        level="ERROR",
        logInfo='{"event":"x"}',
        logId=260610182405000001,
    )
    assert log.type == "BUSI_LOG_hermetic_agent"
    assert log.reqSeqNo == "T260610182405B00001"
    assert log.logTime == now
    assert log.level == "ERROR"
