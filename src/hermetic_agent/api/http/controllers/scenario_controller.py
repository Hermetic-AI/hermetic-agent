"""ScenarioController — /agent/scenarios/*  CRUD 端点 (5 核心 + 4 stub).

P6 阶段实现:
  1. GET    /agent/scenarios/                   列出全部
  2. GET    /agent/scenarios/<name>             单个查询
  3. POST   /agent/scenarios/                   注册/覆盖
  4. DELETE /agent/scenarios/<name>             注销
  5. POST   /agent/scenarios/reload             重载 (走 settings.scenario_paths)
  6. GET    /agent/scenarios/<name>/validate    校验 schema + 资源
  7. POST   /agent/scenarios/<name>/chat        (stub) 复用 chat_controller 逻辑
  8. POST   /agent/scenarios/<name>/chat/stream (stub) 复用 chat_controller 逻辑
  9. GET    /agent/scenarios/routing-log        (stub) 导出 routing 历史
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
from sanic import Blueprint
from sanic.request import Request
from sanic.response import JSONResponse
from sanic_ext import openapi as sanic_openapi

from hermetic_agent.api.lifecycle.scenario_lifecycle import find_project_root
from hermetic_agent.api.lifecycle.scenario_models import (
    RegisterScenarioRequest,
    ScenarioDeleteResponse,
    ScenarioGetResponse,
    ScenarioListResponse,
    ScenarioRegisterResponse,
    ScenarioReloadResponse,
    ScenarioRoutingLogResponse,
    ScenarioValidateResponse,
)
from hermetic_agent.scenarios.config import ScenarioConfig
from hermetic_agent.scenarios.errors import (
    ScenarioResourceError,
)
from hermetic_agent.scenarios.registry import ScenarioRegistry

logger = structlog.get_logger(__name__)

doc_summary = sanic_openapi.summary
doc_description = sanic_openapi.description
doc_tag = sanic_openapi.tag
operation = sanic_openapi.operation
response = sanic_openapi.response
body = sanic_openapi.body

scenario_bp = Blueprint("agent_scenarios", url_prefix="/agent/scenarios")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_registry(request: Request) -> ScenarioRegistry:
    return request.app.ctx.scenario_registry


def _get_router(request: Request):
    return request.app.ctx.scenario_router


def _get_injector(request: Request):
    return request.app.ctx.scenario_injector


def _scenario_to_dict(cfg: ScenarioConfig) -> dict[str, Any]:
    """ScenarioConfig → JSON 友好的 dict (mode=json 把 datetime 等转字符串)."""
    return cfg.model_dump(mode="json")


def _err(code: str, message: str, action: str | None = None, status: int = 400):
    return JSONResponse(
        {
            "success": False,
            "code": code,
            "error": message,
            "action": action,
        },
        status=status,
    )


# ---------------------------------------------------------------------------
# 1. 列出所有 scenario
# ---------------------------------------------------------------------------


@scenario_bp.get("/")
@doc_summary("列出所有 scenario")
@doc_description("返回当前注册表里的全部 scenario (按 name 排序).")
@doc_tag("Scenarios")
@operation("listScenarios")
@response(200, ScenarioListResponse)
async def list_scenarios(request: Request) -> JSONResponse:
    """GET /agent/scenarios/ — 列出所有 scenario."""
    registry = _get_registry(request)
    scenarios = registry.list_all()
    return JSONResponse(
        ScenarioListResponse(
            total=len(scenarios),
            scenarios=[_scenario_to_dict(s) for s in scenarios],
        ).model_dump()
    )


# ---------------------------------------------------------------------------
# 2. 查询单个 scenario
# ---------------------------------------------------------------------------


@scenario_bp.get("/<name>")
@doc_summary("查询单个 scenario")
@doc_description("按 name 查找 scenario; 不存在返回 404 + 候选列表.")
@doc_tag("Scenarios")
@operation("getScenario")
@response(200, ScenarioGetResponse)
async def get_scenario(request: Request, name: str) -> JSONResponse:
    """GET /agent/scenarios/<name>."""
    registry = _get_registry(request)
    cfg = registry.get(name)
    if cfg is None:
        return JSONResponse(
            ScenarioGetResponse(
                success=False,
                code="SCENARIO_NOT_FOUND",
                error=f"Scenario {name!r} not found",
                available=registry.list_names(),
            ).model_dump(),
            status=404,
        )
    return JSONResponse(
        ScenarioGetResponse(scenario=_scenario_to_dict(cfg)).model_dump()
    )


# ---------------------------------------------------------------------------
# 3. 注册/覆盖 scenario
# ---------------------------------------------------------------------------


@scenario_bp.post("/")
@doc_summary("注册/覆盖一个 scenario")
@doc_description(
    "Body 是完整 scenario config dict; 顶层必填 name + version.\n\n"
    "成功 → 201 + 完整 scenario 序列化; 校验失败 → 400 + code."
)
@doc_tag("Scenarios")
@operation("registerScenario")
@body(RegisterScenarioRequest)
@response(201, ScenarioRegisterResponse)
@response(400, ScenarioRegisterResponse, description="schema/资源校验失败")
async def register_scenario(request: Request) -> JSONResponse:
    """POST /agent/scenarios/."""
    registry = _get_registry(request)
    body = request.json or {}
    try:
        RegisterScenarioRequest(**body)
    except Exception as e:
        return _err("VALIDATION_FAILED", f"Invalid request body: {e}")

    # 用 loader.load_scenario 解析 — 但因为 body 已经是 dict, 直接 pydantic 校验
    try:
        # 从 body 移除我们知道的 envelope (顶层), 其余字段直接喂给 ScenarioConfig
        cfg = ScenarioConfig.model_validate(body)
    except Exception as e:
        return _err(
            "SCENARIO_VALIDATION_FAILED",
            f"Schema validation failed: {e}",
            action="Fix the fields listed; ensure name pattern / version / required blocks.",
        )

    # 同步做一次物理资源校验 (仿 load_scenario)
    try:
        from hermetic_agent.scenarios.loader import _validate_resources  # type: ignore
        _validate_resources(cfg)
    except ScenarioResourceError as e:
        return _err(
            e.code,
            str(e),
            action=getattr(e, "action", None),
        )

    registry.register(cfg, override=True)
    logger.info("scenario_registered_via_api", name=cfg.name)
    return JSONResponse(
        ScenarioRegisterResponse(scenario=_scenario_to_dict(cfg)).model_dump(),
        status=201,
    )


# ---------------------------------------------------------------------------
# 4. 注销 scenario
# ---------------------------------------------------------------------------


@scenario_bp.delete("/<name>")
@doc_summary("注销一个 scenario")
@doc_description("从注册表里删除; 不存在返回 404.")
@doc_tag("Scenarios")
@operation("deleteScenario")
@response(200, ScenarioDeleteResponse)
@response(404, ScenarioDeleteResponse)
async def delete_scenario(request: Request, name: str) -> JSONResponse:
    """DELETE /agent/scenarios/<name>."""
    registry = _get_registry(request)
    ok = registry.unregister(name)
    if not ok:
        return JSONResponse(
            ScenarioDeleteResponse(
                success=False,
                code="SCENARIO_NOT_FOUND",
                error=f"Scenario {name!r} not found",
            ).model_dump(),
            status=404,
        )
    logger.info("scenario_deleted_via_api", name=name)
    return JSONResponse(ScenarioDeleteResponse(name=name).model_dump())


# ---------------------------------------------------------------------------
# 5. 重载 (从 settings.scenario_paths 重新读)
# ---------------------------------------------------------------------------


@scenario_bp.post("/reload")
@doc_summary("重载所有 scenario")
@doc_description("清空当前注册表, 重新从 settings.scenario_paths 加载.")
@doc_tag("Scenarios")
@operation("reloadScenarios")
@response(200, ScenarioReloadResponse)
async def reload_scenarios(request: Request) -> JSONResponse:
    """POST /agent/scenarios/reload."""
    registry = _get_registry(request)
    settings = request.app.ctx.settings
    paths = list(getattr(settings, "scenario_paths", []) or [])
    # 兼容老 app 没设 settings 的情况
    if not paths:
        work_root = getattr(settings, "work_root", "work")
        paths = [work_root + "/scenarios"]
    # 与 init_scenarios 一致: 相对路径锚到项目根(走 pyproject.toml 向上找,
    # 不依赖启动 cwd — 修 2026-06-03 reload 返回 0 的 bug)
    project_root = find_project_root()
    resolved_paths: list[str] = []
    for p in paths:
        pp = Path(p)
        if not pp.is_absolute():
            pp = project_root / pp
        if pp.exists():
            resolved_paths.append(str(pp))
        else:
            logger.warning(
                "scenario_path_not_found_in_reload",
                path=str(pp),
                project_root=str(project_root),
            )
    loaded = registry.reload(*resolved_paths) if resolved_paths else []
    logger.info(
        "scenarios_reloaded",
        count=len(loaded),
        requested=paths,
        resolved=resolved_paths,
        project_root=str(project_root),
    )
    return JSONResponse(
        ScenarioReloadResponse(
            loaded=len(loaded),
            scenarios=registry.list_names(),
        ).model_dump()
    )


# ---------------------------------------------------------------------------
# 6. 校验 (不注册) — 复用 load_scenario
# ---------------------------------------------------------------------------


@scenario_bp.get("/<name>/validate")
@doc_summary("校验一个 scenario (不注册)")
@doc_description("通过 name 找已注册的 scenario, 跑资源 + 物理路径校验.")
@doc_tag("Scenarios")
@operation("validateScenario")
@response(200, ScenarioValidateResponse)
async def validate_scenario(request: Request, name: str) -> JSONResponse:
    """GET /agent/scenarios/<name>/validate."""
    registry = _get_registry(request)
    cfg = registry.get(name)
    if cfg is None:
        return JSONResponse(
            ScenarioValidateResponse(
                success=True,
                valid=False,
                name=name,
                errors=[f"Scenario {name!r} not found"],
            ).model_dump(),
            status=200,
        )
    # 资源校验 — 已在 load_scenario 阶段过 schema 校验, 这里只看物理路径
    errors: list[str] = []
    warnings: list[str] = []
    try:
        from hermetic_agent.scenarios.loader import _validate_resources  # type: ignore
        _validate_resources(cfg)
    except ScenarioResourceError as e:
        for m in e.missing:
            errors.append(f"resource missing: {m}")
    return JSONResponse(
        ScenarioValidateResponse(
            valid=not errors,
            name=name,
            errors=errors,
            warnings=warnings,
        ).model_dump()
    )


# ---------------------------------------------------------------------------
# 9. routing-log  (stub)
# ---------------------------------------------------------------------------


@scenario_bp.get("/routing-log")
@doc_summary("导出 routing 历史 (stub)")
@doc_description("P6 阶段 stub. P7 阶段会接 router 的 routing_log.")
@doc_tag("Scenarios")
@operation("routingLog")
async def routing_log(request: Request) -> JSONResponse:
    """GET /agent/scenarios/routing-log — stub."""
    registry = _get_registry(request)
    log = registry.get_routing_log()
    return JSONResponse(ScenarioRoutingLogResponse(log=log).model_dump())


__all__ = ["scenario_bp"]
