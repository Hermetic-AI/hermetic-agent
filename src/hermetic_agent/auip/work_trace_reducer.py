"""WorkTrace Reducer — 纯函数 SSE -> TraceEvent.

无副作用: 输入 ``StreamEvent`` + 上下文, 输出 ``TraceEvent[]``.
业务规则见 ``docs/superpowers/specs/2026-06-30-persistent-work-trace-design.md §4``.

设计要点:
- 仅 8 个 kind 翻译进 trace (scenario / state / tool_io / card / suspend /
  question / todo / error / product). text / reasoning / done / session 跳过.
- ``redact_value`` 在 ``tool_result`` / ``tool_use`` 入参上递归脱敏密钥
- ``_truncate_output`` 把超 4KB 的 output 截断, 标 ``output_truncated=True``
- product 推断: 仅基于工具名 (write / edit / create / notebook_edit) 标
  ``kind=file``, 实际 path 由后续步骤补全
- seq 由 ``ReducerState`` 跨调用累计, listener 持有 1 份 / turn
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from hermetic_agent.providers.streaming import StreamEvent
from hermetic_agent.store.dto.work_trace import TraceEventResponse

MAX_OUTPUT_BYTES = 4096

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"BEGIN PRIVATE KEY[\s\S]+?END PRIVATE KEY"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{16,}"),
]

_FILE_TOOL_NAMES = {"write", "edit", "create", "notebook_edit"}


def redact_value(v: Any) -> tuple[Any, bool]:
    """递归 redact 字符串; 返回 (新值, 是否发生改动).

    仅对 ``str`` 应用密钥正则; 字典 / 列表递归.
    """
    if isinstance(v, str):
        new = v
        changed = False
        for pat in _SECRET_PATTERNS:
            replaced = pat.sub("***REDACTED***", new)
            if replaced != new:
                changed = True
                new = replaced
        return (new, changed)
    if isinstance(v, dict):
        out: dict[str, Any] = {}
        any_change = False
        for k, vv in v.items():
            nv, c = redact_value(vv)
            out[k] = nv
            any_change = any_change or c
        return (out, any_change)
    if isinstance(v, list):
        out_list: list[Any] = []
        any_change = False
        for item in v:
            nv, c = redact_value(item)
            out_list.append(nv)
            any_change = any_change or c
        return (out_list, any_change)
    return (v, False)


def _truncate_output(v: Any) -> tuple[Any, bool]:
    """output > 4KB 截断 + 标记 truncated."""
    raw = v if isinstance(v, str) else repr(v)
    encoded = raw.encode("utf-8", errors="replace")
    if len(encoded) <= MAX_OUTPUT_BYTES:
        return (v, False)
    truncated = encoded[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace") + "…[truncated]"
    return (truncated, True)


def _infer_products(tool_name: str, _output: Any) -> list[dict[str, Any]]:
    """从 tool name + output 推断 product (heuristic)."""
    products: list[dict[str, Any]] = []
    name_l = (tool_name or "").lower()
    if name_l in _FILE_TOOL_NAMES:
        products.append({"kind": "file", "path": None})
    return products


@dataclass
class ReducerContext:
    """reducer 上下文 (turn 元信息)."""

    turn_id: str
    session_id: str
    scenario: str | None
    seq: int = 0
    started_at: str | None = None
    state: ReducerState | None = None


@dataclass
class ReducerState:
    """跨 event 维持 seq 计数; listener 持有 1 份 / turn."""

    seq: int = 0
    tool_call_index: dict[str, str] = field(default_factory=dict)


def _next(state: ReducerState) -> TraceEventResponse:
    seq = state.seq
    state.seq += 1
    return TraceEventResponse(seq=seq, at="", kind="error", payload={})


def reduce_event(
    event: StreamEvent,
    ctx: ReducerContext,
    state: ReducerState | None = None,
) -> list[TraceEventResponse]:
    """单 SSE event -> 0..N TraceEvent; state 累计 seq.

    参数:
        event: 来自 chat 流的一个 ``StreamEvent``
        ctx:   业务上下文 (turn_id / scenario 等; 兼容旧调用, 实际未直接读)
        state: 跨 event 共享的 seq 状态; 不传则内部 new 一个 (丢弃 seq)
    """
    state = state or ReducerState()
    out: list[TraceEventResponse] = []
    etype = event.type

    if etype == "scenario":
        e = _next(state)
        e.kind = "scenario"
        e.payload = {
            "name": event.data.get("name"),
            "version": event.data.get("version", ""),
            "matched_by": event.data.get("matched_by", "default"),
        }
        out.append(e)
    elif etype == "state":
        e = _next(state)
        e.kind = "state"
        e.payload = {"from": event.data.get("from"), "to": event.data.get("to")}
        if event.data.get("label"):
            e.payload["label"] = event.data["label"]
        out.append(e)
    elif etype == "tool_use":
        raw_input = event.data.get("input") or {}
        redacted_input, _ = redact_value(raw_input)
        e = _next(state)
        e.kind = "tool_io"
        e.payload = {
            "id": event.data.get("part_id") or event.data.get("id") or "",
            "name": event.data.get("tool_name") or event.data.get("name") or "unknown",
            "phase": "call",
            "input": redacted_input,
        }
        out.append(e)
    elif etype == "tool_result":
        raw_output = event.data.get("output")
        redacted, _ = redact_value(raw_output)
        truncated_output, is_trunc = _truncate_output(redacted)
        tool_name = event.data.get("tool_name") or event.data.get("name") or "unknown"
        e = _next(state)
        e.kind = "tool_io"
        e.payload = {
            "id": event.data.get("part_id") or event.data.get("id") or "",
            "name": tool_name,
            "phase": "result",
            "output_redacted": truncated_output,
            "output_truncated": is_trunc,
        }
        out.append(e)
        # product 推断
        for prod in _infer_products(tool_name, redacted):
            pe = _next(state)
            pe.kind = "product"
            pe.payload = prod
            out.append(pe)
    elif etype == "card":
        e = _next(state)
        e.kind = "card"
        e.payload = {
            "card_id": event.data.get("card_id", ""),
            "card_type": event.data.get("card_type", ""),
        }
        if event.data.get("title"):
            e.payload["title"] = event.data["title"]
        out.append(e)
    elif etype in {"suspend", "resume"}:
        e = _next(state)
        e.kind = "suspend"
        e.payload = {
            "checkpoint_id": event.data.get("checkpoint_id", ""),
        }
        if etype == "resume":
            e.payload["action"] = "resume"
        out.append(e)
    elif etype == "question_asked":
        e = _next(state)
        e.kind = "question"
        e.payload = {
            "id": event.data.get("request_id", ""),
            "status": "asked",
            "prompt": event.data.get("questions"),
        }
        out.append(e)
    elif etype in {"question_replied", "question_rejected"}:
        e = _next(state)
        e.kind = "question"
        e.payload = {
            "id": event.data.get("request_id", ""),
            "status": "replied" if etype == "question_replied" else "rejected",
        }
        if etype == "question_replied":
            e.payload["answers"] = event.data.get("answers")
        out.append(e)
    elif etype == "todo_updated":
        e = _next(state)
        e.kind = "todo"
        e.payload = {"items": event.data.get("todos", [])}
        out.append(e)
    elif etype == "error":
        e = _next(state)
        e.kind = "error"
        e.payload = {
            "code": event.data.get("code", "INTERNAL"),
            "message": event.data.get("message", ""),
        }
        out.append(e)
    # else: text / reasoning / done / session → 不进 trace

    return out


__all__ = [
    "ReducerContext",
    "ReducerState",
    "reduce_event",
    "redact_value",
    "MAX_OUTPUT_BYTES",
]
