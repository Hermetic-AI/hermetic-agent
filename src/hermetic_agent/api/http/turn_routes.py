"""turn_routes.py — HITL Turn 生命周期 5 个端点.

设计: docs/design/integrated-orchestration-plan.md §3.1 L1 + book-flight-hitl-design.md §4.

- POST /agent/turn/<id>/resume       从 SUSPEND 恢复 (SSE 推 RESUME + 后续事件)
- GET  /agent/turn/<id>               查询 Turn 当前状态
- GET  /agent/turn/<id>/events?after=N 补拉事件 (SSE, from seq=N+1)
- POST /agent/turn/<id>/heartbeat     延长挂起超时
- POST /agent/turn/<id>/cancel        取消 Turn

依赖:
- request.app.ctx.turn_store: TurnStore 实例
- request.app.ctx.hitl_factory: Callable[[ScenarioConfig], SuspendableScheduler]
- request.app.ctx.scenario_registry: ScenarioRegistry
"""
from __future__ import annotations

import contextlib
import time
from typing import Any

import structlog
from pydantic import BaseModel, Field
from sanic import Blueprint
from sanic.request import Request
from sanic.response import JSONResponse
from sanic.response.types import ResponseStream
from sanic_ext import openapi as sanic_openapi

from hermetic_agent.api.http.streaming import turn_event_to_sse
from hermetic_agent.auip.errors import TurnNotFound
from hermetic_agent.core.suspendable_scheduler import UserInput
from hermetic_agent.providers.streaming import StreamEvent

logger = structlog.get_logger(__name__)

doc_summary = sanic_openapi.summary
doc_description = sanic_openapi.description
doc_tag = sanic_openapi.tag
operation = sanic_openapi.operation
response = sanic_openapi.response
body = sanic_openapi.body

turn_bp = Blueprint("agent_turns", url_prefix="/agent/turn")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _get_turn_store(request: Request) -> Any:
    return getattr(request.app.ctx, "turn_store", None)


def _get_scenario_registry(request: Request) -> Any:
    return getattr(request.app.ctx, "scenario_registry", None)


# TurnEvent → SSE 翻译统一在 hermetic_agent.api.http.streaming.turn_bridge
# 共享给 chat_controller 与 turn_routes, 避免重复维护.
# 兼容旧 import path: 仍然提供 _turn_event_to_sse 名称.
_turn_event_to_sse = turn_event_to_sse


# ---------------------------------------------------------------------------
# Pydantic models for OpenAPI body/response
# ---------------------------------------------------------------------------


class ResumeTurnRequest(BaseModel):
    """POST /agent/turn/<id>/resume 请求体."""

    correlation_id: str = Field(..., description="来自 SUSPEND 事件的 correlation_id")
    user_input: dict[str, Any] = Field(
        default_factory=dict,
        description="用户输入 (结构由 SUSPEND.input_schema 决定)",
    )
    action_id: str | None = Field(None, description="触发的动作按钮 id (来自卡片 actions)")


class TurnStateResponse(BaseModel):
    """GET /agent/turn/<id> 响应."""

    success: bool
    turn: dict[str, Any] = Field(..., description="turn 快照: session_id / skill_name / status / created_at")


class TurnStateErrorResponse(BaseModel):
    """Turn 端点的统一错误响应."""

    success: bool = False
    code: str = Field(..., description="SCENARIO_NOT_FOUND / TURN_NOT_FOUND / TURN_STORE_UNAVAILABLE")
    error: str
    action: str | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@turn_bp.post("/<turn_id>/resume")
