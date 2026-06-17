"""test_log_platform_log_compress — 阈值 + 压缩往返."""
from __future__ import annotations

import pytest

from openagent.audit.log import (
    busi_logger as _busi, object_log_writer as _olw, request_logger as _req,
    seq_no as _seq, setup as _setup, sys_logger as _sys,
)
from openagent.audit.log.log_compress import (
    THRESHOLD_BYTES,
    maybe_compress,
    maybe_decompress,
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


def test_under_threshold_passthrough():
    text = "hello world"
    out, size, compress = maybe_compress(text)
    assert out == text
    assert size == len(text.encode("utf-8"))
    assert compress is False


def test_over_threshold_compresses():
    text = "x" * (THRESHOLD_BYTES + 100)
    out, size, compress = maybe_compress(text)
    assert compress is True
    assert size == len(text.encode("utf-8"))
    assert out is not None
    assert len(out) < len(text)
    assert maybe_decompress(out, compress) == text


def test_none_input():
    out, size, compress = maybe_compress(None)
    assert out is None
    assert size == 0
    assert compress is False


def test_decompress_passthrough_when_not_compressed():
    assert maybe_decompress("plain", False) == "plain"
    assert maybe_decompress(None, False) is None


def test_roundtrip_chinese():
    text = "你好世界" * (THRESHOLD_BYTES // 12 + 100)
    out, size, compress = maybe_compress(text)
    assert compress is True
    assert size == len(text.encode("utf-8"))
    assert maybe_decompress(out, compress) == text
