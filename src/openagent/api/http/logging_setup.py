"""structlog + Rich 日志配置。

设计目标（按设计文档 §10 错误码 + AGENTS.md §6 错误处理约束延伸）：

* console 模式 (开发): Rich ConsoleRenderer, 按 level 自动配色,
  字段自动对齐, 时间戳精确到秒, 减少冗余键值对。
* json 模式 (生产): JSONRenderer (ensure_ascii=False), 直接喂 ELK / Loki。
* 双模式切换只由 ``Settings.log_format`` 控制, 不需要改业务代码。
* 启动期心跳/状态行 (application_startup / *_ready / mcp_token_extracted)
  在调用方降到 ``logger.debug``; INFO 留给真正影响业务的请求/失败事件。
"""
from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from rich.console import Console
from rich.theme import Theme
from structlog.types import EventDict, Processor

from openagent.config.settings import Settings

# Rich 主题: 只在 console 模式生效, 给 level / event / key 配色
LOG_THEME = Theme(
    {
        "log.debug": "dim cyan",
        "log.info": "bold green",
        "log.warning": "bold yellow",
        "log.error": "bold red",
        "log.critical": "bold white on red",
        "log.event": "bold cyan",
        "log.key": "dim magenta",
        "log.number": "cyan",
        "log.string": "green",
        "log.bool_true": "bold green",
        "log.bool_false": "bold red",
        "log.path": "blue",
        "log.dim": "dim",
    }
)


def _drop_redundant_keys(_: Any, __: str, event_dict: EventDict) -> EventDict:
    """把始终不变 / 噪音大的字段从渲染里剔掉。

    * ``logger``: module 名, 重复出现在每行; 调试时按需开
    * ``timestamp`` 由 ConsoleRenderer 自己用更可读的格式重画, 原本的 ISO
      字符串如果留着会和下面的 ``[HH:MM:SS]`` 重复
    """
    event_dict.pop("logger", None)
    event_dict.pop("timestamp", None)
    return event_dict


def _compact_event_renderer(_: Any, __: str, event_dict: EventDict) -> str:
    """Rich 友好的最终格式化: ``[HH:MM:SS] LEVEL  event  k=v k=v``。

    输出是单行 markup 字符串, 由 Rich 的 ``Console.print(markup=True)``
    或 ``RichHandler`` 解释。颜色全部用 ``LOG_THEME`` 里定义的 style。
    """
    ts = event_dict.get("timestamp", "")
    level = str(event_dict.get("level", "info"))

    # 关键字段先 pop, 剩下都是 kv
    kv_pairs: list[tuple[str, Any]] = []
    for k, v in event_dict.items():
        if k in ("timestamp", "level", "event"):
            continue
        kv_pairs.append((k, v))

    parts: list[str] = []
    if ts:
        parts.append(f"[log.dim]{ts}[/log.dim]")
    parts.append(f"[log.{level}]{level.upper():<8}[/log.{level}]")
    parts.append(f"[log.event]{event_dict.get('event', '')}[/log.event]")

    for k, v in kv_pairs:
        if isinstance(v, bool):
            tag = f"log.bool_{str(v).lower()}"
        elif isinstance(v, (int, float)):
            tag = "log.number"
        elif isinstance(v, str) and ("/" in v or "\\" in v):
            tag = "log.path"
        else:
            tag = "log.string"
        parts.append(f"[log.key]{k}[/log.key]=[{tag}]{v!r}[/{tag}]")

    return " ".join(parts)


def build_console_renderer() -> Processor:
    """返回一个 structlog 处理器: 输出 Rich 风格单行彩色日志。"""
    return _compact_event_renderer


def configure_logging(settings: Settings) -> None:
    """根据 settings 配置 structlog + stdlib root logger。

    三个连环坑 (沿用旧 _configure_logging 的修复):

    1. ``LoggerFactory()`` 把日志转给 stdlib logger, 但 stdlib root 默认
       无 handler → 日志被静默丢弃。这里强制装一个 ``StreamHandler``。
    2. ``Settings.__init__`` 会在 ``get_settings()`` 时就触发 structlog
       logger, 比本函数跑得还早; 一旦 ``cache_logger_on_first_use=True``,
       后续 ``structlog.configure`` 改的处理器全失效 → 先
       ``structlog.reset_defaults()`` 抹掉旧 cache。
    3. stdlib root 默认 level=WARNING, INFO 全被过滤 → 按 settings 设。
    """
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)

    if settings.log_format == "console":
        from rich.logging import RichHandler

        # 关闭 RichHandler 自带的 time/level/path/markup, 因为我们用
        # _compact_event_renderer 直接生成完整 Rich markup 字符串,
        # 让 RichHandler 当成普通 message 透传给 Console.print 渲染。
        handler: logging.Handler = RichHandler(
            console=Console(theme=LOG_THEME, stderr=False),
            show_path=False,
            show_time=False,
            show_level=False,
            rich_tracebacks=True,
            tracebacks_show_locals=False,
            markup=True,
        )
    else:
        handler = logging.StreamHandler(sys.stdout)

    handler.setLevel(log_level)
    if settings.log_format == "console":
        # RichHandler 自己渲染; 给个空 Formatter 防止 %(message)s 重复
        handler.setFormatter(logging.Formatter("%(message)s"))
    else:
        handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(handler)
    root.setLevel(log_level)

    structlog.reset_defaults()
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="%H:%M:%S", utc=False),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        _drop_redundant_keys,
    ]
    if settings.log_format == "json":
        renderer: Processor = structlog.processors.JSONRenderer(ensure_ascii=False)
    else:
        renderer = build_console_renderer()

    # 平台日志: 把 structlog event 自动转 BusiLog 推到 ObjectLogWriter.
    # 必须在 renderer 之前 (renderer 把 event_dict 序列化成 str, 后面就拿不到字段了).
    # IS_LOG=False 时 (中间件没开) 是 no-op, 不影响主流程.
    # 懒加载避免循环 import (structlog_processor 又依赖 busi_logger).
    from openagent.audit.log.structlog_processor import platform_log_processor

    structlog.configure(
        processors=[
            *shared_processors,
            platform_log_processor,
            renderer,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