@doc_summary("恢复一个被挂起的 Turn (HITL)")
@doc_description(
    "Body: `{\"correlation_id\": \"...\", \"user_input\": {...}, \"action_id\": \"submit\"}`\n\n"
    "SSE 流推回 RESUME + 后续事件 (TOOL_RESULT / STATE / DONE 等)。\n\n"
    "事件序列 (HITL 恢复):\n"
    "1. `resume` 事件 (含 checkpoint_id)\n"
    "2. `tool_result` 事件 (ask_user 工具被回填 user_input)\n"
    "3. `state` 事件 (resume transition)\n"
    "4. `done` 事件 (end_turn)\n\n"
    "错误情况: 推送一个 `error` 事件后立即结束流。"
)
@doc_tag("Turn")
@operation("resumeTurn")
@body(ResumeTurnRequest)
@response(200, None, description="SSE 流: text/event-stream")
@response(400, TurnStateErrorResponse, description="缺 correlation_id / scenario 不存在")
@response(404, TurnStateErrorResponse, description="turn_id 未找到")
@response(503, TurnStateErrorResponse, description="turn_store / scenario_registry 未初始化")
async def resume_turn(request: Request, turn_id: str) -> ResponseStream:
    """POST /agent/turn/<id>/resume — 从 SUSPEND 恢复."""
    store = _get_turn_store(request)
    registry = _get_scenario_registry(request)
    if store is None:
        return ResponseStream(
            _err_stream("turn_store not initialized", "TURN_STORE_UNAVAILABLE", 503),
            status=503, content_type="text/event-stream",
        )
    if registry is None:
        return ResponseStream(
            _err_stream("scenario_registry not initialized", "SCENARIO_REGISTRY_UNAVAILABLE", 503),
            status=503, content_type="text/event-stream",
        )
    body = request.json or {}
    correlation_id = body.get("correlation_id")
    user_input_data = body.get("user_input", {})
    action_id = body.get("action_id")

    if not correlation_id:
        return ResponseStream(
            _err_stream("correlation_id is required", "VALIDATION_FAILED", 400),
            status=400, content_type="text/event-stream",
        )

    async def _stream(resp: ResponseStream) -> None:
        try:
            # 找 turn 所属 scenario
            turn = await store.get_turn(turn_id)
            if turn is None:
                await resp.write(
                    StreamEvent.error(message=f"turn {turn_id} not found", code="TURN_NOT_FOUND").to_sse()
                )
                return
            scenario_name = turn.get("skill_name", "_default")
            scenario = registry.get(scenario_name)
            if scenario is None:
                await resp.write(
                    StreamEvent.error(
                        message=f"scenario {scenario_name} not found", code="SCENARIO_NOT_FOUND"
                    ).to_sse()
                )
                return

            hitl_factory = getattr(request.app.ctx, "hitl_factory", None)
            if hitl_factory is None:
                await resp.write(
                    StreamEvent.error(message="hitl_factory not initialized", code="HITL_NOT_READY").to_sse()
                )
                return
            scheduler = hitl_factory(scenario)
            user_input = UserInput(
                correlation_id=correlation_id,
                action_id=action_id,
                data=user_input_data,
            )
            try:
                async for turn_evt in scheduler.resume(turn_id, user_input):
                    await resp.write(_turn_event_to_sse(turn_evt).to_sse())
            except TurnNotFound as e:
                await resp.write(
                    StreamEvent.error(message=str(e), code="TURN_NOT_FOUND").to_sse()
                )
        except Exception as e:
            logger.error("resume_turn_failed", turn_id=turn_id, error=str(e))
            with contextlib.suppress(Exception):
                await resp.write(
                    StreamEvent.error(message=f"{type(e).__name__}: {e}").to_sse()
                )
        finally:
            with contextlib.suppress(Exception):
                await resp.eof()

    return ResponseStream(
        _stream,
        status=200,
        content_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@turn_bp.get("/<turn_id>")
@doc_summary("查询 Turn 状态")
@doc_description("返回 Turn 快照: session_id / skill_name / skill_version / status (running/suspended/done/error/cancelled) / created_at。")
@doc_tag("Turn")
@operation("getTurn")
@response(200, TurnStateResponse, description="Turn 当前状态")
@response(404, TurnStateErrorResponse, description="turn_id 不存在")
@response(503, TurnStateErrorResponse, description="turn_store 未初始化")
async def get_turn(request: Request, turn_id: str) -> JSONResponse:
    """GET /agent/turn/<id> — Turn 当前快照."""
    store = _get_turn_store(request)
    if store is None:
        return JSONResponse(
            {"success": False, "code": "TURN_STORE_UNAVAILABLE", "error": "turn_store not initialized"},
            status=503,
        )
    turn = await store.get_turn(turn_id)
    if turn is None:
        return JSONResponse(
            {"success": False, "code": "TURN_NOT_FOUND", "error": f"turn {turn_id} not found"},
            status=404,
        )
    return JSONResponse({"success": True, "turn": turn})


@turn_bp.get("/<turn_id>/events")
@doc_summary("补拉 Turn 事件 (SSE)")
@doc_description(
    "从 `?after=N` 之后开始流式推回 turn 的所有事件 (用于前端 reconnect / replay)。\n\n"
    "每个事件是一个 `data: {\"type\": \"...\", \"data\": {...}}` 行, 最后以 `done` (reason=replay_end) 结束。"
)
@doc_tag("Turn")
@operation("getTurnEvents")
@response(200, None, description="SSE 流: text/event-stream")
@response(404, TurnStateErrorResponse, description="turn_id 不存在")
@response(503, TurnStateErrorResponse, description="turn_store 未初始化")
async def get_turn_events(request: Request, turn_id: str) -> ResponseStream:
    """GET /agent/turn/<id>/events?after=N — SSE 补拉."""
    store = _get_turn_store(request)
    if store is None:
        return ResponseStream(
            _err_stream("turn_store not initialized", "TURN_STORE_UNAVAILABLE", 503),
            status=503, content_type="text/event-stream",
        )
    try:
        after = int(request.args.get("after", "0"))
    except (TypeError, ValueError):
        after = 0

    async def _stream(resp: ResponseStream) -> None:
        try:
            events = await store.get_events(turn_id, after_seq=after)
            if not events:
                # 兜底
                turn = await store.get_turn(turn_id)
                if turn is None:
                    await resp.write(
                        StreamEvent.error(message=f"turn {turn_id} not found", code="TURN_NOT_FOUND").to_sse()
                    )
                    return
            for evt in events:
                await resp.write(_turn_event_to_sse(evt).to_sse())
            await resp.write(StreamEvent.done(reason="replay_end", replayed=len(events)).to_sse())
        except Exception as e:
            logger.error("get_turn_events_failed", turn_id=turn_id, error=str(e))
            with contextlib.suppress(Exception):
                await resp.write(
                    StreamEvent.error(message=f"{type(e).__name__}: {e}").to_sse()
                )
        finally:
            with contextlib.suppress(Exception):
                await resp.eof()

    return ResponseStream(
        _stream,
        status=200,
        content_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@turn_bp.post("/<turn_id>/heartbeat")
@doc_summary("延长 Turn 挂起超时")
@doc_description("前端每 60s 调一次, 防止挂起超时 (默认 5min, S11/F3 10min). 始终返回 200 + ts.")
@doc_tag("Turn")
@operation("heartbeatTurn")
@response(200, None, description="{\"success\": true, \"turn_id\": \"...\", \"ts\": 12345.0}")
@response(404, TurnStateErrorResponse, description="turn_id 不存在")
async def heartbeat_turn(request: Request, turn_id: str) -> JSONResponse:
    """POST /agent/turn/<id>/heartbeat — 延长超时 (前端每 60s 调一次)."""
    store = _get_turn_store(request)
    if store is None:
        return JSONResponse(
            {"success": False, "code": "TURN_STORE_UNAVAILABLE", "error": "turn_store not initialized"},
            status=503,
        )
    turn = await store.get_turn(turn_id)
    if turn is None:
        return JSONResponse(
            {"success": False, "code": "TURN_NOT_FOUND", "error": f"turn {turn_id} not found"},
            status=404,
        )
    # InMemoryTurnStore 不存 timeout 字段, 这里只返回 ok + 当前时间
    return JSONResponse(
        {
            "success": True,
            "turn_id": turn_id,
            "status": turn.get("status"),
            "ts": time.time(),
        }
    )


@turn_bp.post("/<turn_id>/cancel")
@doc_summary("取消 Turn")
@doc_description("把 turn 标为 cancelled. 已 suspend 的 turn 不会再被 resume.")
@doc_tag("Turn")
@operation("cancelTurn")
@response(200, None, description="{\"success\": true, \"turn_id\": \"...\", \"status\": \"cancelled\"}")
@response(404, TurnStateErrorResponse, description="turn_id 不存在")
@response(500, TurnStateErrorResponse, description="update_turn_status 失败")
async def cancel_turn(request: Request, turn_id: str) -> JSONResponse:
    """POST /agent/turn/<id>/cancel — 标记 cancelled."""
    store = _get_turn_store(request)
    if store is None:
        return JSONResponse(
            {"success": False, "code": "TURN_STORE_UNAVAILABLE", "error": "turn_store not initialized"},
            status=503,
        )
    try:
        await store.update_turn_status(turn_id, "cancelled")
    except Exception as e:
        return JSONResponse(
            {"success": False, "code": "CANCEL_FAILED", "error": str(e)},
            status=500,
        )
    return JSONResponse({"success": True, "turn_id": turn_id, "status": "cancelled"})


# ---------------------------------------------------------------------------
# helpers (private)
# ---------------------------------------------------------------------------


async def _err_stream(message: str, code: str, status: int):
    """构造一个 SSE error 流的 ResponseStream 协程.

    Sanic 的 ResponseStream 接受 async callable (resp), 所以这里返回一个 generator.
    """

    async def _gen(resp):
        await resp.write(
            StreamEvent.error(message=message, code=code).to_sse()
        )
        await resp.eof()

    return _gen
