"""Scenario Loader — YAML 加载 + 占位符解析 + 资源校验.

公开 API:
- resolve_placeholders(value, ctx): 递归替换 ${KEY}, 找不到保留原样
- load_scenario(path, ctx): 4 步加载: 读 YAML → 解析占位符 → 校验 schema → 校验资源
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import structlog
import yaml
from pydantic import ValidationError

from openagent.scenarios.config import ScenarioConfig
from openagent.scenarios.errors import (
    ScenarioLoadError,
    ScenarioResourceError,
)

logger = structlog.get_logger(__name__)

_PLACEHOLDER_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")
# 占位符可后接路径片段 (/foo/bar), 整个表达式都需要加引号
_UNQUOTED_PLACEHOLDER_RE = re.compile(
    r'(?<!")\$\{([A-Z_][A-Z0-9_]*)\}(?:[/A-Za-z0-9._-]*)?(?!")'
)


def _quote_placeholders(text: str) -> str:
    """把未加引号的 ${KEY}[/suffix] 用双引号包起来.

    YAML 1.1 在 flow context (方括号) 中不允许未加引号的 `${...}`,
    会抛 ParserError. 这里做一次预处理, 解决兼容问题.
    占位符后常跟路径片段 (/docs, /skills/foo), 一并包到引号内.
    """

    def _wrap(m: re.Match[str]) -> str:
        return f'"{m.group(0)}"'

    return _UNQUOTED_PLACEHOLDER_RE.sub(_wrap, text)


class _StrictYAMLLoader(yaml.SafeLoader):
    """YAML 1.1 兼容加载器: 关闭 off/on/yes/no → bool 的隐式解析.

    PyYAML 默认按 YAML 1.1 解析, 会把 `network: off` 转成 `False`,
    这与 Scenario YAML 的语义 (字符串字面量) 冲突.
    """


# 移除 off/on/yes/no 的隐式 bool 解析; 移除 null 的隐式解析 (n/N 开头)
_StrictYAMLLoader.yaml_implicit_resolvers = {
    k: [
        (tag, regex)
        for tag, regex in resolvers
        if tag
        not in (
            "tag:yaml.org,2002:bool",
            "tag:yaml.org,2002:null",
        )
    ]
    for k, resolvers in _StrictYAMLLoader.yaml_implicit_resolvers.items()
}


def resolve_placeholders(value: Any, ctx: dict[str, str] | None) -> Any:
    """递归替换字符串中的 ${KEY}.

    找不到的占位符保留原样 (不抛错, 让 Pydantic 校验时报告).
    支持 str / list / dict 三种容器, 其他类型原样返回.
    """
    ctx = ctx or {}

    def _sub(s: str) -> str:
        return _PLACEHOLDER_RE.sub(lambda m: ctx.get(m.group(1), m.group(0)), s)

    if isinstance(value, str):
        return _sub(value)
    if isinstance(value, list):
        return [resolve_placeholders(v, ctx) for v in value]
    if isinstance(value, dict):
        return {k: resolve_placeholders(v, ctx) for k, v in value.items()}
    return value


def load_scenario(path: os.PathLike[str] | str, ctx: dict[str, str] | None = None) -> ScenarioConfig:
    """加载一个 Scenario YAML 并返回校验后的 ScenarioConfig.

    4 步: 读文件 → 占位符 → schema 校验 → 资源校验.
    任何一步失败都包装成 ScenarioLoadError, 资源缺失用 ScenarioResourceError.
    """
    p = Path(path)
    if not p.exists():
        raise ScenarioLoadError(
            f"Scenario file not found: {p}",
            action="Provide a valid path to a *.scenario.yaml file.",
        )

    # 1. 读 YAML — 预处理: 把未加引号的 ${KEY} 用双引号包起来
    text = p.read_text(encoding="utf-8")
    text = _quote_placeholders(text)
    try:
        raw = yaml.load(text, Loader=_StrictYAMLLoader)
    except yaml.YAMLError as e:
        raise ScenarioLoadError(
            f"Scenario {p.name}: YAML parse error: {e}",
            action="Fix the YAML syntax. Use 'python -c \"import yaml; yaml.safe_load(open(...))\"' to test.",
        ) from e

    if not isinstance(raw, dict):
        raise ScenarioLoadError(
            f"Scenario {p.name}: top-level must be a mapping, got {type(raw).__name__}",
            action="Ensure the YAML root is a dict (starts with 'name:' / 'version:').",
        )

    # 2. 占位符解析
    resolved = resolve_placeholders(raw, ctx)

    # 3. Pydantic schema 校验
    try:
        cfg = ScenarioConfig.model_validate(resolved)
    except ValidationError as e:
        msg_lines = [f"Scenario {p.name} failed validation ({e.error_count()} errors):"]
        for err in e.errors()[:10]:
            loc = ".".join(str(x) for x in err.get("loc", ()))
            msg_lines.append(f"  - {loc}: {err.get('msg')}")
        raise ScenarioLoadError(
            "\n".join(msg_lines),
            action="Fix the fields listed above in the scenario YAML.",
        ) from e

    # 4. 物理资源校验
    _validate_resources(cfg)
    return cfg


def _validate_resources(cfg: ScenarioConfig) -> None:
    """检查 Scenario 引用的所有物理路径存在."""
    missing: list[str] = []
    missing.extend(_check_workspace(cfg))
    missing.extend(_check_a2ui(cfg))
    missing.extend(_check_skills(cfg))
    if missing:
        raise ScenarioResourceError(
            f"Scenario {cfg.name} has missing resources ({len(missing)}):",
            missing=missing,
            action=(
                "Create the missing files or fix resource_dirs in the scenario YAML. "
                "Check that all ${...} placeholders were resolved."
            ),
        )


def _check_workspace(cfg: ScenarioConfig) -> list[str]:
    out: list[str] = []
    for ws in cfg.workspace.workspace_dirs:
        if not Path(ws).exists():
            out.append(f"workspace_dir not found: {ws}")
    for ro in cfg.workspace.readonly_dirs:
        if ro and not Path(ro).exists():
            out.append(f"readonly_dir not found: {ro}")
    return out


def _check_a2ui(cfg: ScenarioConfig) -> list[str]:
    out: list[str] = []
    if cfg.a2ui.enabled and cfg.a2ui.cards_dir and not Path(cfg.a2ui.cards_dir).exists():
        out.append(f"a2ui.cards_dir not found: {cfg.a2ui.cards_dir}")
    if (
        cfg.execution.orchestration == "hitl"
        and cfg.a2ui.state_machine
        and not Path(cfg.a2ui.state_machine).exists()
    ):
        out.append(f"a2ui.state_machine not found: {cfg.a2ui.state_machine}")
    return out


def _check_skills(cfg: ScenarioConfig) -> list[str]:
    if not cfg.execution.skills:
        return []
    root = cfg.resource_dirs.get("skills")
    if not root:
        return ["resource_dirs.skills is empty but execution.skills is non-empty"]
    return [
        f"skill SKILL.md not found: {Path(root) / sk / 'SKILL.md'}"
        for sk in cfg.execution.skills
        if not (Path(root) / sk / "SKILL.md").exists()
    ]


__all__ = ["resolve_placeholders", "load_scenario"]
