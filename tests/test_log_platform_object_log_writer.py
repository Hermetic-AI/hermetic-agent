"""test_log_platform_object_log_writer — 内存队列 + drain + file + tee."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from hermetic_agent.audit.log import (
    busi_logger as _busi, object_log_writer as _olw, request_logger as _req,
    seq_no as _seq, setup as _setup, sys_logger as _sys,
)
from hermetic_agent.audit.log.dto import BusiLog, RequestLog
from hermetic_agent.audit.log.object_log_writer import ObjectLogWriter


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


@pytest.fixture
def tmp_log_file(tmp_path: Path) -> str:
    return str(tmp_path / "platform.log")


def test_init_creates_singleton():
    w = ObjectLogWriter.init(
        use_redis=False, queue_name="test", max_queue_size=10,
    )
    assert w is ObjectLogWriter.get_instance()


def test_write_busi_then_drain():
    w = ObjectLogWriter.init(
        use_redis=False, queue_name="test", max_queue_size=10,
    )
    w.write_busi(BusiLog(type="BUSI_LOG_X", logTime=datetime.now(), logInfo="hi"))
    w.write_busi(BusiLog(type="BUSI_LOG_X", logTime=datetime.now(), logInfo="hi2"))
    items = w.drain()
    assert len(items) == 2
    parsed = [json.loads(x) for x in items]
    assert parsed[0]["type"] == "BUSI_LOG_X"
    assert parsed[1]["logInfo"] == "hi2"


def test_drain_max_items():
    w = ObjectLogWriter.init(
        use_redis=False, queue_name="test", max_queue_size=100,
    )
    for i in range(5):
        w.write_busi(BusiLog(type="X", logInfo=str(i)))
    items = w.drain(max_items=3)
    assert len(items) == 3
    rest = w.drain()
    assert len(rest) == 2


def test_write_request_in_queue():
    w = ObjectLogWriter.init(
        use_redis=False, queue_name="test", max_queue_size=10,
    )
    w.write_request(RequestLog(type="REQUEST_LOG_X", serviceName="/chat"))
    items = w.drain()
    assert len(items) == 1
    parsed = json.loads(items[0])
    assert parsed["type"] == "REQUEST_LOG_X"
    assert parsed["serviceName"] == "/chat"


def test_serialize_datetime_iso():
    w = ObjectLogWriter.init(
        use_redis=False, queue_name="test", max_queue_size=10,
    )
    dt = datetime(2026, 6, 10, 18, 24, 5, 123000)
    w.write_busi(BusiLog(type="X", logTime=dt))
    items = w.drain()
    parsed = json.loads(items[0])
    assert parsed["logTime"] == "2026-06-10 18:24:05.123"


# ---- file 落盘 (mode B) ----

def test_file_fallback_writes_each_line(tmp_log_file: str) -> None:
    w = ObjectLogWriter.init(
        use_redis=False, queue_name="test", max_queue_size=10,
        file_path=tmp_log_file,
    )
    w.write_busi(BusiLog(type="BUSI_LOG_X", logInfo="a"))
    w.write_busi(BusiLog(type="BUSI_LOG_X", logInfo="b"))
    content = Path(tmp_log_file).read_text(encoding="utf-8")
    lines = [line for line in content.splitlines() if line]
    assert len(lines) == 2
    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["logInfo"] == "a"
    assert parsed[1]["logInfo"] == "b"


def test_file_fallback_also_pushes_to_queue(tmp_log_file: str) -> None:
    """file 写跟 in-memory queue 叠加, 防止后续切到 redis 丢日志."""
    w = ObjectLogWriter.init(
        use_redis=False, queue_name="test", max_queue_size=10,
        file_path=tmp_log_file,
    )
    w.write_busi(BusiLog(type="X", logInfo="a"))
    items = w.drain()
    assert len(items) == 1
    assert Path(tmp_log_file).read_text(encoding="utf-8").strip()


def test_file_fallback_skipped_when_redis_enabled(tmp_log_file: str) -> None:
    """Redis 是主 sink, file 不创建也不写 (避免双发)."""
    w = ObjectLogWriter.init(
        use_redis=True, queue_name="test", max_queue_size=10,
        file_path=tmp_log_file,
    )
    w.write_busi(BusiLog(type="X", logInfo="a"))
    assert not Path(tmp_log_file).exists()
    assert len(w.drain()) == 1


def test_file_open_failure_does_not_crash(tmp_path: Path) -> None:
    """不存在的目录: open 失败, 但内存队列仍能 push."""
    bad = str(tmp_path / "no_such_dir" / "x.log")
    w = ObjectLogWriter.init(
        use_redis=False, queue_name="test", max_queue_size=10,
        file_path=bad,
    )
    w.write_busi(BusiLog(type="X", logInfo="a"))
    assert len(w.drain()) == 1
    assert w._file_handle is None


def test_file_close_on_reset(tmp_log_file: str) -> None:
    ObjectLogWriter.init(
        use_redis=False, queue_name="test", max_queue_size=10,
        file_path=tmp_log_file,
    )
    ObjectLogWriter.reset_for_test()
    assert ObjectLogWriter.get_instance() is None


# ---- stdout tee (用 pytest capsys 拦截 sys.stdout) ----

def test_tee_writes_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    w = ObjectLogWriter.init(
        use_redis=False, queue_name="test", max_queue_size=10,
        tee_to_stdout=True,
    )
    w.write_busi(BusiLog(type="BUSI_LOG_X", logInfo="hello"))
    captured = capsys.readouterr()
    assert "[platform-log]" in captured.out
    assert "BUSI_LOG_X" in captured.out
    assert "hello" in captured.out


def test_tee_default_off(capsys: pytest.CaptureFixture[str]) -> None:
    ObjectLogWriter.init(
        use_redis=False, queue_name="test", max_queue_size=10,
    )
    ObjectLogWriter.get_instance().write_busi(
        BusiLog(type="X", logInfo="should_not_appear"),
    )
    captured = capsys.readouterr()
    assert "[platform-log]" not in captured.out


def test_tee_compatible_with_file(
    tmp_log_file: str, capsys: pytest.CaptureFixture[str],
) -> None:
    """file + tee 同时开, 都能写."""
    w = ObjectLogWriter.init(
        use_redis=False, queue_name="test", max_queue_size=10,
        file_path=tmp_log_file,
        tee_to_stdout=True,
    )
    w.write_busi(BusiLog(type="X", logInfo="both"))
    captured = capsys.readouterr()
    assert "[platform-log]" in captured.out
    assert "both" in Path(tmp_log_file).read_text(encoding="utf-8")


def test_tee_compatible_with_redis(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Redis + tee 同时开, Redis 是 sink, tee 走 stdout."""
    w = ObjectLogWriter.init(
        use_redis=True, queue_name="test", max_queue_size=10,
        tee_to_stdout=True,
    )
    w.write_busi(BusiLog(type="X", logInfo="redis_and_tee"))
    captured = capsys.readouterr()
    assert "[platform-log]" in captured.out
    assert len(w.drain()) == 1
