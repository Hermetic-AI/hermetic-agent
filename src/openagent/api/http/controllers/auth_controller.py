"""AuthController — Hub 端 feihe 登录代理.

目的:
  让前端**永远不直连** `https://traveldev.feiheair.com` 域名. 原因:
    1. CORS: 浏览器从 openagent-frontend (localhost) 调 traveldev, feihe
       后端不会返 `Access-Control-Allow-Origin: *`, 直接被浏览器 block.
    2. 安全: 登录接口要发 userCode + password + (可能的) captcha. 这些**绝
       不应该**出现在前端 console / Network 里. 走 Hub 代理后, Hub 才是
       唯一接触明文密码的地方, 未来可以加 audit / rate limit / 二次验证.

端点:
  POST /api/auth/logon
    Body: { companyCode, userCode, password, captchaId?, captcha? }
    调 feihe ${feihe_base_url}/api/sys/logonV2, 把 response **header `token`**
    + 解析后的 userName 一起返给前端. 不返密码 / 任何敏感字段.

  GET  /api/auth/captcha
    调 feihe ${feihe_base_url}/api/sys/logon/getGraphicsCaptcha, 返
    { captchaId, imageDataUrl } 给前端 <img src=>.

CORS: 这个 controller 在 Hub 同域, 浏览器 → Hub 走 /api 代理, 不跨域.
      Hub → feihe 是服务端调用, 没有浏览器 CORS 限制.
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, Field
from sanic import Blueprint
from sanic.request import Request
from sanic.response import JSONResponse
from sanic_ext import openapi as sanic_openapi

doc_summary = sanic_openapi.summary
doc_description = sanic_openapi.description
doc_tag = sanic_openapi.tag
operation = sanic_openapi.operation
body = sanic_openapi.body
response = sanic_openapi.response

logger = structlog.get_logger(__name__)

auth_bp = Blueprint("auth", url_prefix="/auth")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class LogonRequest(BaseModel):
    """POST /api/auth/logon 请求体.

    前端只发这 5 个字段, 其它 feihe 后端要的非必填字段 (fromType / language
    / uuid) 在 Hub 侧补齐. 这样前端不必知道 feihe 接口完整 shape.
    """

    company_code: str = Field(..., min_length=1, description="公司代号, e.g. 10043")
    user_code: str = Field(..., min_length=1, description="用户名, e.g. 013")
    password: str = Field(..., min_length=1, description="登录密码 (明文, 仅本次 HTTP 走 TLS)")
    captcha_id: str | None = Field(
        default=None,
        description="图形验证码 id (首次 / 风控触发时由 captcha 端点发)",
    )
    captcha: str | None = Field(default=None, description="图形验证码值")


class LogonSuccessResponse(BaseModel):
    success: bool = True
    token: str = Field(..., description="feihe 后端 session token (response header `token`)")
    login_info: dict[str, Any] = Field(
        default_factory=dict,
        description="辅助信息 (userCode / companyCode / displayName / loggedInAt)",
    )


class ErrorBody(BaseModel):
    success: bool = False
    code: str
    error: str
    # 偶发场景: feihe 后端说要验证码, 但前端没带. 让前端知道要重拉 captcha.
    needs_captcha: bool = False


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _feihe_base() -> str:
    """读 settings.feihe_base_url. 失败兜底用默认 dev URL."""
    try:
        from openagent.config.settings import get_settings

        return get_settings().feihe_base_url.rstrip("/")
    except Exception:  # pragma: no cover
        return os.environ.get("FEIHE_BASE_URL", "https://traveldev.feiheair.com").rstrip("/")


def _feihe_timeout() -> float:
    try:
        from openagent.config.settings import get_settings

        return get_settings().feihe_request_timeout
    except Exception:  # pragma: no cover
        return float(os.environ.get("FEIHE_REQUEST_TIMEOUT", "10"))


def _feihe_origin_header() -> dict[str, str]:
    """feihe 后端要求 Origin / Referer 跟 Origin 域一致. 实际我们是从
    Hub 服务端调, 没有真正的 browser origin, 但 feihe 检查不严,
    给它写 Origin 域兜住 (跟抓包时浏览器发的对齐). Origin 域从
    settings.feihe_origin_url 读 (默认 https://crmdev.feiheair.com)."""
    try:
        from openagent.config.settings import get_settings
        origin = get_settings().feihe_origin_url.rstrip("/")
    except Exception:  # pragma: no cover
        origin = "https://crmdev.feiheair.com"
    return {
        "Origin": origin,
        "Referer": f"{origin}/",
        "Accept": "application/json, text/plain, */*",
    }


def _json_or_none(resp: httpx.Response) -> dict[str, Any] | None:
    try:
        data = resp.json()
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _response_message(data: dict[str, Any] | None) -> str:
    if not data:
        return ""
    msg = data.get("message") or data.get("msg") or data.get("error") or ""
    return msg.strip() if isinstance(msg, str) else ""


def _message_needs_captcha(message: str) -> bool:
    text = message.lower()
    return "验证码" in message or "captcha" in text


def _feihe_password_value(password: str) -> str:
    """Return the password format expected by feihe logonV2.

    Browser traffic sends a 32-char lowercase MD5 hex string. If the caller
    already provided that shape, keep it unchanged so retry/debug calls do not
    get double-hashed.
    """
    value = password.strip()
    if re.fullmatch(r"[0-9a-fA-F]{32}", value):
        return value.lower()
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def _safe_log_dict(d: dict[str, Any] | None) -> dict[str, Any]:
    """返回 dict 的"安全日志视图": 敏感字段名替换为 ``"<redacted,len=N>"``.

    用于把 HTTP body / form dict 落到日志前的统一脱敏. 仅做**键名匹配**,
    字段名包含 password / token / secret / captcha / phone / idCard / ssn
    等敏感词的全部 redact.
    """
    if not d:
        return {}
    sensitive_keys = (
        "password", "token", "secret", "apikey", "api_key", "auth",
        "captcha", "phone", "idcard", "ssn",
    )
    out: dict[str, Any] = {}
    for k, v in d.items():
        kl = k.lower()
        if any(s in kl for s in sensitive_keys):
            if isinstance(v, str):
                out[k] = f"<redacted,len={len(v)}>"
            else:
                out[k] = "<redacted>"
        else:
            out[k] = v
    return out


def _find_token(value: Any) -> str:
    """递归从 dict/list 中找 token 字符串 (不记原文到日志)."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in {"token", "accesstoken", "access_token"} and isinstance(item, str):
                logger.info(
                    "feihe_logon_token_parse_hit",
                    source=f"json_key:{key}",
                    token_len=len(item.strip()),
                )
                return item.strip()
        for item in value.values():
            token = _find_token(item)
            if token:
                return token
    if isinstance(value, list):
        for item in value:
            token = _find_token(item)
            if token:
                return token
    return ""


def _token_from_response(resp: httpx.Response, data: dict[str, Any] | None) -> str:
    """从 feihe 响应中抽取 token, 全部路径都**只记 token 长度**不记原文.

    合规要求: token / password / 验证码 任何一种都不能进 structlog 日志
    (生产是 Loki/ELK, 落盘即合规事故). 排查时靠 `token_len` + 状态码 + 来源
    三个字段足以定位问题, 不需要原文.
    """
    # 1. response header `token`
    token = (resp.headers.get("token") or resp.headers.get("Token") or "").strip()
    if token:
        logger.info(
            "feihe_logon_token_parse_hit",
            source="response_header:token",
            token_len=len(token),
        )
        return token
    # 2. JSON body 递归
    token = _find_token(data)
    if token:
        return token
    # 3. response text regex (兜底)
    match = re.search(r'"(?:token|accessToken|access_token)"\s*:\s*"([^"]+)"', resp.text)
    if match:
        token = match.group(1).strip()
        logger.info(
            "feihe_logon_token_parse_hit",
            source="response_text_regex",
            token_len=len(token),
        )
        return token
    # 4. miss — 记状态/类型/keys, **不记 response text 全文** (可能含密码错提示)
    logger.info(
        "feihe_logon_token_parse_miss",
        status=resp.status_code,
        content_type=resp.headers.get("content-type", ""),
        json_top_keys=list(data.keys()) if isinstance(data, dict) else [],
        response_text_len=len(resp.text or ""),
    )
    return ""


async def _post_logon_v2(body: dict[str, Any]) -> httpx.Response:
    """发 logonV2, 不解释响应. 由 caller 处理 status / header / body."""
    async with httpx.AsyncClient(timeout=_feihe_timeout()) as client:
        return await client.post(
            f"{_feihe_base()}/api/sys/logonV2",
            json=body,
            headers={
                **_feihe_origin_header(),
                "Content-Type": "application/json",
            },
        )


async def _get_graphics_captcha() -> httpx.Response:
    async with httpx.AsyncClient(timeout=_feihe_timeout()) as client:
        return await client.get(
            f"{_feihe_base()}/api/sys/logon/getGraphicsCaptcha",
            headers=_feihe_origin_header(),
        )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@auth_bp.post("/logon")
@doc_summary("代理 feihe 正式系统登录 (POST /api/sys/logonV2)")
@doc_description(
    "前端发账号 + 密码 (Hub 代为调 traveldev.feiheair.com/api/sys/logonV2), "
    "成功时把 feihe response header `token` 跟 userName 一起返. 失败时把 "
    "feihe 的 message + 4xx/5xx 转成统一结构.\n\n"
    "**安全**: 密码仅在本次 HTTPS 请求里出现, 不进日志, 不进响应."
)
@doc_tag("Auth")
@operation("logonV2")
@body(LogonRequest)
@response(200, LogonSuccessResponse, description="登录成功, 返 token + loginInfo")
@response(400, ErrorBody, description="参数缺失 / 验证码缺失")
@response(401, ErrorBody, description="feihe 后端鉴权失败 (密码错 / 账号停用)")
@response(502, ErrorBody, description="feihe 后端不可达 / 超时")
async def logon(request: Request) -> JSONResponse:
    """Handle POST /api/auth/logon."""
    try:
        payload = LogonRequest(**(request.json or {}))
    except Exception as e:
        return JSONResponse(
            ErrorBody(
                code="VALIDATION_FAILED", error=f"invalid logon body: {e}"
            ).model_dump(),
            status=400,
        )

    # 不打印 password (哪怕 debug). 仅记 userCode 跟 captcha 是否带.
    logger.info(
        "feihe_logon_attempt",
        company_code=payload.company_code,
        user_code=payload.user_code,
        has_captcha=bool(payload.captcha_id and payload.captcha),
    )

    feihe_body = {
        "companyCode": payload.company_code,
        "userCode": payload.user_code,
        "password": _feihe_password_value(payload.password),
        "uuid": "",
        "fromType": "Browse",
        "captchaId": payload.captcha_id or "",
        "captcha": payload.captcha or "",
        "language": "cn",
    }

    try:
        feihe_resp = await _post_logon_v2(feihe_body)
        # 合规: 响应 body 可能含密码错提示/部分手机号/错误堆栈, **不原文落日志**.
        # 仅记状态码 + content-type + body 长度, 排查时按需重放 (debug 级别).
        logger.info(
            "feihe_logon_response_received",
            status=feihe_resp.status_code,
            content_type=feihe_resp.headers.get("content-type", ""),
            body_len=len(feihe_resp.text or ""),
        )
    except httpx.TimeoutException:
        logger.warning("feihe_logon_timeout", timeout=_feihe_timeout())
        return JSONResponse(
            ErrorBody(
                code="FEIHE_TIMEOUT",
                error="feihe login timeout (Hub → traveldev.feiheair.com)",
            ).model_dump(),
            status=502,
        )
    except httpx.HTTPError as e:
        logger.warning("feihe_logon_network_error", error=str(e))
        return JSONResponse(
            ErrorBody(
                code="FEIHE_UNREACHABLE",
                error=f"Hub → feihe network error: {e}",
            ).model_dump(),
            status=502,
        )

    # feihe 后端非 2xx: 解析 body 拿 message (用户密码错 / 验证码错 / 账号锁定)
    if not (200 <= feihe_resp.status_code < 300):
        detail_msg = ""
        detail_msg = _response_message(_json_or_none(feihe_resp))
        if not detail_msg:
            detail_msg = f"feihe logon failed (HTTP {feihe_resp.status_code})"

        # 验证码相关: feihe 4xx 经常是 "请输入验证码" / "验证码错误"
        needs_captcha = bool(payload.captcha_id and _message_needs_captcha(detail_msg))
        # 兜底: 没带验证码但被风控挡了, 也提示前端要拉
        if not payload.captcha_id and _message_needs_captcha(detail_msg):
            needs_captcha = True

        logger.info(
            "feihe_logon_failed",
            user_code=payload.user_code,
            status=feihe_resp.status_code,
            needs_captcha=needs_captcha,
            detail=detail_msg[:120],
        )
        # 401/403 鉴权错; 4xx 其他当 400
        status = (
            401
            if feihe_resp.status_code in (401, 403)
            else 400
            if feihe_resp.status_code < 500
            else 502
        )
        return JSONResponse(
            ErrorBody(
                code="LOGON_FAILED",
                error=detail_msg,
                needs_captcha=needs_captcha,
            ).model_dump(),
            status=status,
        )

    # 2xx: 抓 response header `token` (跟抓包一致)
    j = _json_or_none(feihe_resp)
    token = _token_from_response(feihe_resp, j)
    if not token:
        detail_msg = _response_message(j)
        needs_captcha = _message_needs_captcha(detail_msg) or not payload.captcha_id
        if not detail_msg:
            detail_msg = (
                "登录未返回 token，请输入验证码后重试"
                if needs_captcha
                else "登录未返回 token，请检查账号、密码或验证码"
            )
        logger.info(
            "feihe_logon_no_token",
            status=feihe_resp.status_code,
            needs_captcha=needs_captcha,
            detail=detail_msg[:120],
        )
        return JSONResponse(
            ErrorBody(
                code="LOGON_FAILED",
                error=detail_msg,
                needs_captcha=needs_captcha,
            ).model_dump(),
            status=400,
        )

    # 抓 userName (非敏感, 用来顶栏展示)
    display_name: str | None = None
    try:
        if isinstance(j, dict):
            data = j.get("data") if isinstance(j.get("data"), dict) else j
            display_name = (
                data.get("userName")
                or data.get("username")
                or data.get("name")
            )
            if isinstance(display_name, str):
                display_name = display_name.strip() or None
    except Exception:
        # body 不是 JSON 也无所谓, token 已经拿到
        pass

    from datetime import datetime, timezone

    login_info = {
        "userCode": payload.user_code,
        "companyCode": payload.company_code,
        "displayName": display_name,
        "loggedInAt": datetime.now(timezone.utc).isoformat(),
    }
    logger.info(
        "feihe_logon_ok",
        user_code=payload.user_code,
        token_len=len(token),
        display_name=display_name or "",
    )
    return JSONResponse(
        LogonSuccessResponse(token=token, login_info=login_info).model_dump(),
        status=200,
    )


@auth_bp.get("/captcha")
@doc_summary("代理 feihe 图形验证码 (GET /api/sys/logon/getGraphicsCaptcha)")
@doc_description(
    "返 { captchaId, imageDataUrl } 给前端 <img src=...>. 容错处理 feihe 后端"
    "实际响应里 image / captchaId 可能在 data.* 里."
)
@doc_tag("Auth")
@operation("feiheGraphicsCaptcha")
@response(200, {"captchaId": str, "imageDataUrl": str})
@response(502, ErrorBody, description="feihe 不可达 / 响应缺字段")
async def captcha(request: Request) -> JSONResponse:
    """Handle GET /api/auth/captcha."""
    try:
        feihe_resp = await _get_graphics_captcha()
    except httpx.TimeoutException:
        return JSONResponse(
            ErrorBody(
                code="FEIHE_TIMEOUT",
                error="feihe captcha timeout",
            ).model_dump(),
            status=502,
        )
    except httpx.HTTPError as e:
        return JSONResponse(
            ErrorBody(
                code="FEIHE_UNREACHABLE",
                error=f"Hub → feihe network error: {e}",
            ).model_dump(),
            status=502,
        )
    if not (200 <= feihe_resp.status_code < 300):
        return JSONResponse(
            ErrorBody(
                code="FEIHE_CAPTCHA_FAILED",
                error=f"feihe captcha failed (HTTP {feihe_resp.status_code})",
            ).model_dump(),
            status=502,
        )

    content_type = feihe_resp.headers.get("content-type", "").split(";")[0].lower()
    if content_type.startswith("image/"):
        captcha_id = (
            feihe_resp.headers.get("X-Captcha-Id")
            or feihe_resp.headers.get("x-captcha-id")
            or ""
        ).strip()
        if not captcha_id:
            return JSONResponse(
                ErrorBody(
                    code="FEIHE_CAPTCHA_MISSING_FIELD",
                    error="feihe image captcha response missing X-Captcha-Id header",
                ).model_dump(),
                status=502,
            )
        encoded = base64.b64encode(feihe_resp.content).decode("ascii")
        return JSONResponse(
            {"captchaId": captcha_id, "imageDataUrl": f"data:{content_type};base64,{encoded}"},
            status=200,
        )

    try:
        j = feihe_resp.json()
    except Exception:
        return JSONResponse(
            ErrorBody(
                code="FEIHE_CAPTCHA_BAD_JSON",
                error="feihe captcha response is not JSON",
            ).model_dump(),
            status=502,
        )

    # feihe 字段可能在顶层 / data.* 里, 容错
    captcha_id = (j or {}).get("captchaId") or (j or {}).get("data", {}).get("captchaId") or ""
    image = (j or {}).get("image") or (j or {}).get("data", {}).get("image") or ""
    if not captcha_id or not image:
        return JSONResponse(
            ErrorBody(
                code="FEIHE_CAPTCHA_MISSING_FIELD",
                error="feihe captcha response missing captchaId / image",
            ).model_dump(),
            status=502,
        )
    return JSONResponse(
        {"captchaId": captcha_id, "imageDataUrl": image},
        status=200,
    )
