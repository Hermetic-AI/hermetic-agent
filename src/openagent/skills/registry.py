"""Skill Registry - 技能注册中心

管理所有可用的技能定义，支持从文件系统加载和动态注册。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import structlog
import yaml

logger = structlog.get_logger(__name__)

DEFAULT_TEMPLATE = """## Skill: {name}

{description}

### Version
{version}

### Triggers
{triggers}

### Input Schema
```json
{input_schema}
```

### Output Schema
```json
{output_schema}
```

### MCP Tools
{mcp_tools}

### Prompt Template
{prompt_template}
"""


@dataclass
class Skill:
    """技能定义。

    一个 Skill 描述了 LLM 在特定场景下可复用的提示词模板与相关元数据，
    包括触发词、输入/输出 JSON Schema、依赖的 MCP 工具等。

    Attributes:
        name: 技能名称，唯一标识。
        description: 技能描述。
        version: 技能版本。
        triggers: 触发关键词列表。
        input_schema: 输入 JSON Schema。
        output_schema: 输出 JSON Schema。
        prompt_template: 提示词模板。
        mcp_tools: MCP 工具列表。
        source: 技能来源（文件路径或配置名）。
    """

    name: str
    description: str = ""
    version: str = "1.0.0"
    triggers: list[str] = field(default_factory=list)
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    prompt_template: str = ""
    mcp_tools: list[str] = field(default_factory=list)
    source: str = ""


class SkillRegistry:
    """技能注册中心。

    管理所有可用技能，支持从文件系统加载和动态注册。提供按名称查询、
    按触发词匹配以及把多个技能拼装进系统提示词等能力。

    Usage:
        registry = SkillRegistry()

        # 从路径加载技能
        registry.load_from_paths("skills/", "plugins/")

        # 手动注册技能
        registry.register(Skill(name="my_skill", ...))

        # 获取技能
        skill = registry.get("my_skill")

        # 列出所有技能
        all_skills = registry.list_all()

        # 根据触发词匹配技能
        matched = registry.match_by_trigger("帮我写代码")
    """

    def __init__(self) -> None:
        """初始化一个空的技能注册表。"""
        self._skills: dict[str, Skill] = {}

    def load_from_paths(self, *paths: str) -> list[Skill]:
        """从指定路径加载所有 SKILL.md 文件。

        支持传入目录（递归查找 ``SKILL.md``）或单个 ``SKILL.md`` 文件。

        Args:
            paths: 目录或文件路径列表，支持相对路径和绝对路径。

        Returns:
            成功加载的 Skill 列表；解析失败的条目会被跳过并打 warning 日志。
        """
        loaded = []
        for path_str in paths:
            path = Path(path_str)
            if not path.exists():
                logger.warning("skill_path_not_found", path=str(path))
                continue

            if path.is_file():
                if path.name == "SKILL.md":
                    skill = self._parse_skill_md(path)
                    if skill:
                        self.register(skill)
                        loaded.append(skill)
            else:
                for skill_path in path.rglob("SKILL.md"):
                    skill = self._parse_skill_md(skill_path)
                    if skill:
                        self.register(skill)
                        loaded.append(skill)

        logger.info("skills_loaded", count=len(loaded), paths=list(paths))
        return loaded

    def _parse_skill_md(self, path: Path) -> Optional[Skill]:
        """解析单个 SKILL.md 文件（实际逻辑委托给 frontmatter 模块）。"""
        from openagent.skills.frontmatter import parse_skill_md

        return parse_skill_md(path)

    def register(self, skill: Skill) -> None:
        """注册一个技能实例。

        Args:
            skill: 待注册的技能实例。

        Raises:
            ValueError: 技能名称已存在（实现当前静默跳过并打 warning 以兼容热加载）。
        """
        if skill.name in self._skills:
            logger.warning("skill_already_registered", name=skill.name)
            return

        self._skills[skill.name] = skill
        logger.debug("skill_registered", name=skill.name, source=skill.source)

    def register_from_config(self, config: dict[str, Any]) -> Skill:
        """从配置字典构造并注册一个 Skill。

        Args:
            config: 技能配置字典，键对应 ``Skill`` 字段。

        Returns:
            注册成功的 Skill 实例。
        """
        skill = Skill(
            name=str(config["name"]),
            description=str(config.get("description", "")),
            version=str(config.get("version", "1.0.0")),
            triggers=list(config.get("triggers", [])),
            input_schema=config.get("input_schema", {}),
            output_schema=config.get("output_schema", {}),
            prompt_template=str(config.get("prompt_template", "")),
            mcp_tools=list(config.get("mcp_tools", [])),
            source=str(config.get("source", "config")),
        )
        self.register(skill)
        return skill

    def get(self, name: str) -> Optional[Skill]:
        """按名称获取技能。

        Args:
            name: 技能名称。

        Returns:
            技能实例，不存在返回 None。
        """
        return self._skills.get(name)

    def list_all(self) -> list[Skill]:
        """返回当前注册表内全部技能的列表（拷贝）。"""
        return list(self._skills.values())

    def inject(self, name: str, **kwargs: Any) -> Optional[Skill]:
        """复制一个技能并覆盖指定字段。

        Args:
            name: 要复制的技能名称。
            **kwargs: 要覆盖的字段及其新值。

        Returns:
            新的技能实例，原始技能不存在返回 None。
        """
        original = self.get(name)
        if not original:
            return None

        import copy

        new_skill = copy.deepcopy(original)
        for key, value in kwargs.items():
            if hasattr(new_skill, key):
                setattr(new_skill, key, value)

        return new_skill

    def build_system_prompt_with_skills(
        self,
        system_prompt: str,
        skill_names: list[str],
    ) -> tuple[str, list[str]]:
        """把指定技能的 prompt_template 拼到 system_prompt 之后。

        Args:
            system_prompt: 原始系统提示词。
            skill_names: 要注入的 skill 名称列表。

        Returns:
            ``(拼接后的 system_prompt, 未找到的 skill 名称列表)``。找不到的
            skill 不会抛异常，由调用方决定如何处理（记日志 / 报错）。
        """
        parts: list[str] = []
        if system_prompt:
            parts.append(system_prompt)

        injected: list[str] = []
        missing: list[str] = []
        for name in skill_names:
            skill = self.get(name)
            if skill is None:
                missing.append(name)
                continue
            if skill.prompt_template:
                parts.append(skill.prompt_template)
            injected.append(name)

        if missing:
            logger.warning(
                "skills_not_found",
                missing=missing,
                available=list(self._skills.keys()),
            )
        if injected:
            logger.info(
                "skills_injected_into_prompt",
                injected=injected,
            )

        return "\n\n".join(parts), missing

    def metadata_list(
        self,
        skill_names: list[str] | None = None,
        *,
        missing_label: str = "(not in registry)",
    ) -> str:
        """渲染 ``(name, description)`` 列表 — Anthropic Skills 协议 L1 (metadata-only).

        用法: 在 system prompt 顶部放一段小广告, 让 LLM 知道"哪些 skill 可用 +
        何时该用". LLM 看到相关关键词后, 主动调 ``read_skill`` 加载完整内容.

        Args:
            skill_names: 要列出的 skill 名称列表. None = 全注册表.
            missing_label: 列表中找不到的 skill 名称渲染为什么.

        Returns:
            多行字符串, 形如::

                [Available skills (call read_skill to load full content on demand)]
                - flight-query: 通过 MCP 端点查询国内航班...
                - flight-booking: 机票预订状态机...
                - nonexistent: (not in registry)
        """
        # None = 默认列出全部注册表; [] = 显式空, 啥也不列 (caller 区分用).
        if skill_names is None:
            names = [s.name for s in self.list_all()]
        else:
            names = list(skill_names)
        if not names:
            return ""
        lines = [
            "[Available skills "
            "(call read_skill to load full SKILL.md on demand)]"
        ]
        for name in names:
            skill = self._skills.get(name)
            if skill is None:
                lines.append(f"- {name}: {missing_label}")
                continue
            desc = skill.description or "(no description)"
            lines.append(f"- {skill.name} (v{skill.version}): {desc}")
        return "\n".join(lines)

    def match_by_trigger(self, text: str) -> list[Skill]:
        """根据触发词匹配技能。

        使用简单的关键词匹配，``text`` 中出现触发词即视为匹配。

        Args:
            text: 待匹配的文本。

        Returns:
            匹配到的技能列表，按命中触发词数量降序排列。
        """
        matched: list[tuple[Skill, int]] = []

        for skill in self._skills.values():
            if not skill.triggers:
                continue

            count = sum(1 for trigger in skill.triggers if trigger in text)
            if count > 0:
                matched.append((skill, count))

        matched.sort(key=lambda x: x[1], reverse=True)
        return [s for s, _ in matched]
