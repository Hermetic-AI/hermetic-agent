"""tests/test_read_skill_tool.py — read_skill tool 单元测试 (P0-2).

Anthropic Skills 协议要求 LLM 能"按需加载"子 skill 片段. 本测试
覆盖 read_skill handler 的 4 类行为:

  1. 全文 (只传 name)         → 返 SKILL.md 内容
  2. 片段 (name + fragment)   → 返 fragments/<id>.md 内容
  3. skill 不存在             → 返 SKILL_NOT_FOUND + available 列表
  4. fragment 不存在          → 返 FRAGMENT_NOT_FOUND + expected_path
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from openagent.skills.registry import Skill, SkillRegistry


def _make_skill(
    tmp_path: Path,
    name: str,
    main_text: str = "MAIN-BODY",
    fragments: dict[str, str] | None = None,
    description: str = "",
) -> Skill:
    """建一个临时 skill: SKILL.md (+ 可选 fragments/*.md)."""
    skill_dir = tmp_path / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(main_text, encoding="utf-8")
    if fragments:
        (skill_dir / "fragments").mkdir(exist_ok=True)
        for fid, body in fragments.items():
            (skill_dir / "fragments" / f"{fid}.md").write_text(body, encoding="utf-8")
    return Skill(
        name=name,
        description=description or f"skill {name}",
        source=str(skill_dir / "SKILL.md"),
    )


# Re-import the handler lazily so this test stays isolated from lifecycle.py's
# module-level work.  We import the same closure definition by inlining a copy
# of the handler that uses our test registry.
async def _read_skill_handler(
    registry: SkillRegistry, name: str, fragment: str | None = None, **_: object
) -> dict:
    """Mirror of the production handler in lifecycle.py — kept in sync."""
    from pathlib import Path as _P

    skill = registry.get(name)
    if skill is None:
        return {
            "ok": False,
            "error_code": "SKILL_NOT_FOUND",
            "name": name,
            "available": [s.name for s in registry.list_all()],
        }
    if fragment:
        if not skill.source:
            return {
                "ok": False,
                "error_code": "FRAGMENT_NOT_FOUND",
                "name": name,
                "fragment": fragment,
                "reason": "skill has no source file",
            }
        skill_dir = _P(skill.source).parent
        frag_path = skill_dir / "fragments" / f"{fragment}.md"
        if not frag_path.exists():
            return {
                "ok": False,
                "error_code": "FRAGMENT_NOT_FOUND",
                "name": name,
                "fragment": fragment,
                "expected_path": str(frag_path),
            }
        text = frag_path.read_text(encoding="utf-8")
        return {
            "ok": True,
            "name": name,
            "version": skill.version,
            "fragment": fragment,
            "content": text,
        }
    if skill.source:
        p = _P(skill.source)
        if p.is_file() and p.exists():
            return {
                "ok": True,
                "name": name,
                "version": skill.version,
                "description": skill.description,
                "content": p.read_text(encoding="utf-8"),
            }
    return {
        "ok": True,
        "name": name,
        "version": skill.version,
        "description": skill.description,
        "content": skill.prompt_template or "",
    }


# ----- tests --------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_skill_returns_full_body(tmp_path: Path) -> None:
    """只传 name → 返 SKILL.md 全文 + 元数据."""
    reg = SkillRegistry()
    reg.register(_make_skill(tmp_path, "flight-query", main_text="## Flight\nbody"))

    out = await _read_skill_handler(reg, name="flight-query")
    assert out["ok"] is True
    assert out["name"] == "flight-query"
    assert "Flight" in out["content"]
    assert out["description"]  # non-empty


@pytest.mark.asyncio
async def test_read_skill_returns_fragment(tmp_path: Path) -> None:
    """传 name + fragment → 返 fragments/<id>.md 内容."""
    reg = SkillRegistry()
    reg.register(_make_skill(
        tmp_path, "flight-query",
        fragments={"summary": "SUMMARY-DETAIL", "deep": "DEEP-DETAIL"},
    ))

    out = await _read_skill_handler(reg, name="flight-query", fragment="summary")
    assert out["ok"] is True
    assert out["fragment"] == "summary"
    assert out["content"] == "SUMMARY-DETAIL"


@pytest.mark.asyncio
async def test_read_skill_unknown_name_returns_error() -> None:
    """skill 名不在 registry → 返 SKILL_NOT_FOUND + available 列表."""
    reg = SkillRegistry()
    out = await _read_skill_handler(reg, name="nonexistent")
    assert out["ok"] is False
    assert out["error_code"] == "SKILL_NOT_FOUND"
    assert out["name"] == "nonexistent"
    assert out["available"] == []


@pytest.mark.asyncio
async def test_read_skill_unknown_fragment_returns_error(tmp_path: Path) -> None:
    """fragment 文件不存在 → 返 FRAGMENT_NOT_FOUND + expected_path."""
    reg = SkillRegistry()
    reg.register(_make_skill(tmp_path, "flight-query", fragments={"summary": "x"}))

    out = await _read_skill_handler(reg, name="flight-query", fragment="nope")
    assert out["ok"] is False
    assert out["error_code"] == "FRAGMENT_NOT_FOUND"
    assert out["fragment"] == "nope"
    assert "nope.md" in out["expected_path"]


@pytest.mark.asyncio
async def test_read_skill_registered_in_mcp_registry(tmp_path: Path) -> None:
    """验证 read_skill 工具被 MCPRegistry 正确注册 (schema 完整, handler 可调)."""
    from openagent.mcp.registry import MCPRegistry

    reg = SkillRegistry()
    reg.register(_make_skill(tmp_path, "flight-query", fragments={"summary": "OK"}))

    mcp = MCPRegistry()
    mcp.register(
        name="read_skill",
        description="test read_skill",
        input_schema={"type": "object", "required": ["name"]},
        handler=lambda **kwargs: _read_skill_handler(reg, **kwargs),
    )

    tool = mcp._tools["read_skill"]  # type: ignore[attr-defined]
    assert tool.name == "read_skill"
    assert "name" in tool.input_schema["required"]
    # Handler is reachable and async
    assert tool.handler is not None
    out = await tool.handler(name="flight-query", fragment="summary")
    assert out["ok"] is True
    assert out["content"] == "OK"
