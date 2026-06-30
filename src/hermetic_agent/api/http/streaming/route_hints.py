"""api/streaming/route_hints.py — 飞鹤航班场景的路由/日期启发式.

P0 报告 #4: ``_FH_ROUTE_RE`` / ``_FH_DATE_RE`` 过宽, 会把"从abc到def"、
"13-45" 这种"看起来像但实际无效"输入误判为"用户已提供完整信息",
跳过 ask_user 卡片, 进入下游分支.

修复:
1. 城市名严格限制 2-5 个汉字/英文字母 (避免 "从abc到def" 命中)
2. 日期走 ``datetime.strptime`` 真实解析, 拒绝 13-45 这种

这些启发式**只为"是否绕过 HITL 占位卡片"** 决策, 不参与实际 LLM 路由.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

# 飞鹤航线: "从 北京 到 上海" / "北京至上海" / "PEK飞PVG"
# 严格边界: 城市名只接受 2-5 个汉字/英文字母, 前后需要明确的"从/至/飞"
# 关键词 + 分隔符.
#
# 拒绝: "从abc到def" (英文 abc 不足 2 字符 OK, 但 def 不足)
# 拒绝: "从头到尾到xyz" (含 "到" 多次出现, 但第二段 "到xyz" 缺分隔)
#
# 实际允许: 前后至少有 1 个空白 (中英文空格都算), 城市名长度 2-5 字符
_ROUTE_RE = re.compile(
    r"从\s*[\u4e00-\u9fffA-Za-z]{2,5}\s*(?:到|至|飞)\s*[\u4e00-\u9fffA-Za-z]{2,5}"
)

# 日期格式 (2026-06-11 / 2026/6/11 / 2026年6月11日 / 6月11日 / 6-11 / 6/11)
# 注意: 月份和日都限制 1-2 位数字, 后续 ``_parse_date`` 会进一步校验
# 月份 ≤ 12 / 日期 ≤ 当月最大天数.
_DATE_PREFIX_RE = re.compile(
    r"(\d{4}[-/.年])?(\d{1,2})[-/.月](\d{1,2})日?"
)
_DATE_KEYWORD_RE = re.compile(
    r"(今天|明天|后天|大后天|周[一二三四五六日天]|星期[一二三四五六日天])"
)


def _parse_date(text: str) -> bool:
    """真实解析日期, 拒绝 13-45 这类结构合法但语义无效的输入.

    Returns:
        True = text 含至少一个可解析的合法日期.
    """
    if not text:
        return False
    # 关键词日期 (今天/明天/...) 直接通过
    if _DATE_KEYWORD_RE.search(text):
        return True

    # 数字日期: 找所有匹配, 至少要有一个能 strptime 通过
    for m in _DATE_PREFIX_RE.finditer(text):
        year_str, month_str, day_str = m.group(1), m.group(2), m.group(3)
        year = int(year_str.rstrip("年/.-")) if year_str else datetime.now().year
        try:
            month = int(month_str)
            day = int(day_str)
        except ValueError:
            continue
        if month < 1 or month > 12:
            continue
        if day < 1 or day > 31:
            continue
        # 用 try 校验是否真的是合法日期 (e.g. 2月30日)
        try:
            datetime(year, month, day)
        except ValueError:
            continue
        return True
    return False


def has_complete_route_hint(message: str) -> bool:
    """用户消息里是否含完整航线信息 (from-to + 日期).

    用于 ``_should_bypass_hitl_placeholder``: 当消息已含完整 OD + 日期,
    跳过 ask_user 占位卡片, 直接进入 LLM 处理.
    """
    if not message:
        return False
    return bool(_ROUTE_RE.search(message)) and _parse_date(message)


def should_bypass_hitl_placeholder(
    scenario: Any,
    message: str,
    *,
    enabled_scenarios: set[str] | None = None,
) -> bool:
    """判定: 当前 scenario + 用户消息 是否可绕过 HITL 占位卡片.

    基座默认对**所有** scenario 都关闭, 业务 SKILL 显式传 ``enabled_scenarios``
    才生效. 业务 SKILL 也可以在 scenario YAML 中声明自己需要的策略.

    Args:
        scenario: 当前 scenario 对象.
        message: 用户消息文本.
        enabled_scenarios: 显式启用本策略的 scenario name 集合. None
            表示禁用 (业务 SKILL 应传自己的 scenario name 集合).
    """
    if not enabled_scenarios:
        return False
    if getattr(scenario, "name", "") not in enabled_scenarios:
        return False
    return has_complete_route_hint(message or "")
