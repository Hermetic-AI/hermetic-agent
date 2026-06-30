"""盯住新增的 console 模式 (Rich 渲染) + 字段过滤行为。

覆盖点:
  * ``log_format=console`` 必须装上 ``RichHandler``, 主题色 + markup 渲染
  * ``log_format=json`` 走 ``JSONRenderer`` (沿用旧测试的回归点)
  * ``_drop_redundant_keys`` 把 ``logger`` / ``timestamp`` 从 event_dict 剔掉
  * ``_compact_event_renderer`` 输出包含 level / event / kv, 可被 Rich
    ``Console.print(markup=True)`` 正确解析 (即不出现未闭合 markup tag)
"""
from __future__ import annotations

import io
import json
import logging

import structlog
from rich.console import Console
from rich.logging import RichHandler

from hermetic_agent.api.http.logging_setup import (
    LOG_THEME,
    _compact_event_renderer,
    _drop_redundant_keys,
    configure_logging,
)
from hermetic_agent.config.settings import Settings


def _capture_stdlib_root() -> io.StringIO:
    """把 stdlib root 的所有 StreamHandler.stream 全部重定向到内存 buf。

    注意: RichHandler 有自己的 ``Console`` 实例, 不会走 ``h.stream``。
    我们同步把 ``RichHandler.console.file`` 改成同一个 buf。
    """
    buf = io.StringIO()
    for h in logging.getLogger().handlers:
        if isinstance(h, RichHandler):
            h.console.file = buf  # type: ignore[attr-defined]
        elif isinstance(h, logging.StreamHandler):
            h.stream = buf
    return buf


def test_console_mode_installs_rich_handler() -> None:
    """``log_format=console`` 必须装 RichHandler, 不是普通 StreamHandler."""
    configure_logging(Settings(log_format="console", log_level="INFO"))
    handlers = logging.getLogger().handlers
    assert any(isinstance(h, RichHandler) for h in handlers), (
        "console 模式期望装 RichHandler, 实际: "
        f"{[type(h).__name__ for h in handlers]}"
    )


def test_json_mode_keeps_stream_handler() -> None:
    """``log_format=json`` 保持普通 StreamHandler, 给 Loki/ELK 抓。"""
    configure_logging(Settings(log_format="json", log_level="INFO"))
    handlers = logging.getLogger().handlers
    assert any(isinstance(h, logging.StreamHandler) and not isinstance(h, RichHandler) for h in handlers), (
        "json 模式期望装普通 StreamHandler, 实际: "
        f"{[type(h).__name__ for h in handlers]}"
    )


def test_console_mode_renders_with_rich_theme() -> None:
    """控制台输出经 Rich 渲染, 含 ANSI 颜色码 (开发期) 或纯 markup 文本 (无 TTY)。"""
    configure_logging(Settings(log_format="console", log_level="INFO"))
    buf = _capture_stdlib_root()
    log = structlog.get_logger("demo.theme")
    log.warning("health_check_failed", error="timeout")

    out = buf.getvalue()
    # Rich 在没有真实 TTY 时输出无 ANSI 字符串, 但 markup tag 必须闭合
    # (即不会有未配对的 [xxx] / [/xxx] 残留)
    open_tags = out.count("[log.")
    close_tags = out.count("[/log.")
    assert open_tags == close_tags, (
        f"markup 标签未闭合: open={open_tags} close={close_tags}, output={out!r}"
    )
    assert "health_check_failed" in out
    assert "WARNING" in out
    # 主题里定义了 log.warning style, 必须存在
    assert "log.warning" in LOG_THEME.styles


def test_console_mode_filters_redundant_keys() -> None:
    """``logger`` 不应出现在输出里, 避免重复. timestamp 保留用于完整时间戳."""
    configure_logging(Settings(log_format="console", log_level="INFO"))
    buf = _capture_stdlib_root()
    log = structlog.get_logger("hermetic_agent.something.deep")
    log.info("ready", count=3)

    out = buf.getvalue()
    # 不应该有形如 [12 chars 的 logger 名] 出现
    assert "hermetic_agent.something.deep" not in out, (
        f"logger 字段应被 _drop_redundant_keys 过滤: {out!r}"
    )
    # 现在输出完整时间戳 (YYYY-MM-DD HH:MM:SS.mmm), 验证格式正确
    assert "2026-" in out or "2025-" in out or "2027-" in out, (
        f"应包含完整日期时间: {out!r}"
    )


def test_json_mode_emits_valid_json() -> None:
    """json 模式回归点: 输出必须是合法 JSON, 业务事件不丢字段。"""
    configure_logging(Settings(log_format="json", log_level="INFO"))
    buf = _capture_stdlib_root()
    log = structlog.get_logger("demo.json")
    log.info("chat_completed", session_id="s1", duration_ms=42)

    line = buf.getvalue().strip()
    obj = json.loads(line)
    assert obj["event"] == "chat_completed"
    assert obj["session_id"] == "s1"
    assert obj["duration_ms"] == 42
    assert obj["level"] == "info"


def test_drop_redundant_keys_removes_logger() -> None:
    """单测过滤器: 直接给 event_dict, 验证剔除 logger (timestamp 保留用于完整时间戳)."""
    out = _drop_redundant_keys(None, "info", {
        "event": "x",
        "level": "info",
        "logger": "hermetic_agent.foo",
        "timestamp": "2026-06-10T10:00:00",
        "keep": 1,
    })
    assert "logger" not in out
    assert "timestamp" in out  # 保留用于完整时间戳输出
    assert out["event"] == "x"
    assert out["keep"] == 1


def test_compact_event_renderer_emits_valid_rich_markup() -> None:
    """单测 renderer: 手工构造 event_dict, 验证 markup 闭合 + 内容齐全。"""
    line = _compact_event_renderer(None, "info", {
        "timestamp": "10:00:00",
        "level": "info",
        "event": "chat_completed",
        "session_id": "s1",
        "duration_ms": 1234,
    })
    # 所有 [tag] 必须有配对的 [/tag]
    import re
    open_tags = re.findall(r"\[([a-zA-Z0-9_.]+)\]", line)
    close_tags = re.findall(r"\[/([a-zA-Z0-9_.]+)\]", line)
    assert sorted(open_tags) == sorted(close_tags), (
        f"markup 不配对: open={open_tags} close={close_tags}\n{line}"
    )
    assert "chat_completed" in line
    assert "session_id" in line
    assert "s1" in line


def test_console_mode_renders_via_rich_console() -> None:
    """renderer 输出的 markup 字符串可以原样塞进 ``Console.print``, 不抛异常。"""
    console = Console(file=io.StringIO(), theme=LOG_THEME, force_terminal=False)
    rendered = _compact_event_renderer(None, "info", {
        "timestamp": "10:00:00",
        "level": "info",
        "event": "ok",
        "x": 1,
    })
    console.print(rendered, markup=True)  # 不抛 = 全部 tag 都被识别
    # 还要保证色名都在 theme 里
    out_str = console.file.getvalue()  # type: ignore[attr-defined]
    assert "ok" in out_str


def test_level_filtering_respected() -> None:
    """INFO 级: DEBUG 调用不输出。"""
    configure_logging(Settings(log_format="json", log_level="INFO"))
    buf = _capture_stdlib_root()
    log = structlog.get_logger("demo.level")
    log.debug("should_not_appear", x=1)
    log.info("should_appear", x=2)
    assert "should_not_appear" not in buf.getvalue()
    assert "should_appear" in buf.getvalue()
