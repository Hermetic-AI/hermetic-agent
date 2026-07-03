"""Agent DTO — 入参 / 出参 / 列表响应.

Agent 复合体: 引用 4 类资产 (skill / mcp_server / prompt / command) 的 code 列表,
外加自身 system_prompt / model / tool_level / network 配置.
"""
from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

CODE_RE = r"^[A-Za-z0-9_\-.]+$"


def _normalize_codes(v: list[str]) -> list[str]:
    for item in v:
        if not re.match(CODE_RE, item):
            raise ValueError(f"invalid code in list: {item!r}")
    return v


class CreateAgentRequest(BaseModel):
    """创建 Agent 入参."""

    code: str = Field(min_length=1, max_length=128, pattern=CODE_RE)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2048)
    system_prompt: str = Field(default="")
    model: str = Field(default="openai/gpt-4o-mini", max_length=128)
    tool_level: str = Field(default="standard", pattern=r"^(safe|standard|full)$")
    network: str = Field(default="local", pattern=r"^(off|local|any)$")
    skill_codes: list[str] = Field(default_factory=list, max_length=32)
    mcp_server_codes: list[str] = Field(default_factory=list, max_length=32)
    prompt_codes: list[str] = Field(default_factory=list, max_length=32)
    command_codes: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("skill_codes", "mcp_server_codes", "prompt_codes", "command_codes")
    @classmethod
    def _check_codes(cls, v: list[str]) -> list[str]:
        return _normalize_codes(v)


class UpdateAgentRequest(BaseModel):
    """更新 Agent 入参 (所有字段可选)."""

    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    model: str | None = Field(default=None, max_length=128)
    tool_level: str | None = Field(default=None, pattern=r"^(safe|standard|full)$")
    network: str | None = Field(default=None, pattern=r"^(off|local|any)$")
    skill_codes: list[str] | None = Field(default=None, max_length=32)
    mcp_server_codes: list[str] | None = Field(default=None, max_length=32)
    prompt_codes: list[str] | None = Field(default=None, max_length=32)
    command_codes: list[str] | None = Field(default=None, max_length=32)
    status: str | None = None


class AgentResponse(BaseModel):
    """Agent 出参."""

    id: str
    code: str
    name: str
    description: str | None
    system_prompt: str
    model: str
    tool_level: str
    network: str
    skill_codes: list[str]
    mcp_server_codes: list[str]
    prompt_codes: list[str]
    command_codes: list[str]
    owner_user_id: str
    visibility: str
    status: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, m) -> AgentResponse:
        data = {}
        for k in cls.model_fields:
            v = getattr(m, k)
            if k == "id" and v is not None:
                v = str(v)
            data[k] = v
        return cls(**data)


class AgentListResponse(BaseModel):
    """Agent 列表响应."""

    total: int
    items: list[AgentResponse]


__all__ = [
    "CreateAgentRequest",
    "UpdateAgentRequest",
    "AgentResponse",
    "AgentListResponse",
]
