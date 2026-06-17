"""Shared autouse fixture for log platform tests.

pytest 不识别 ``test_*_conftest.py`` 命名 (只认 ``conftest.py``), 而
``tests/conftest.py`` 是 read-only. 唯一可行的方案: 把 autouse fixture
放在每个 log_platform 测试文件里 (copy-paste). 留这个模块让其它测试
可以 ``from tests._log_platform_reset import reset_log_platform`` 手
动调, 但更推荐内联 autouse fixture (避免漏 import).

每个 log_platform 测试文件都内联了同样的 autouse fixture.
"""
from __future__ import annotations

import pytest

from openagent.audit.log import (
    busi_logger as _busi,
    object_log_writer as _olw,
    request_logger as _req,
    seq_no as _seq,
    setup as _setup,
    sys_logger as _sys,
)


@pytest.fixture(autouse=True)
def _reset_log_platform_state():
    """每个测试前/后: 重置所有 module-level 单例, 避免测试间污染."""
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
