"""hermetic-skill-cli — SKILL 脚手架 + 校验 CLI.

子命令:
  init <name>      在 work/shared/skills/ 下生成新 SKILL 模板目录
  validate <path>  校验已有 SKILL (SKILL.md + __init__.py + skill.yaml)
  list             列出 work/shared/skills/ 下所有 SKILL

设计原则:
  - 纯 Python, 跟 hermetic-agent 同包发布 (可选 extras, 不阻塞主包)
  - 不强制 opencode SDK 依赖 (pyyaml 已有, 复用 auip.skill_compiler)
  - 单文件模块, 控制在 L5 ≤ 200 行
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml


def _project_root() -> Path:
    """``work/shared/skills/`` 所在的项目根 (cwd 或其祖先)."""
    cwd = Path.cwd().resolve()
    for p in [cwd, *cwd.parents]:
        if (p / "work" / "shared" / "skills").is_dir():
            return p
    return cwd


# ---------------------------------------------------------------------------
# SKILL template
# ---------------------------------------------------------------------------

_SKILL_MD_TEMPLATE = """---
name: {skill_name}
version: 1.0.0
description: |
  {skill_name} — TODO: 简述本 SKILL 的业务能力 + 何时调用.
triggers:
  - "TODO: 触发关键词 1"
  - "TODO: 触发关键词 2"
input_schema:
  type: object
  required: []
  properties: {{}}
output_schema:
  type: object
  required: []
  properties: {{}}
---

# {skill_name} (Skill)

> TODO: 概述本 SKILL, 列关键文件 + 核心状态机.

## 1. 状态机

| # | State ID | Name     | Description                  |
|---|----------|----------|------------------------------|
| 1 | S01      | AwaitInput | 等用户提供输入              |
| 2 | F1       | Done       | 流程完成                    |

## 2. 工具白名单

- `ask_user` (框架级, Hub 注册)

## 3. Operating Rules

1. 收到 trigger 关键词, 进入 S01
2. 调 `ask_user` 收集必需输入
3. 处理完毕 → F1 终止

## 4. 完成定义

- 用户在 card 上点击 "确认" → F1
- 用户在 card 上点击 "取消" → S01
"""

_INIT_PY_TEMPLATE = '''"""{skill_name} — 业务 SKILL 注册样板.

Hub 启动时扫描 SKILL 目录, 自动 import 各模块, 调本文件暴露的
``register_*()`` 把业务实现注入基座 Registry.

业务 SKILL 标准做法:
  1. 在本 ``__init__.py`` 顶层调 ``register_card_type()`` 把所有要用的
     CardType 字符串注册到基座白名单.
  2. 在 ``card_renderers/`` 实现 CardRenderer 子类.
  3. 在 ``message_rewriters/`` 实现 MessageRewriter 子类.
  4. 在本 ``__init__.py`` 暴露 ``register_renderers()`` /
     ``register_rewriters()`` 入口, 由 Hub 启动钩子调用.
"""
from __future__ import annotations

from hermetic_agent.auip import (
    CardRendererRegistry,
    MessageRewriterRegistry,
    register_card_type,
)

# TODO: 把本 SKILL 用到的所有 CardType 字符串注册到基座白名单.
# 例: register_card_type("MY_RESULT")
#     register_card_type("MY_FORM")
register_card_type("{skill_name_upper}_RESULT")


def register_renderers(registry: CardRendererRegistry) -> None:
    """Hub 启动时调用 — 把本 SKILL 的 CardRenderer 注册到基座 Registry.

    TODO: 实现并注册你的 CardRenderer 子类. 例::

        from .card_renderers.my_renderer import MyCardRenderer
        registry.register(MyCardRenderer())
    """


def register_rewriters(registry: MessageRewriterRegistry) -> None:
    """Hub 启动时调用 — 把本 SKILL 的 MessageRewriter 注册到基座 Registry.

    TODO: 实现并注册你的 MessageRewriter 子类.
    """


__all__ = [
    "register_renderers",
    "register_rewriters",
]
'''

_SKILL_YAML_TEMPLATE = """\
# {skill_name} 配置文件 — 由 Hub 启动时加载.
# TODO: 填实际值.

skill:
  name: {skill_name}
  version: "1.0.0"

