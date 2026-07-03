"""Pydantic request/response models for /agent/scenarios/* endpoints.

设计目标: 极简 — 业务方传完整 scenario dict (Pydantic 在 loader 里校验),
这里只校验顶层 name/version 必填 + 形态合法.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# 通用: 允许 extras (业务方传完整的 scenario 配置, 字段会转发给 loader)
class _Permissive(BaseModel):
    model_config = ConfigDict(extra="allow")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterScenarioRequest(_Permissive):
    """POST /agent/scenarios 的请求体 — 完整 scenario config dict.

    顶层强制校验 name + version; 其余字段透传给 ScenarioConfig 校验.
    """

    name: str = Field(..., min_length=1, max_length=64, description="场景名 (kebab/snake)")
    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$", description="语义化版本")


class ScenarioListResponse(_Strict):
    """GET /agent/scenarios/ 的响应."""

    success: bool = True
    total: int
    scenarios: list[dict[str, Any]] = Field(default_factory=list)


class ScenarioGetResponse(_Strict):
    """GET /agent/scenarios/<name> 的响应."""

    success: bool = True
    scenario: dict[str, Any] | None = None
    code: str | None = None
    error: str | None = None
    available: list[str] | None = None
    action: str | None = None


class ScenarioRegisterResponse(_Strict):
    """POST /agent/scenarios/ 的响应."""

    success: bool = True
    scenario: dict[str, Any] | None = None
    code: str | None = None
    error: str | None = None
    action: str | None = None


class ScenarioDeleteResponse(_Strict):
    """DELETE /agent/scenarios/<name> 的响应."""

    success: bool = True
    name: str | None = None
    code: str | None = None
    error: str | None = None


class ScenarioReloadResponse(_Strict):
    """POST /agent/scenarios/reload 的响应."""

    success: bool = True
    loaded: int
    scenarios: list[str] = Field(default_factory=list)


class ScenarioValidateResponse(_Strict):
    """GET /agent/scenarios/<name>/validate 的响应."""

    success: bool = True
    valid: bool
    name: str
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ScenarioRoutingLogResponse(_Strict):
    """GET /agent/scenarios/routing-log 的响应."""

    success: bool = True
    log: list[dict[str, Any]] = Field(default_factory=list)


class ScenarioChatResponse(_Strict):
    """DEPRECATED: 永远不要新建 /agent/scenarios/{name}/chat 入口.

    对话入口统一在 chat_controller.py (/agent/chat + /agent/chat/stream),
    ScenarioMiddleware 在那之前做路由. 这个类保留只是为了不让旧 import 失败,
    新代码请用 ChatResponse (src/hermetic_agent/api/schemas.py).
    """

    success: bool = True
    scenario: str
    matched_by: str
    injection: dict[str, Any] | None = None
    code: str | None = None
    error: str | None = None


__all__ = [
    "RegisterScenarioRequest",
    "ScenarioListResponse",
    "ScenarioGetResponse",
    "ScenarioRegisterResponse",
    "ScenarioDeleteResponse",
    "ScenarioReloadResponse",
    "ScenarioValidateResponse",
    "ScenarioRoutingLogResponse",
    # ScenarioChatResponse 已废弃 — 不要新建 per-scenario chat 端点
    # 真实对话统一在 /agent/chat (chat_controller.py)
]
