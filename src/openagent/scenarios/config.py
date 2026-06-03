"""Scenario Pydantic 配置 — L2 Scenario Orchestration Layer.

完整 Pydantic Schema 定义: ScenarioConfig + 9 个子配置块.
所有字段严格按设计文档 §5 校验, 含跨字段约束.
"""

from __future__ import annotations

import os
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# 类型别名
ToolLevel = Literal["safe", "standard", "full"]
NetworkMode = Literal["off", "local", "any"]
WorkspaceStrategy = Literal["project_relative", "absolute", "readonly_only"]
A2UIProtocol = Literal["auip", "a2ui-google", "custom"]
ProgressiveStrategy = Literal["on_demand", "all", "explicit", "none"]
BudgetPolicy = Literal["error", "warn", "truncate"]
OrchestrationMode = Literal["single", "parallel", "chain", "hitl", "delegate"]
Tier = Literal["bronze", "silver", "gold", "platinum"]
EngineType = Literal["claude_code", "opencode", "auto"]

# 危险命令 + 禁止工作区
_DENIED_REQUIRED = ("rm -rf", "sudo", "dd")
_FORBIDDEN_WS = ("/", "~", "~/", "${HOME}", "$HOME", "/root", "/home", "")


def _probe(p: str) -> str:
    """占位符替换 + ~ 展开, 用来做危险路径判断."""
    return os.path.expanduser(
        p.replace("${PROJECT_DIR}", "/__p__")
        .replace("${WORK_ROOT}", "/__w__")
        .replace("${WORK_SHARED}", "/__ws__")
        .replace("${SCENARIO_DIR}", "/__s__")
    )


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RoutingConfig(_Strict):
    trigger_keywords: list[str] = Field(default_factory=list)
    trigger_intent: str | None = None
    url_path: str | None = None
    priority: int = Field(default=100, ge=0, le=99999)


class HITLConfig(_Strict):
    card_schemas: list[str] = Field(default_factory=list)
    suspend_timeout: int = Field(default=300, ge=1, le=86400)
    state_machine: str | None = None


class ParallelConfig(_Strict):
    n: int = Field(default=2, ge=2, le=16)
    aggregation: Literal["merge", "vote", "first"] = "merge"


class ChainConfig(_Strict):
    steps: list[str] = Field(default_factory=list)


class ExecutionConfig(_Strict):
    system_prompt: str = ""
    skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    orchestration: OrchestrationMode = "single"
    hitl: HITLConfig | None = None
    parallel: ParallelConfig | None = None
    chain: ChainConfig | None = None


class SecurityConfig(_Strict):
    tool_level: ToolLevel = "standard"
    allowed_tools: list[str] = Field(default_factory=list)
    denied_tools: list[str] = Field(default_factory=list)
    allowed_commands: list[str] = Field(default_factory=list)
    denied_commands: list[str] = Field(default_factory=list)
    network: NetworkMode = "local"
    max_turns: int = Field(default=50, ge=1, le=200)
    max_budget_usd: float = Field(default=5.0, ge=0)
    require_approval_for_writes: bool = True

    @field_validator("denied_commands")
    @classmethod
    def _denied_required(cls, v: list[str]) -> list[str]:
        for cmd in _DENIED_REQUIRED:
            if not any(cmd in d for d in v):
                raise ValueError(
                    f"security.denied_commands must include '{cmd}' "
                    f"(or similar). Got: {v}. Add it explicitly."
                )
        return v


class LauncherConfig(_Strict):
    prefer_engine: EngineType = "auto"
    fallback_engine: EngineType = "auto"
    engine_config: dict[str, Any] = Field(default_factory=dict)


