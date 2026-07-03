"""SKILL.md frontmatter parser — extracted from skills/registry.py.

The parser is self-contained: a YAML frontmatter block (delimited by `---`)
followed by a markdown body. On any parse error, returns None and logs a
warning — callers are expected to skip the file rather than abort the whole
load.
"""

from __future__ import annotations

import re
from pathlib import Path

import structlog
import yaml

from hermetic_agent.skills.registry import Skill

logger = structlog.get_logger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def parse_skill_md(path: Path) -> Skill | None:
    """解析单个 SKILL.md 文件。

    文件结构：开头是 YAML frontmatter 块（用 ``---`` 包围），之后是 markdown
    正文，正文会作为 ``prompt_template`` 存入 Skill。

    Args:
        path: SKILL.md 文件路径。

    Returns:
        成功解析返回 Skill 实例；读取失败、缺少 frontmatter、YAML 解析错误或
        frontmatter 为空时返回 None，并打对应 warning/error 日志。
    """
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as e:
        logger.error("skill_read_error", path=str(path), error=str(e))
        return None

    fm_match = _FRONTMATTER_RE.match(content)
    if not fm_match:
        logger.warning("skill_no_frontmatter", path=str(path))
        return None
    fm_text, body = fm_match.groups()

    try:
        fm_data = yaml.safe_load(fm_text)
    except yaml.YAMLError as e:
        logger.error("skill_yaml_error", path=str(path), error=str(e))
        return None
    except Exception as e:
        logger.error("skill_parse_error", path=str(path), error=str(e))
        return None

    if not fm_data:
        logger.warning("skill_empty_frontmatter", path=str(path))
        return None

    return Skill(
        name=str(fm_data.get("name", path.stem)),
        description=str(fm_data.get("description", "")),
        version=str(fm_data.get("version", "1.0.0")),
        triggers=list(fm_data.get("triggers", [])),
        input_schema=fm_data.get("input_schema", {}),
        output_schema=fm_data.get("output_schema", {}),
        prompt_template=body.strip(),
        mcp_tools=list(fm_data.get("mcp_tools", [])),
        source=str(path),
    )
