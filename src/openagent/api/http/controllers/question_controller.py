"""QuestionController — opencode 原生 question 端点的代理 (L1).

L1 通过 L3 ``auip.opencode_resolver`` 调 opencode SDK 包装的
question_list/reply/reject, 不直接 import L4 providers (5 层依赖方向)。
"""
from __future__ import annotations

import structlog
from sanic import Blueprint
from sanic.request import Request
from sanic.response import JSONResponse
from sanic_ext import openapi as sanic_openapi

from openagent.api.http.schemas import ErrorResponse, get_bridge
from openagent.auip.opencode_resolver import (
    list_questions_for_session,
    reject_question,
    reply_question,
)

logger = structlog.get_logger(__name__)

doc_summary = sanic_openapi.summary
doc_description = sanic_openapi.description
doc_tag = sanic_openapi.tag
operation = sanic_openapi.operation
body = sanic_openapi.body
response = sanic_openapi.response

question_bp = Blueprint("questions", url_prefix="/agent")


@question_bp.get("/questions")
@doc_summary("列出 opencode pending question requests")
@doc_description(
    "代理 opencode `GET /question?directory=...`, 按 `session_id` 过滤。"
)
@doc_tag("Question")
@operation("listQuestions")
@response(200, {"questions": list}, description="Pending question 列表")
@response(400, ErrorResponse, description="参数缺失")
@response(404, ErrorResponse, description="session 不存在")
async def list_questions_route(request: Request) -> JSONResponse:
    """GET /agent/questions?session_id=... — 列出待回答 question。

    修复 P0 报告 #question-404: 原实现 ``[q for q in items if q.get("sessionID") == session_id or not session_id]``
    永远让 ``filtered`` 等于 ``items`` (空时也是空), 当 items 真的为空时
    误判为 "session not found". 现在改为:
    1) 先用 ``bridge.get_agent_for_session`` O(1) 判断 session 存在性;
    2) 仅当 session 不存在时返 404, 否则透传 upstream 列表.
    """
    session_id = (request.args.get("session_id") or "").strip()
    if not session_id:
        return JSONResponse(
            ErrorResponse(error="session_id query param is required").model_dump(),
            status=400,
        )
    bridge = get_bridge(request)
    # 先验证 session 存在 (避免误报 404)
    if bridge.get_agent_for_session(session_id) is None:
        return JSONResponse(
            ErrorResponse(error=f"Session '{session_id}' not found").model_dump(),
            status=404,
        )
    items = await list_questions_for_session(bridge, session_id)
    filtered = [q for q in items if q.get("sessionID") == session_id]
    logger.info(
        "questions_listed",
        session_id=session_id,
        total=len(items),
        filtered=len(filtered),
    )
    return JSONResponse(
        {"success": True, "session_id": session_id, "questions": filtered}
    )


@question_bp.post("/questions/<request_id>/reply")
@doc_summary("提交 question 答案")
@doc_description(
    "代理 opencode `POST /question/:id/reply`。Body: "
    "`{\"answers\": [[\"label1\"], [\"labelA\", \"labelB\"], ...]}`"
)
@doc_tag("Question")
@operation("replyQuestion")
@body({
    "application/json": {
        "schema": {
            "type": "object",
            "required": ["answers", "session_id"],
            "properties": {
                "session_id": {"type": "string", "description": "会话 ID"},
                "answers": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "string"}},
                    "description": "二维数组 answers[question_index][option_index]",
                },
            },
        },
    },
})
@response(200, {"success": bool, "replied": bool}, description="提交结果")
async def reply_question_route(request: Request, request_id: str) -> JSONResponse:
    body = request.json or {}
    session_id = (body.get("session_id") or "").strip()
    answers = body.get("answers")
    if not session_id or answers is None:
        return JSONResponse(
            ErrorResponse(error="session_id and answers are required").model_dump(),
            status=400,
        )
    if not isinstance(answers, list) or any(not isinstance(a, list) for a in answers):
        return JSONResponse(
            ErrorResponse(error="answers must be a list of lists of strings").model_dump(),
            status=400,
        )
    bridge = get_bridge(request)
    ok, err = await reply_question(bridge, request_id, session_id, answers)
    if err:
        status = 404 if "not found" in err else 502
        return JSONResponse(ErrorResponse(error=err).model_dump(), status=status)
    return JSONResponse({"success": True, "request_id": request_id, "replied": ok})


@question_bp.post("/questions/<request_id>/reject")
@doc_summary("忽略/拒绝 question")
@doc_description("代理 opencode `POST /question/:id/reject`")
@doc_tag("Question")
@operation("rejectQuestion")
@body({
    "application/json": {
        "schema": {
            "type": "object",
            "required": ["session_id"],
            "properties": {"session_id": {"type": "string", "description": "会话 ID"}},
        },
    },
})
@response(200, {"success": bool, "rejected": bool}, description="忽略结果")
async def reject_question_route(request: Request, request_id: str) -> JSONResponse:
    body = request.json or {}
    session_id = (body.get("session_id") or "").strip()
    if not session_id:
        return JSONResponse(
            ErrorResponse(error="session_id is required").model_dump(),
            status=400,
        )
    bridge = get_bridge(request)
    ok, err = await reject_question(bridge, request_id, session_id)
    if err:
        status = 404 if "not found" in err else 502
        return JSONResponse(ErrorResponse(error=err).model_dump(), status=status)
    return JSONResponse({"success": True, "request_id": request_id, "rejected": ok})


__all__ = ["question_bp"]
