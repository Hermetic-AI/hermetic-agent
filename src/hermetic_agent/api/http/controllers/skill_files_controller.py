"""SkillFilesController — /agent/skills/<code>/files/* 端点.

管理 skill 文件清单 (MinIO / 内存两种 backend, 由 ``app.ctx.asset_clients`` 注入).

延迟加载: 不 import service / store 到模块级, 避免 Sanic 路由注册时触发 DB 连接.
"""
from __future__ import annotations

import base64
import io as _io

import structlog
from sanic import Blueprint
from sanic.request import Request
from sanic.response import JSONResponse
from sanic_ext import openapi as sanic_openapi

from hermetic_agent.store.object.skill_files import validate_skill_code

logger = structlog.get_logger(__name__)
doc_summary = sanic_openapi.summary
doc_tag = sanic_openapi.tag

skill_files_bp = Blueprint("skill_files", url_prefix="/agent/skills")

MAX_FILE_SIZE = 16 * 1024 * 1024
MAX_BATCH = 8


def _err(code: str, message: str, status: int = 400) -> JSONResponse:
    return JSONResponse(
        {"success": False, "code": code, "error": message},
        status=status,
    )


def _get_clients(request: Request) -> dict:
    return request.app.ctx.asset_clients


def _validate_code_or_400(code: str) -> str | JSONResponse:
    """统一在 controller 入口校验 code; 不合法直接返 400."""
    try:
        return validate_skill_code(code)
    except ValueError as e:
        return _err("VALIDATION_FAILED", str(e), status=400)


@skill_files_bp.get("/<code>/files")
@doc_summary("List files in a skill")
@doc_tag("Skill Files")
async def list_skill_files(request: Request, code: str) -> JSONResponse:
    code = _validate_code_or_400(code)
    if isinstance(code, JSONResponse):
        return code
    cl = _get_clients(request)
    files = await cl["skill_files"].list_files(code)
    return JSONResponse({
        "code": code,
        "total": len(files),
        "items": [
            {"path": f.path, "size": f.size, "etag": f.etag,
             "modified_at": str(f.modified_at)}
            for f in files
        ],
    })


@skill_files_bp.get("/<code>/files/<path:path>")
@doc_summary("Download one skill file")
@doc_tag("Skill Files")
async def get_skill_file(request: Request, code: str, path: str) -> JSONResponse:
    code = _validate_code_or_400(code)
    if isinstance(code, JSONResponse):
        return code
    cl = _get_clients(request)
    try:
        blob = await cl["skill_files"].download_file(code, path)
    except FileNotFoundError:
        return _err("FILE_NOT_FOUND", f"{code}/{path} not found", status=404)
    except Exception as e:
        logger.error("skill_file_download_error", error=str(e))
        return _err("OBJECT_STORE_UNAVAILABLE", str(e), status=503)
    return JSONResponse({
        "code": code, "path": path,
        "content_b64": base64.b64encode(blob).decode(),
    })


@skill_files_bp.put("/<code>/files/<path:path>")
@doc_summary("Upload/update one skill file (<= 16 MB)")
@doc_tag("Skill Files")
async def put_skill_file(request: Request, code: str, path: str) -> JSONResponse:
    code = _validate_code_or_400(code)
    if isinstance(code, JSONResponse):
        return code
    cl = _get_clients(request)
    body = request.body or b""
    if len(body) > MAX_FILE_SIZE:
        return _err(
            "VALIDATION_FAILED",
            f"file too large (> {MAX_FILE_SIZE} bytes)",
            status=413,
        )
    try:
        entry = await cl["skill_files"].upload_file(
            code, path, _io.BytesIO(body), len(body),
        )
    except ValueError as e:
        return _err("VALIDATION_FAILED", str(e))
    except Exception as e:
        logger.error("skill_file_upload_error", error=str(e))
        return _err("OBJECT_STORE_UNAVAILABLE", str(e), status=503)
    return JSONResponse({
        "code": code, "path": entry.path,
        "size": entry.size, "etag": entry.etag,
    }, status=201)


@skill_files_bp.delete("/<code>/files/<path:path>")
@doc_summary("Delete one skill file")
@doc_tag("Skill Files")
async def delete_skill_file(request: Request, code: str, path: str) -> JSONResponse:
    code = _validate_code_or_400(code)
    if isinstance(code, JSONResponse):
        return code
    cl = _get_clients(request)
    try:
        await cl["skill_files"].delete_file(code, path)
    except Exception as e:
        logger.error("skill_file_delete_error", error=str(e))
        return _err("OBJECT_STORE_UNAVAILABLE", str(e), status=503)
    return JSONResponse({"success": True, "code": code, "path": path})


@skill_files_bp.post("/<code>/files/batch")
@doc_summary("Batch upload skill files (<= 8 per call)")
@doc_tag("Skill Files")
async def batch_upload(request: Request, code: str) -> JSONResponse:
    code = _validate_code_or_400(code)
    if isinstance(code, JSONResponse):
        return code
    cl = _get_clients(request)
    body = request.json or {}
    files = body.get("files", [])
    if not isinstance(files, list) or not files:
        return _err("VALIDATION_FAILED", "files[] required")
    if len(files) > MAX_BATCH:
        return _err(
            "VALIDATION_FAILED",
            f"too many files (> {MAX_BATCH})",
            status=413,
        )
    results = []
    for item in files:
        path = item.get("path")
        cb64 = item.get("content_b64")
        if not path or not cb64:
            results.append({"path": path, "ok": False,
                            "error": "missing path/content_b64"})
            continue
        try:
            blob = base64.b64decode(cb64)
        except Exception as e:
            results.append({"path": path, "ok": False,
                            "error": f"b64 decode: {e}"})
            continue
        try:
            entry = await cl["skill_files"].upload_file(
                code, path, _io.BytesIO(blob), len(blob),
            )
        except Exception as e:
            results.append({"path": entry.path, "ok": False, "error": str(e)})
            continue
        results.append({"path": entry.path, "ok": True,
                        "size": entry.size, "etag": entry.etag})
    return JSONResponse({"code": code, "results": results})


__all__ = ["skill_files_bp"]