# 外部 MCP 工具声明 (本 SKILL 调用的所有 MCP 工具)
# 例: feihe-travel MCP 提供 queryFlightBasic 等.
mcp_tools:
  # my-mcp-server:
  #   tools: [my_tool_a, my_tool_b]

# 本 SKILL 需要的外部凭证 (Hub 启动时校验, 缺失则告警)
# 真实值走 scenario.yaml 的 env 注入, 此处只声明.
required_envs:
  # MY_API_KEY: "${{MY_API_KEY}}"

# 渐进式加载配置 (Anthropic Skills 协议)
fragment_loader:
  strategy: on_demand      # none | all | on_demand | explicit
  budget_tokens: 4000      # 每次 chat 加载的 skill 片段总 token 上限
  budget_policy: error     # 超预算时: error | warn | truncate
"""


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    """在 work/shared/skills/<name>/ 下生成 SKILL 模板."""
    name: str = args.name
    target = _project_root() / "work" / "shared" / "skills" / name
    if target.exists():
        print(f"ERROR: target already exists: {target}", file=sys.stderr)
        return 2
    target.mkdir(parents=True, exist_ok=False)
    (target / "__init__.py").write_text(
        _INIT_PY_TEMPLATE.format(skill_name=name, skill_name_upper=name.upper()),
        encoding="utf-8",
    )
    (target / "SKILL.md").write_text(
        _SKILL_MD_TEMPLATE.format(skill_name=name),
        encoding="utf-8",
    )
    (target / "skill.yaml").write_text(
        _SKILL_YAML_TEMPLATE.format(skill_name=name),
        encoding="utf-8",
    )
    print(f"OK: scaffolded {target}")
    print("  next steps:")
    print(f"    1. edit {target}/SKILL.md (状态机 + 工具白名单)")
    print(f"    2. edit {target}/__init__.py (register_card_type + register_renderers/rewriters)")
    print("    3. implement card_renderers/my_renderer.py (可选)")
    print(f"    4. wire into a scenario: work/scenarios/<x>.scenario.yaml → skills: [- {name}]")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """校验已有 SKILL: SKILL.md 可被 compile_skill_md 解析 + __init__.py 可 import."""
    path = Path(args.path).resolve()
    if not path.is_dir():
        print(f"ERROR: not a directory: {path}", file=sys.stderr)
        return 2

    skill_md = path / "SKILL.md"
    init_py = path / "__init__.py"
    errors: list[str] = []
    warnings: list[str] = []

    if not skill_md.is_file():
        errors.append(f"missing {skill_md.name}")
    if not init_py.is_file():
        errors.append(f"missing {init_py.name}")

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    # 1. SKILL.md 解析
    try:
        from hermetic_agent.auip.skill_compiler import compile_skill_md
        out = compile_skill_md(skill_md)
    except Exception as exc:
        print(f"ERROR: SKILL.md parse failed: {exc}", file=sys.stderr)
        return 1
    name = out.get("name", "?")
    states = out.get("states", [])
    tools = out.get("allowed_tools", [])
    print(f"  SKILL.md OK  name={name} v{out.get('version', '?')} "
          f"states={len(states)} tools={len(tools)}")
    if not states:
        warnings.append("SKILL.md has no state machine (S01 / F1 etc.)")
    if not tools:
        warnings.append("SKILL.md declares no tools (no `## Tool whitelist` section?)")

    # 2. __init__.py AST 静态分析 (不真的 import, 避免运行时副作用)
    # 检查是否有 register_renderers() / register_rewriters() 函数定义,
    # 以及 register_card_type() 调用.
    import ast
    raw_init = init_py.read_text(encoding="utf-8")
    if raw_init.startswith("\ufeff"):
        raw_init = raw_init.lstrip("\ufeff")
    try:
        tree = ast.parse(raw_init)
    except SyntaxError as exc:
        print(f"ERROR: __init__.py syntax error: {exc}", file=sys.stderr)
        return 1

    has_renderers = False
    has_rewriters = False
    registered_types: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            if node.name == "register_renderers":
                has_renderers = True
            elif node.name == "register_rewriters":
                has_rewriters = True
        elif isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Name)
                and func.id == "register_card_type"
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                registered_types.append(str(node.args[0].value))
    if not has_renderers:
        warnings.append("__init__.py missing register_renderers() (Hub will skip card rendering)")
    if not has_rewriters:
        warnings.append("__init__.py missing register_rewriters() (Hub will skip message rewriters)")
    print(f"  __init__.py OK  register_renderers={has_renderers} "
          f"register_rewriters={has_rewriters} "
          f"register_card_type={registered_types or '(none)'}")
    # 临时注册本 SKILL 的 card_type, 让后续 is_valid_card_type 检查能用
    for ct in registered_types:
        try:
            from hermetic_agent.auip import register_card_type
            register_card_type(ct)
        except ValueError:
            pass  # 跟内置冲突 → 跳过

    # 3. skill.yaml 可选但推荐
    skill_yaml = path / "skill.yaml"
    if skill_yaml.is_file():
        try:
            data: Any = yaml.safe_load(skill_yaml.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            print(f"ERROR: skill.yaml parse failed: {exc}", file=sys.stderr)
            return 1
        if not isinstance(data, dict):
            errors.append("skill.yaml top-level must be a mapping")
            return 1
        print(f"  skill.yaml OK  keys={list(data.keys())}")
    else:
        warnings.append("skill.yaml missing (Hub will use defaults)")

    # 4. 业务 CardType 已注册
    from hermetic_agent.auip import list_registered_card_types
    registered = list_registered_card_types()
    skill_registered = {n for n in registered if n.startswith(name.upper()) or n.endswith("_RESULT") or n.endswith("_FORM")}
    if not skill_registered:
        warnings.append(
            f"no card_type registered for this SKILL (expected something like {name.upper()}_RESULT)"
        )
    else:
        print(f"  registered card_types: {sorted(skill_registered)}")

    # 汇总
    if warnings:
        print("\nWARNINGS:")
        for w in warnings:
            print(f"  ! {w}")
    if errors:
        print("\nERRORS:")
        for e in errors:
            print(f"  ✗ {e}")
        return 1
    print(f"\nOK: {path.name} validated")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """列出 work/shared/skills/ 下所有 SKILL 目录."""
    skills_dir = _project_root() / "work" / "shared" / "skills"
    if not skills_dir.is_dir():
        print(f"ERROR: skills dir not found: {skills_dir}", file=sys.stderr)
        return 2
    rows: list[tuple[str, str, str]] = []
    for p in sorted(skills_dir.iterdir()):
        if not p.is_dir():
            continue
        sm = p / "SKILL.md"
        if not sm.is_file():
            rows.append((p.name, "-", "(no SKILL.md)"))
            continue
        try:
            from hermetic_agent.auip.skill_compiler import compile_skill_md
            out = compile_skill_md(sm)
        except Exception as exc:
            rows.append((p.name, "?", f"parse error: {exc}"))
            continue
        rows.append((
            p.name,
            str(out.get("version", "?")),
            f"{len(out.get('states', []))} states, {len(out.get('allowed_tools', []))} tools",
        ))
    if not rows:
        print(f"(no skills found under {skills_dir})")
        return 0
    name_w = max(len(r[0]) for r in rows)
    print(f"{'NAME'.ljust(name_w)}  VERSION  DETAIL")
    print(f"{'-' * name_w}  -------  ------")
    for n, v, d in rows:
        print(f"{n.ljust(name_w)}  {v.ljust(7)}  {d}")
    return 0


# ---------------------------------------------------------------------------
# argparse plumbing
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="hermetic-skill",
        description="hermetic-agent SKILL 脚手架 + 校验 CLI",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="在 work/shared/skills/ 下生成新 SKILL 模板")
    p_init.add_argument("name", help="SKILL 名 (kebab-case, 例 my-greeting-skill)")
    p_init.set_defaults(func=cmd_init)

    p_val = sub.add_parser("validate", help="校验一个已有 SKILL 目录")
    p_val.add_argument("path", help="SKILL 目录路径 (含 SKILL.md / __init__.py)")
    p_val.set_defaults(func=cmd_validate)

    p_list = sub.add_parser("list", help="列出 work/shared/skills/ 下所有 SKILL")
    p_list.set_defaults(func=cmd_list)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
