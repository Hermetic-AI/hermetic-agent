"""auip/skill_compiler.py — 简化版 SKILL.md → manifest dict.

设计文档 §3 L3 (D5 整合). 设计目标: 把 prose 形式的 ``SKILL.md``
(``docs/skill/book-flight-skill.md``) 编译成结构化 dict, 供
``SkillManifest.from_dict`` 二次精炼.

简化策略 (P5 范围, 不做完整 prose AST 解析):
1. 提取 YAML frontmatter (name / version / description)
2. 扫描 §2.1 状态一览 markdown 表格, 抽取 ``| S0X | name | ... |``
3. 扫描 §3.1 工具白名单 (粗略, 取形如 ``- tool_name`` 的列表项)
4. 其他 prose 章节作为 ``prompt_template`` 整体返回, 不解析.

返回的 dict 兼容 ``SkillManifest.from_dict`` (字段名一致).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

# markdown 表格行: 第一个匹配 S\d+/F\d+ 的 cell 视为 state id,
# 紧随其后的非空 cell 视为 name. 用 split('|') 灵活处理列数.
_STATE_ID_RE = re.compile(r"^S\d+$|^F\d+$")
# markdown 列表行, 形如: - tool_name  /  * tool_name
_TOOL_ITEM_RE = re.compile(r"^[\s]*[-*]\s*`?([a-zA-Z_][a-zA-Z0-9_]*)`?")

_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL
)

# §2.1 状态表的 "锚点" — 任意标题包含 "状态一览" / "State ID" / "State" 都触发
_STATE_SECTION_ANCHORS = ("状态一览", "State ID", "State ", "States")
# §3.1 工具白名单的 "锚点"
_TOOL_SECTION_ANCHORS = ("MCP 工具", "工具白名单", "可用工具", "Tools")


def compile_skill_md(md_path: str | Path) -> dict[str, Any]:
    """把 prose SKILL.md 编译成 machine-readable dict.

    Args:
        md_path: SKILL.md 文件路径.

    Returns:
        包含 ``name`` / ``version`` / ``description`` / ``states`` /
        ``initial_state`` / ``allowed_tools`` / ``prompt_template`` 的 dict.

    Note:
        解析失败时 (无 frontmatter / 文件不存在) 仍返回合法 dict, 字段
        退化为文件名 / 默认值 — 不抛异常, 由调用方决定是否进一步校验.
    """
    p = Path(md_path)
    content = p.read_text(encoding="utf-8") if p.exists() else ""

    fm, body = _split_frontmatter(content)
    name = (fm.get("name") if isinstance(fm, dict) else None) or p.stem
    version = (fm.get("version") if isinstance(fm, dict) else None) or "1.0.0"
    description = (fm.get("description") if isinstance(fm, dict) else None) or ""

    states = _parse_state_table(body)
    allowed_tools = _parse_tool_whitelist(body)

    return {
        "name": str(name),
        "version": str(version),
        "description": str(description),
        "states": states,
        "initial_state": states[0]["id"] if states else "S01",
        "allowed_tools": allowed_tools,
        "prompt_template": body.strip(),
    }


def _split_frontmatter(content: str) -> tuple[dict[str, Any] | None, str]:
    """提取 YAML frontmatter, 剩余作为 body."""
    if not content:
        return None, ""
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return None, content
    fm_text, body = m.groups()
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        return None, body
    if not isinstance(fm, dict):
        return None, body
    return fm, body


def _parse_state_table(body: str) -> list[dict[str, str]]:
    """扫描 §2.1 状态一览 markdown 表格.

    规则: 找到第一个含锚点的标题行, 在其后扫描 ``|`` 起始的行,
    提取首列符合 ``^S\\d+$|^F\\d+$`` 的状态 id + 第二列 name.
    """
    if not body:
        return []
    lines = body.split("\n")
    in_state_section = False
    states: list[dict[str, str]] = []
    seen: set[str] = set()
    for line in lines:
        if not in_state_section:
            if any(anchor in line for anchor in _STATE_SECTION_ANCHORS):
                in_state_section = True
            continue
        # 已脱离表格区域
        if line.strip() and not line.startswith("|"):
            if states:
                # 允许表格后继续写 prose, 但状态表已收齐, break
                break
            continue
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if len(cells) < 2:
            continue
        # 找第一个匹配 S\d+/F\d+ 的 cell 作 state id
        sid_idx = -1
        for i, c in enumerate(cells):
            if _STATE_ID_RE.match(c):
                sid_idx = i
                break
        if sid_idx < 0 or sid_idx + 1 >= len(cells):
            continue
        sid = cells[sid_idx]
        if sid in seen:
            continue
        seen.add(sid)
        # name = sid 后的第一个非空 cell
        name = cells[sid_idx + 1]
        states.append({"id": sid, "name": name})
    return states


def _parse_tool_whitelist(body: str) -> list[str]:
    """扫描 §3.1 工具白名单, 返回有序去重的工具名列表.

    锚点匹配 ``### ... 工具白名单 / 可用工具 / MCP 工具 / Tools`` 这类
    子节标题; 遇到下一节 ``##`` 级别标题即停.
    """
    if not body:
        return []
    lines = body.split("\n")
    in_tool_section = False
    tools: list[str] = []
    seen: set[str] = set()
    for line in lines:
        if not in_tool_section:
            # 仅匹配 ### 子节 (避免把上级章节标题当成锚点)
            if not line.startswith("###"):
                continue
            if any(anchor in line for anchor in _TOOL_SECTION_ANCHORS):
                in_tool_section = True
            continue
        # 下一节: ## 章节或更高级别
        if line.startswith("## "):
            break
        m = _TOOL_ITEM_RE.match(line)
        if not m:
            continue
        name = m.group(1)
        if name in seen:
            continue
        seen.add(name)
        tools.append(name)
    return tools


__all__ = ["compile_skill_md"]
