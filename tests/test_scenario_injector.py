"""ScenarioInjector 单测 — 白名单 + 提示词拼接."""

from __future__ import annotations

import pytest

from openagent.scenarios.config import (
    ExecutionConfig,
    ProgressiveSkillConfig,
    RoutingConfig,
    ScenarioConfig,
    WorkspaceConfig,
)
from openagent.scenarios.injector import (
    InMemoryAuditLogger,
    InjectionResult,
    ScenarioInjector,
)


def _scenario(*, skills: list[str], tools: list[str], prompt: str = "BASE") -> ScenarioConfig:
    return ScenarioConfig(
        name="t",
        version="1.0.0",
        routing=RoutingConfig(),
        execution=ExecutionConfig(
            system_prompt=prompt,
            skills=skills,
            tools=tools,
            orchestration="single",
        ),
        workspace=WorkspaceConfig(workspace_dirs=["/tmp/proj"]),
        progressive_skill=ProgressiveSkillConfig(strategy="none"),
    )


@pytest.fixture
def injector() -> ScenarioInjector:
    return ScenarioInjector()


@pytest.fixture
def audit() -> InMemoryAuditLogger:
    return InMemoryAuditLogger()


# ----------------------------------------------------------------------
# 基础
# ----------------------------------------------------------------------


def test_inject_skills_intersection(injector: ScenarioInjector):
    s = _scenario(skills=["a", "b", "c"], tools=[])
    r = injector.inject(s, user_message="hi", caller_skills=["a", "x", "b"])
    assert sorted(r.final_skills) == ["a", "b"]


def test_inject_tools_intersection(injector: ScenarioInjector):
    s = _scenario(skills=[], tools=["t1", "t2"])
    r = injector.inject(s, user_message="hi", caller_tools=["t1", "t3", "t2"])
    assert sorted(r.final_tools) == ["t1", "t2"]


def test_inject_caller_system_prompt_appended(injector: ScenarioInjector):
    s = _scenario(skills=[], tools=[], prompt="BASE_PROMPT")
    r = injector.inject(s, user_message="hi", caller_system_prompt="USER_NOTE")
    assert r.final_system_prompt == "BASE_PROMPT\n\nUSER_NOTE"


def test_inject_caller_prompt_only_used_when_present(injector: ScenarioInjector):
    s = _scenario(skills=[], tools=[], prompt="ONLY_BASE")
    r = injector.inject(s, user_message="hi")
    assert r.final_system_prompt == "ONLY_BASE"


# ----------------------------------------------------------------------
# 拒绝记录
# ----------------------------------------------------------------------


def test_inject_records_rejected(injector: ScenarioInjector):
    s = _scenario(skills=["a"], tools=["t1"])
    r = injector.inject(
        s, user_message="hi",
        caller_skills=["a", "b", "c"],
        caller_tools=["t1", "t2"],
    )
    assert sorted(r.rejected_skills) == ["b", "c"]
    assert r.rejected_tools == ["t2"]


def test_inject_no_rejection_when_all_allowed(injector: ScenarioInjector):
    s = _scenario(skills=["a", "b"], tools=["t1"])
    r = injector.inject(
        s,
        caller_skills=["a", "b"],
        caller_tools=["t1"],
    )
    assert r.rejected_skills == []
    assert r.rejected_tools == []


def test_inject_no_rejection_when_caller_empty(injector: ScenarioInjector):
    s = _scenario(skills=["a"], tools=["t1"])
    r = injector.inject(s)
    assert r.final_skills == []
    assert r.final_tools == []
    assert r.rejected_skills == []
    assert r.rejected_tools == []


# ----------------------------------------------------------------------
# 审计
# ----------------------------------------------------------------------


def test_inject_audit_logger_recorded(audit: InMemoryAuditLogger):
    inj = ScenarioInjector(audit=audit)
    s = _scenario(skills=["a"], tools=[])
    inj.inject(s, caller_skills=["a", "b"])
    assert len(audit.records) == 1
    rec = audit.records[0]
    assert rec["event"] == "scenario_inject"
    assert rec["scenario"] == "t"
    assert rec["rejected_skills"] == ["b"]


def test_inject_default_audit_does_not_raise():
    """不传 audit 时使用 InMemoryAuditLogger 默认实现, 不应报错."""
    s = _scenario(skills=[], tools=[])
    ScenarioInjector().inject(s, caller_system_prompt="x")


# ----------------------------------------------------------------------
# 返回值
# ----------------------------------------------------------------------


def test_injection_result_to_dict(injector: ScenarioInjector):
    s = _scenario(skills=["a"], tools=[], prompt="X")
    r = injector.inject(s, caller_skills=["a"], caller_system_prompt="Y")
    d = r.to_dict()
    assert d["final_skills"] == ["a"]
    assert d["final_tools"] == []
    assert d["final_system_prompt_len"] == len("X\n\nY")
    assert d["rejected_skills"] == []
    assert d["rejected_tools"] == []


def test_injection_result_default_construction():
    r = InjectionResult()
    assert r.final_skills == []
    assert r.final_tools == []
    assert r.final_system_prompt == ""
    assert r.rejected_skills == []
    assert r.rejected_tools == []
