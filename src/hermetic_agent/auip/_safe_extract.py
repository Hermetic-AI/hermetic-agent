"""auip/_safe_extract.py — 通用字段安全提取工具.

集中 _first_text / _first_number / _date_part 这一类**纯数据变换**工具,
供业务 SKILL CardRenderer / MessageRewriter 复用. 跟业务无关, 仅做防御性
字段提取 + 字符串/数字规整.

设计原则:
- 纯函数, 无状态, 无 IO, 易于单测
- 命名以 _ 开头表示"工具函数", 业务 SKILL 可直接 import
- 不假设 input 来自 MCP / opencode / 任何具体协议

典型用法 (SKILL 侧):
    from hermetic_agent.auip._safe_extract import first_text, first_number, date_part

    flight_no = first_text(raw.get("flightNo"), raw.get("flightNumber"))
    price = first_number(raw.get("lowestPrice"), raw.get("price"), default=0.0)
    dep = date_part(raw.get("departureTime"))  # "2026-06-06 08:00" -> "2026-06-06"
"""

from __future__ import annotations

from typing import Any

INVALID_NUMBER_SENTINEL = 0.0
"""``first_number`` 解析失败时的兜底值. 跟 ``parse_minutes`` 的 sentinel 思路一致."""


def first_text(*values: Any) -> str:
    """从若干候选值中取第一个非空字符串.

    支持:
    - None 跳过
    - dict 自动取 .name / .companyName / .text
    - 数字 / bool 强制转为 str
    - 空白字符串视为空

    Returns:
        第一个非空字符串, 全部为空时返空串.
    """
    for value in values:
        if value is None:
            continue
        if isinstance(value, dict):
            value = value.get("name") or value.get("companyName") or value.get("text")
        text = str(value).strip()
        if text:
            return text
    return ""


def first_number(*values: Any, default: float = INVALID_NUMBER_SENTINEL) -> float:
    """从若干候选值中取第一个可解析为 float 的值.

    支持:
    - None / 空字符串跳过
    - 数字直接返回
    - 字符串尝试 float(...)
    - 全部失败返 ``default`` (默认 0.0)
    """
    for value in values:
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return default


def date_part(value: Any) -> str:
    """从 ``"2026-06-06 08:00"`` 形式取日期部分 ``"2026-06-06"``.

    空值返空串. 找不到空格分隔时, 返原始 text (假设就是纯日期).
    """
    text = first_text(value)
    return text.split(" ")[0] if text else ""


__all__ = [
    "INVALID_NUMBER_SENTINEL",
    "first_text",
    "first_number",
    "date_part",
]
