"""auip/_duration.py — 航班时长解析共享工具.

历史: flight_card.py 的 ``_parse_minutes`` 与 flight_query_presenter.py 的
``_parse_duration`` 各自实现一套"2h20m" / "1h55m" → 数字 分钟 的解析,
互不复用. P1 重构抽出这个共享解析器, 保留两份 API 的输入/输出语义:

  - ``parse_minutes`` (flight_card 语义): "2h20m" / "1h55m" / "150m" / 数字 → int
  - ``parse_duration_text`` (presenter 语义): "2h20m" → 140 (兼容 "h" / "小时" / "m" / "分钟")
"""
from __future__ import annotations

import re

# 数字+单位 (h/小时/m/分钟/分) 的捕获正则.
# group(1) = 小时数, group(2) = 分钟数.
_HOURS_RE = re.compile(r"(\d+)\s*(?:h|小时)", re.IGNORECASE)
_MINUTES_RE = re.compile(r"(\d+)\s*(?:m|分钟|分)", re.IGNORECASE)

# 解析失败时的兜底值 (在排序中推到最末).
INVALID_MINUTES_SENTINEL = 9999


def parse_minutes(duration: str | None, *, invalid_sentinel: int = INVALID_MINUTES_SENTINEL) -> int:
    """把时长字符串解析为分钟数 (flight_card 语义).

    支持格式:
      - "2h20m"   → 140
      - "1h55m"   → 115
      - "150m"    → 150
      - "3h"      → 180
      - "5小时30分" / "5小时30分钟" → 330
      - 纯数字 "150" → 150

    Args:
        duration: 时长字符串; 空白或 None 返 ``invalid_sentinel``.
        invalid_sentinel: 解析失败时返回的兜底值. flight_card 排序场景
            用 9999 让无效航班排到末尾; flight_query_presenter 用 0 表示
            "我没法解析, 让上层走 0 路径".

    Returns:
        分钟数; 解析失败返 ``invalid_sentinel``.
    """
    if not duration:
        return invalid_sentinel
    text = str(duration).strip()
    h = _HOURS_RE.search(text)
    m = _MINUTES_RE.search(text)
    hours = int(h.group(1)) if h else 0
    minutes = int(m.group(1)) if m else 0
    if h or m:
        return hours * 60 + minutes
    if text.isdigit():
        return int(text)
    return invalid_sentinel


def parse_duration_text(duration: str | None) -> int:
    """把时长字符串解析为分钟数 (flight_query_presenter 语义).

    历史 ``flight_query_presenter._parse_duration`` 对无效输入返 0
    (让上层走"没法排序但有数据"的路径). 这里保留旧行为, 不传
    ``invalid_sentinel`` 时等价于 ``parse_minutes(..., invalid_sentinel=0)``.
    """
    return parse_minutes(duration, invalid_sentinel=0)


def format_duration_label(duration: str | None) -> str:
    """flight_query_presenter 使用的"原样返回"逻辑.

    有些上游数据已经传了"2h20m"形式, 直接返回; 空 / None / 解析失败
    时回退空串. 跟 ``parse_minutes`` 互补, 一个解数字, 一个保原文.
    """
    if not duration:
        return ""
    text = str(duration).strip()
    return text
