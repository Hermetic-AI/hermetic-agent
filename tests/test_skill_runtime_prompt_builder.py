"""tests/test_skill_runtime_prompt_builder.py — PromptBuilder 单元测试."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from hermetic_agent.skills.runtime.fragments import FragmentLoader, FragmentLoadReport
from hermetic_agent.skills.runtime.prompt_builder import PromptBuilder
from hermetic_agent.skills.registry import Skill, SkillRegistry


@dataclass
class FakeMessage:
    role: str
    content: str


def _scenario(
    *,
    name: str = "test",
    strategy: str = "none",
    system_prompt: str = "scenario system",
    a2ui_enabled: bool = False,
    initial_skills: list[dict] | None = None,
    load_on_state: dict[str, list[str]] | None = None,
) -> SimpleNamespace:
    a2ui = SimpleNamespace(enabled=a2ui_enabled)
    exec_ = SimpleNamespace(system_prompt=system_prompt)
    prog = SimpleNamespace(
        strategy=strategy,
        initial_skills=initial_skills or [],
        load_on_state=load_on_state or {},
    )
    return SimpleNamespace(name=name, a2ui=a2ui, execution=exec_, progressive_skill=prog)


class _StubFragmentLoader:
    """替换 FragmentLoader, 避免依赖文件系统."""

    def __init__(self, text: str = "", loaded: list[str] | None = None) -> None:
        self._text = text
        self._loaded = loaded or []

    def load(self, scenario, current_state):  # noqa: ANN001
        return self._text, FragmentLoadReport(loaded=list(self._loaded), total_tokens=42)


@pytest.fixture
def stub_loader() -> _StubFragmentLoader:
    return _StubFragmentLoader()


# ----- tests --------------------------------------------------------------


def test_build_includes_framework_base(stub_loader: _StubFragmentLoader) -> None:
    b = PromptBuilder(stub_loader, framework_base="BASE-CONTENT")
    out = b.build(_scenario(), current_state="S01")
    assert "BASE-CONTENT" in out


def test_build_includes_scenario_prompt(stub_loader: _StubFragmentLoader) -> None:
    b = PromptBuilder(stub_loader, framework_base="BASE")
    scn = _scenario(system_prompt="SCEN-SPECIFIC")
    out = b.build(scn, current_state="S01")
    assert "SCEN-SPECIFIC" in out


def test_build_includes_a2ui_when_enabled(stub_loader: _StubFragmentLoader) -> None:
    b = PromptBuilder(
        stub_loader,
        framework_base="BASE",
        aui_instructions="AUI-INSTR",
    )
    scn = _scenario(a2ui_enabled=True)
    out = b.build(scn, current_state="S01")
    assert "AUI-INSTR" in out


def test_build_skips_a2ui_when_disabled(stub_loader: _StubFragmentLoader) -> None:
    b = PromptBuilder(
        stub_loader,
        framework_base="BASE",
        aui_instructions="AUI-INSTR",
    )
    scn = _scenario(a2ui_enabled=False)
    out = b.build(scn, current_state="S01")
    assert "AUI-INSTR" not in out


def test_build_includes_skill_fragments(stub_loader: _StubFragmentLoader) -> None:
    stub_loader._text = "FRAG-CONTENT"
    stub_loader._loaded = ["book-flight:state-s05"]
    b = PromptBuilder(stub_loader, framework_base="BASE")
    out = b.build(_scenario(strategy="on_demand"), current_state="S05")
    assert "FRAG-CONTENT" in out
    assert "book-flight:state-s05" in out
    assert "Active skill fragments" in out


def test_build_includes_current_state(stub_loader: _StubFragmentLoader) -> None:
    b = PromptBuilder(stub_loader, framework_base="BASE")
    out = b.build(_scenario(), current_state="S11")
    assert "Current state: S11" in out


def test_build_strategy_none_skips_fragments(tmp_path: Path) -> None:
    """当 strategy=none, real loader 应当返回空 text, prompt 不应包含片段段."""
    reg = SkillRegistry()
    loader = FragmentLoader(reg, budget=1000, policy="error")
    b = PromptBuilder(loader, framework_base="BASE")
    scn = _scenario(strategy="none")
    out = b.build(scn, current_state="S01")
    assert "Active skill fragments" not in out


def test_build_includes_messages(stub_loader: _StubFragmentLoader) -> None:
    b = PromptBuilder(stub_loader, framework_base="BASE")
    msgs = [
        FakeMessage(role="user", content="hi"),
        FakeMessage(role="assistant", content="hello"),
    ]
    out = b.build(_scenario(), current_state="S01", messages=msgs)
    assert "[user] hi" in out
    assert "[assistant] hello" in out


def test_build_six_section_order(stub_loader: _StubFragmentLoader) -> None:
    """6 段顺序: base → scenario → a2ui → fragments → state → messages."""
    stub_loader._text = "FRAG"
    stub_loader._loaded = ["x:summary"]
    b = PromptBuilder(
        stub_loader,
        framework_base="1_BASE",
        aui_instructions="3_AUI",
    )
    scn = _scenario(system_prompt="2_SCEN", a2ui_enabled=True)
    msgs = [FakeMessage(role="user", content="6_MSG")]
    out = b.build(scn, current_state="S05", messages=msgs)
    idx_base = out.find("1_BASE")
    idx_scen = out.find("2_SCEN")
    idx_aui = out.find("3_AUI")
    idx_frag = out.find("FRAG")
    idx_state = out.find("Current state: S05")
    idx_msg = out.find("6_MSG")
    assert 0 <= idx_base < idx_scen < idx_aui < idx_frag < idx_state < idx_msg


def test_build_without_messages(stub_loader: _StubFragmentLoader) -> None:
    b = PromptBuilder(stub_loader, framework_base="BASE")
    out = b.build(_scenario(), current_state="S01")
    # no message section appended
    assert "[" not in out.split("Current state: S01")[1]


def test_build_with_empty_messages(stub_loader: _StubFragmentLoader) -> None:
    b = PromptBuilder(stub_loader, framework_base="BASE")
    out = b.build(_scenario(), current_state="S01", messages=[])
    # empty messages should be fine
    assert "BASE" in out
    assert "Current state: S01" in out


# ----- render_skill_section (P0-1) -----------------------------------------


def test_render_skill_section_returns_empty_when_strategy_none(tmp_path: Path) -> None:
    """当 strategy=none 或片段为空, 返回空字符串 + 空 report."""
    reg = SkillRegistry()
    loader = FragmentLoader(reg, budget=1000, policy="error")
    b = PromptBuilder(loader)
    scn = _scenario(strategy="none")
    text, report = b.render_skill_section(scn, current_state="S01")
    assert text == ""
    assert report.loaded == []


def test_render_skill_section_returns_section_with_header(stub_loader: _StubFragmentLoader) -> None:
    """非空时, 返回 [Active skill fragments: ...] header + body."""
    stub_loader._text = "FRAG-BODY"
    stub_loader._loaded = ["a:summary", "a:detail"]
    b = PromptBuilder(stub_loader)
    scn = _scenario(strategy="on_demand")
    text, report = b.render_skill_section(scn, current_state="S05")
    assert "FRAG-BODY" in text
    assert "[Active skill fragments: a:summary, a:detail]" in text
    assert report.loaded == ["a:summary", "a:detail"]


def test_render_skill_section_does_not_include_scenario_prompt(stub_loader: _StubFragmentLoader) -> None:
    """render_skill_section 只输出第 4 段; 不应带 scenario system_prompt /
    a2ui / state 标记 (这些由 caller 自己拼)."""
    stub_loader._text = "FRAG"
    stub_loader._loaded = ["a:summary"]
    b = PromptBuilder(
        stub_loader,
        framework_base="BASE",  # 不应出现
        aui_instructions="AUI",  # 不应出现
    )
    scn = _scenario(strategy="on_demand", system_prompt="SCEN-SYS")
    text, _ = b.render_skill_section(scn, current_state="S01")
    assert "FRAG" in text
    assert "SCEN-SYS" not in text
    assert "BASE" not in text
    assert "AUI" not in text
    assert "Current state" not in text
