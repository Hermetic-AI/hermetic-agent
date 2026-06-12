"""盯住 _configure_logging 的 3 个连环坑:

  1. stdlib root logger 必须装 handler, 否则 ``LoggerFactory()`` 写出的
     日志被静默丢弃;
  2. structlog 的 cache 必须能被 ``reset_defaults() + configure()`` 抹掉,
     否则 ``Settings.__init__`` 里提前触发的 structlog logger 会用
     默认 config, 后续 ``_configure_logging`` 设的 renderer 失效;
  3. stdlib root level 必须按 settings.log_level 设, 默认 WARNING 会
     把 INFO 全过滤掉。

回归点: 之前用户跑 sanic 服务时完全看不到 llm_request 日志, 根因就是
这 3 个, 任何 1 个回归都会让我的 ``llm_payload.log_opencode_request``
调用变成 no-op。
"""
from __future__ import annotations

import io
import logging

import structlog

from openagent.api.app.app import _configure_logging
from openagent.config.settings import Settings
from openagent.providers.llm_payload import build_opencode_payload, log_opencode_request


def _payload() -> dict:
    return build_opencode_payload(
        session_id="sess-test",
        model_id="m",
        provider_id="opencode",
        parts=[{"type": "text", "text": "hi", "id": "p1"}],
        system="sys with MCP_TOKEN: SECRET",
        tools=None,
        timeout=10.0,
        extra_query={"directory": "/d"},
    )


def test_configure_logging_attaches_stdlib_handler() -> None:
    """修复点 1: 必须有 StreamHandler 装在 stdlib root 上."""
    _configure_logging(Settings(log_format="text", log_level="INFO"))
    handlers = logging.getLogger().handlers
    assert handlers, "stdlib root logger 没有任何 handler, 日志会被静默丢弃"
    assert any(isinstance(h, logging.StreamHandler) for h in handlers)


def test_configure_logging_sets_stdlib_level() -> None:
    """修复点 3: stdlib root level 必须按 settings.log_level 设."""
    _configure_logging(Settings(log_format="text", log_level="INFO"))
    assert logging.getLogger().level == logging.INFO
    _configure_logging(Settings(log_format="text", log_level="DEBUG"))
    assert logging.getLogger().level == logging.DEBUG


def test_configure_logging_resets_structlog_cache() -> None:
    """修复点 2: Settings 先 import, structlog 默认 config 被缓存, \
        _configure_logging 之后必须能让 JSONRenderer 生效.

    模拟真实启动顺序: 触发一次 structlog logger (锁默认 config) -> 跑
    _configure_logging(json) -> 实际 log_opencode_request -> 期望 stdout
    抓到的字符串是合法 JSON (说明 JSONRenderer 接管了, 不是默认的
    ConsoleRenderer)。
    """
    # 1) 触发 structlog 缓存默认 config
    logger = structlog.get_logger("openagent.test_cache_poison")
    logger.info("priming", x=1)

    # 2) 跑 _configure_logging(json), 装上我们的 handler + 抹掉 cache
    _configure_logging(Settings(log_format="json", log_level="INFO"))

    # 3) 把 stdlib root 的 StreamHandler 重定向到内存, 抓输出
    buf = io.StringIO()
    for h in logging.getLogger().handlers:
        if isinstance(h, logging.StreamHandler):
            h.stream = buf

    # 4) 实际打 llm_request
    log_opencode_request(_payload())

    line = buf.getvalue().strip()
    assert line, "_configure_logging 后 llm_request 仍没产生任何输出"
    # 必须能被 json.loads 解析, 证明 JSONRenderer 真的接替了
    import json
    obj = json.loads(line)
    assert obj["event"] == "llm_request"
    assert obj["session_id"] == "sess-test"
    assert "***MASKED***" in obj["system"]
    assert "SECRET" not in obj["system"]
