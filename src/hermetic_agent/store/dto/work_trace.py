"""WorkTrace DTO — 持久化入参 + API 出参.

设计文档: ``docs/superpowers/specs/2026-06-30-persistent-work-trace-design.md §2``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from hermetic_agent.store.dto._common import DTOMixin, iso_or_none

TraceKind = Literal[
    "tool_io",
    "state",
    "todo",
    "question",
    "scenario",
    "card",
    "suspend",
    "product",
    "error",
]


class TraceEventResponse(DTOMixin):
    """单条 trace event (入参 + 出参共用).

    Attributes:
        seq: turn 内单调递增 (0-based).
        at: ISO timestamp.
        kind: event 类型 (见 TraceKind).
        payload: kind-specific payload dict.
    """

    seq: int = Field(ge=0)
    at: str
    kind: TraceKind
    payload: dict[str, Any]


class AppendTraceEventsRequest(DTOMixin):
    """reducer/listener 调用的 append 入参.

    若 ``turn_id`` 不存在则自动 create (status=running); 存在则 append events
    到已有 events[] 末尾 (按 seq 去重).
    """

    turn_id: str
    session_id: str
    scenario: str | None = None
    status: Literal["running", "suspended", "done", "error"] | None = None
    events: list[TraceEventResponse] = Field(default_factory=list)
    summary: dict[str, Any] | None = None


class MarkTraceStatusRequest(DTOMixin):
    """更新 turn 终态 (suspended / done / error)."""

    status: Literal["running", "suspended", "done", "error"]
    finished_at: datetime | None = None
    summary: dict[str, Any] | None = None


class WorkTraceIndexItem(DTOMixin):
    """session 下 turn 索引 (列表用, 不含完整 events)."""

    turn_id: str
    session_id: str
    scenario: str | None
    status: str | None
    started_at: str | None
    finished_at: str | None
    summary: dict[str, Any]


class TurnWorkTraceResponse(DTOMixin):
    """单 turn 完整 trace (API 出参)."""

    turn_id: str
    session_id: str
    scenario: str | None
    status: str | None
    started_at: str | None
    finished_at: str | None
    summary: dict[str, Any]
    events: list[TraceEventResponse]


class ProductContentResponse(DTOMixin):
    """产物内容 (GET /agent/turns/{id}/work-trace/products/{pid})."""

    product_id: str
    turn_id: str
    kind: Literal["file", "url", "text"]
    path: str | None = None
    url: str | None = None
    text: str | None = None
    mime: str | None = None
    size_bytes: int | None = None


def utc_iso(dt: datetime | None) -> str | None:
    """``datetime`` -> ISO 字符串; None 原样返回. 用于从 model 转 DTO."""
    return iso_or_none(dt)


__all__ = [
    "AppendTraceEventsRequest",
    "MarkTraceStatusRequest",
    "ProductContentResponse",
    "TraceEventResponse",
    "TurnWorkTraceResponse",
    "WorkTraceIndexItem",
    "TraceKind",
    "utc_iso",
]