class WorkspaceConfig(_Strict):
    strategy: WorkspaceStrategy = "project_relative"
    workspace_dirs: list[str] = Field(min_length=1)
    readonly_dirs: list[str] = Field(default_factory=list)
    deny_dirs: list[str] = Field(default_factory=list)
    deny_path_patterns: list[str] = Field(default_factory=list)
    launcher: LauncherConfig = Field(default_factory=LauncherConfig)

    @field_validator("workspace_dirs")
    @classmethod
    def _no_root(cls, v: list[str]) -> list[str]:
        for p in v:
            if p in _FORBIDDEN_WS or _probe(p) in _FORBIDDEN_WS:
                raise ValueError(
                    f"workspace.workspace_dirs contains forbidden root path: {p!r}. "
                    f"Must be project-relative. (user 诉求 3)"
                )
        return v


class AskUserConfig(_Strict):
    tool_name: str = "ask_user"
    schema_ref: str | None = Field(default=None, alias="schema")
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class A2UIConfig(_Strict):
    enabled: bool = False
    protocol: A2UIProtocol = "auip"
    cards_dir: str | None = None
    state_machine: str | None = None
    default_card_timeout: int = Field(default=300, ge=1, le=86400)
    ask_user: AskUserConfig | None = None
    renderer_hint: str = "react_aui_v1"
    progressive_loading: bool = False


class InitialSkillConfig(_Strict):
    name: str
    mode: Literal["summary", "full", "explicit"] = "summary"


class ProgressiveSkillConfig(_Strict):
    strategy: ProgressiveStrategy = "on_demand"
    budget_tokens: int = Field(default=4000, ge=500, le=32000)
    budget_policy: BudgetPolicy = "error"
    initial_skills: list[InitialSkillConfig] = Field(default_factory=list)
    load_on_state: dict[str, list[str]] = Field(default_factory=dict)


class ResourcesConfig(_Strict):
    agent: str | None = None
    model: str | None = None
    timeout: int = Field(default=300, ge=1, le=86400)


class ScenarioConfig(_Strict):
    """完整 Scenario 配置 — Source of Truth: docs/design/.../§5."""

    name: str = Field(pattern=r"^[a-z_][a-z0-9_]*$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    description: str = ""
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)
    owner: str | None = None
    contact: str | None = None
    tier: Tier = "silver"
    routing: RoutingConfig
    execution: ExecutionConfig
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    workspace: WorkspaceConfig
    a2ui: A2UIConfig = Field(default_factory=A2UIConfig)
    progressive_skill: ProgressiveSkillConfig = Field(
        default_factory=ProgressiveSkillConfig
    )
    resource_dirs: dict[str, str] = Field(default_factory=dict)
    resources: ResourcesConfig = Field(default_factory=ResourcesConfig)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _cross_field(self) -> ScenarioConfig:
        # 1. HITL 必 a2ui.enabled
        if self.execution.orchestration == "hitl" and not self.a2ui.enabled:
            raise ValueError(
                f"Scenario {self.name}: orchestration=hitl requires a2ui.enabled=true."
            )
        # 2. on_demand 必 load_on_state
        if (
            self.progressive_skill.strategy == "on_demand"
            and not self.progressive_skill.load_on_state
        ):
            raise ValueError(
                f"Scenario {self.name}: progressive_skill.strategy=on_demand "
                f"requires non-empty load_on_state."
            )
        # 3. workspace_dirs[0] 不能是危险路径
        first = self.workspace.workspace_dirs[0]
        if first in _FORBIDDEN_WS or _probe(first) in _FORBIDDEN_WS:
            raise ValueError(
                f"Scenario {self.name}: workspace.workspace_dirs[0] = {first!r} "
                f"is forbidden."
            )
        return self


__all__ = [
    "RoutingConfig",
    "ExecutionConfig",
    "HITLConfig",
    "ParallelConfig",
    "ChainConfig",
    "SecurityConfig",
    "WorkspaceConfig",
    "LauncherConfig",
    "A2UIConfig",
    "AskUserConfig",
    "ProgressiveSkillConfig",
    "InitialSkillConfig",
    "ResourcesConfig",
    "ScenarioConfig",
]
