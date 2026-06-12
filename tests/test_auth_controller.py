"""test_auth_controller.py — Hub 端 feihe 登录代理的核心断言.

策略: monkeypatch `openagent.api.http.controllers.auth_controller.httpx.AsyncClient`
→ _FakeClient. 在 fake 里记录调用的 URL + 返预设 Response, 不真走网络.

为什么不用 sanic test_client + 真 app:
  完整流程需要挂在 `app.config.FALLBACK_ERROR_FORMAT = "json"` 之类的
  全局配置, 跑整套 storage / bridge / pool 初始化, 单测不必要.
  本测试只验 controller 的 3 个核心逻辑:
    1. 真把请求发到 feihe URL (而不是别的)
    2. 真从 feihe response header `token` 抓 token
    3. 4xx 消息含 "验证码" → 设 needs_captcha = true
"""
from __future__ import annotations

import hashlib
import uuid
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from sanic import Sanic

# ---------------------------------------------------------------------------
# fake feihe backend
# ---------------------------------------------------------------------------


def _feihe_response(
    status: int,
    body: dict | None = None,
    headers: dict | None = None,
) -> httpx.Response:
    return httpx.Response(
        status_code=status,
        json=body if body is not None else {},
        headers=headers or {},
        request=httpx.Request("POST", "https://traveldev.feiheair.com/"),
    )


def _feihe_binary_response(
    status: int,
    content: bytes,
    headers: dict | None = None,
) -> httpx.Response:
    return httpx.Response(
        status_code=status,
        content=content,
        headers=headers or {},
        request=httpx.Request("GET", "https://traveldev.feiheair.com/"),
    )


@pytest.fixture
def fake_feihe(monkeypatch):
    """替 httpx.AsyncClient, 让 controller 的网络调用落到 fake 上.

    用 queue 喂预设响应 (httpx.Response 或 Exception).
    暴露 fake.post_calls / fake.get_calls 供测试断言.
    """
    from openagent.api.http.controllers import auth_controller

    fake = MagicMock()
    fake.post_calls = []
    fake.get_calls = []
    fake.responses: list = []  # httpx.Response 或 Exception

    client_instance = MagicMock()

    async def fake_post(url, json=None, headers=None, **kwargs):
        fake.post_calls.append({"url": url, "json": json, "headers": headers})
        if not fake.responses:
            raise RuntimeError("no fake response queued")
        item = fake.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def fake_get(url, headers=None, **kwargs):
        fake.get_calls.append({"url": url, "headers": headers})
        if not fake.responses:
            raise RuntimeError("no fake response queued")
        item = fake.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    client_instance.post = fake_post
    client_instance.get = fake_get
    # async with AsyncClient() as c: → c
    client_instance.__aenter__ = AsyncMock(return_value=client_instance)
    client_instance.__aexit__ = AsyncMock(return_value=None)

    def _async_client_ctor(*args, **kwargs):
        return client_instance

    monkeypatch.setattr(auth_controller.httpx, "AsyncClient", _async_client_ctor)
    return fake


# ---------------------------------------------------------------------------
# 直接调 controller 函数 (绕过 sanic routing). Sanic request 也用 SimpleNamespace.
# ---------------------------------------------------------------------------


def _make_request(json_body: dict | None = None) -> MagicMock:
    """模拟 sanic Request, 但要让 sanic-ext 的 body 装饰器能拿到它.

    sanic-ext 装饰器会从 args/kwargs 里找 Request 实例.
    我们用 spec=Request 让 isinstance() 仍 work, 同时只 mock 控制器用到的属性.
    """
    from sanic.request import Request
    req = MagicMock(spec=Request)
    req.json = json_body
    req.headers = {}
    return req


# ---------------------------------------------------------------------------
# Tests — POST /api/auth/logon
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logon_success_pulls_token_from_feihe_response_header(fake_feihe) -> None:
    """Hub 应从 feihe response header `token` 抓 token (跟抓包一致)."""
    from openagent.api.http.controllers.auth_controller import logon

    fake_feihe.responses.append(
        _feihe_response(
            200,
            body={"success": True, "data": {"userName": "张三"}},
            headers={"token": "feihe-session-abc123"},
        )
    )

    resp = await logon(_make_request({
        "company_code": "10043",
        "user_code": "013",
        "password": "any-password",
    }))

    assert resp.status == 200
    # Sanic JSONResponse 走 .body 拿原始 bytes
    import json
    parsed = json.loads(resp.body)
    assert parsed["success"] is True
    assert parsed["token"] == "feihe-session-abc123"
    assert parsed["login_info"]["userCode"] == "013"
    assert parsed["login_info"]["companyCode"] == "10043"
    assert parsed["login_info"]["displayName"] == "张三"
    assert "loggedInAt" in parsed["login_info"]

    # 验证 Hub 真的调了 feihe logonV2
    assert len(fake_feihe.post_calls) == 1
    call = fake_feihe.post_calls[0]
    assert call["url"] == "https://traveldev.feiheair.com/api/sys/logonV2"
    # Hub 把 snake_case 翻译成 feihe 原始 camelCase + 补 fromType/language/uuid
    assert call["json"] == {
        "companyCode": "10043",
        "userCode": "013",
        "password": hashlib.md5(b"any-password").hexdigest(),
        "uuid": "",
        "fromType": "Browse",
        "captchaId": "",
        "captcha": "",
        "language": "cn",
    }


@pytest.mark.asyncio
async def test_logon_preserves_already_hashed_password(fake_feihe) -> None:
    """前端/调试请求已传 32 位 MD5 时, Hub 不应二次 hash."""
    from openagent.api.http.controllers.auth_controller import logon

    fake_feihe.responses.append(_feihe_response(200, headers={"token": "abc"}))

    await logon(_make_request({
        "company_code": "10043",
        "user_code": "013",
        "password": "441954d29ad2a375cef8ea524a2c7e73",
    }))

    assert fake_feihe.post_calls[0]["json"]["password"] == "441954d29ad2a375cef8ea524a2c7e73"


@pytest.mark.asyncio
async def test_logon_passes_captcha_to_feihe(fake_feihe) -> None:
    """带 captcha 时 Hub 应原样转发到 feihe."""
    from openagent.api.http.controllers.auth_controller import logon

    fake_feihe.responses.append(
        _feihe_response(200, headers={"token": "token-with-captcha"})
    )

    resp = await logon(_make_request({
        "company_code": "10043",
        "user_code": "013",
        "password": "pw",
        "captcha_id": "cap-uuid-1",
        "captcha": "ab12",
    }))

    assert resp.status == 200
    call = fake_feihe.post_calls[0]
    assert call["json"]["captchaId"] == "cap-uuid-1"
    assert call["json"]["captcha"] == "ab12"


@pytest.mark.asyncio
async def test_logon_success_pulls_token_from_feihe_body_data(fake_feihe) -> None:
    """真实 feihe 登录成功把 token 放在 body.data.token."""
    import json

    from openagent.api.http.controllers.auth_controller import logon

    fake_feihe.responses.append(
        _feihe_response(
            200,
            body={
                "errorCode": "0",
                "errorMsg": "",
                "data": {
                    "token": "body-token-123",
                    "userName": "刘酝泽",
                    "userId": 1051526,
                },
            },
        )
    )

    resp = await logon(_make_request({
        "company_code": "10043",
        "user_code": "013",
        "password": "pw",
        "captcha_id": "cap",
        "captcha": "abcd",
    }))

    assert resp.status == 200
    parsed = json.loads(resp.body)
    assert parsed["token"] == "body-token-123"
    assert parsed["login_info"]["displayName"] == "刘酝泽"


@pytest.mark.asyncio
async def test_logon_4xx_returns_message_and_no_captcha(fake_feihe) -> None:
    """feihe 4xx 鉴权失败: Hub 把 message 转给前端, needs_captcha 默认 false."""
    import json

    from openagent.api.http.controllers.auth_controller import logon

    fake_feihe.responses.append(
        _feihe_response(401, body={"code": "1001", "message": "账号或密码错误"})
    )

    resp = await logon(_make_request({
        "company_code": "10043", "user_code": "013", "password": "wrong",
    }))

    assert resp.status == 401
    parsed = json.loads(resp.body)
    assert parsed["success"] is False
    assert parsed["code"] == "LOGON_FAILED"
    assert "账号或密码错误" in parsed["error"]
    assert parsed["needs_captcha"] is False


@pytest.mark.asyncio
async def test_logon_captcha_required_in_message_sets_flag(fake_feihe) -> None:
    """feihe 报错 '请输入验证码' → Hub 设 needs_captcha=true (前端会自动 loadCaptcha)."""
    import json

    from openagent.api.http.controllers.auth_controller import logon

    fake_feihe.responses.append(
        _feihe_response(400, body={"code": "1002", "message": "请先输入图形验证码"})
    )

    resp = await logon(_make_request({
        "company_code": "10043", "user_code": "013", "password": "pw",
    }))

    assert resp.status == 400
    parsed = json.loads(resp.body)
    assert parsed["code"] == "LOGON_FAILED"
    assert parsed["needs_captcha"] is True


@pytest.mark.asyncio
async def test_logon_wrong_captcha_also_marks_needs_captcha(fake_feihe) -> None:
    """用户填了 captcha 但填错 → Hub 也让前端再拉一次."""
    import json

    from openagent.api.http.controllers.auth_controller import logon

    fake_feihe.responses.append(
        _feihe_response(400, body={"code": "1003", "message": "验证码错误"})
    )

    resp = await logon(_make_request({
        "company_code": "10043", "user_code": "013", "password": "pw",
        "captcha_id": "old", "captcha": "wrong",
    }))

    assert resp.status == 400
    parsed = json.loads(resp.body)
    assert parsed["needs_captcha"] is True


@pytest.mark.asyncio
async def test_logon_network_error_returns_502(fake_feihe) -> None:
    """feihe 不可达 → Hub 502, 前端可重试."""
    import json

    from openagent.api.http.controllers.auth_controller import logon

    fake_feihe.responses.append(httpx.ConnectError("connection refused"))

    resp = await logon(_make_request({
        "company_code": "10043", "user_code": "013", "password": "pw",
    }))

    assert resp.status == 502
    parsed = json.loads(resp.body)
    assert parsed["code"] == "FEIHE_UNREACHABLE"


@pytest.mark.asyncio
async def test_logon_timeout_returns_502(fake_feihe) -> None:
    import json

    from openagent.api.http.controllers.auth_controller import logon

    fake_feihe.responses.append(httpx.ReadTimeout("read timeout"))

    resp = await logon(_make_request({
        "company_code": "10043", "user_code": "013", "password": "pw",
    }))

    assert resp.status == 502
    parsed = json.loads(resp.body)
    assert parsed["code"] == "FEIHE_TIMEOUT"


@pytest.mark.asyncio
async def test_logon_2xx_without_token_returns_logical_failure(fake_feihe) -> None:
    """feihe 2xx 但没 token 通常是业务失败, Hub 应转成 400 而不是 502."""
    import json

    from openagent.api.http.controllers.auth_controller import logon

    fake_feihe.responses.append(_feihe_response(200, body={"message": "请输入验证码"}, headers={}))

    resp = await logon(_make_request({
        "company_code": "10043", "user_code": "013", "password": "pw",
    }))

    assert resp.status == 400
    parsed = json.loads(resp.body)
    assert parsed["code"] == "LOGON_FAILED"
    assert parsed["error"] == "请输入验证码"
    assert parsed["needs_captcha"] is True


@pytest.mark.asyncio
async def test_logon_invalid_body_returns_400_and_no_call(fake_feihe) -> None:
    """缺字段 → Hub 400, 不调 feihe (避免无谓流量 + 密码泄露)."""
    import json

    from openagent.api.http.controllers.auth_controller import logon

    resp = await logon(_make_request({"company_code": "10043"}))  # 缺 userCode + password

    assert resp.status == 400
    parsed = json.loads(resp.body)
    assert parsed["code"] == "VALIDATION_FAILED"
    assert fake_feihe.post_calls == []  # 没发 feihe


# ---------------------------------------------------------------------------
# Tests — GET /api/auth/captcha
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_captcha_success(fake_feihe) -> None:
    """Hub 把 feihe captchaId + image 转成 captchaId + imageDataUrl."""
    import json

    from openagent.api.http.controllers.auth_controller import captcha

    fake_feihe.responses.append(
        _feihe_response(
            200,
            body={
                "captchaId": "cap-uuid-1234",
                "image": "data:image/png;base64,iVBORw0KGgo=",
            },
        )
    )

    resp = await captcha(_make_request())

    assert resp.status == 200
    parsed = json.loads(resp.body)
    assert parsed["captchaId"] == "cap-uuid-1234"
    assert parsed["imageDataUrl"] == "data:image/png;base64,iVBORw0KGgo="

    assert len(fake_feihe.get_calls) == 1
    call = fake_feihe.get_calls[0]
    assert call["url"] == "https://traveldev.feiheair.com/api/sys/logon/getGraphicsCaptcha"


@pytest.mark.asyncio
async def test_captcha_success_from_image_response(fake_feihe) -> None:
    """真实 feihe captcha 返回 image/jpeg, captcha id 在 X-Captcha-Id header."""
    import json

    from openagent.api.http.controllers.auth_controller import captcha

    fake_feihe.responses.append(
        _feihe_binary_response(
            200,
            content=b"\xff\xd8jpeg-bytes",
            headers={
                "Content-Type": "image/jpeg",
                "X-Captcha-Id": "cap-header-1",
            },
        )
    )

    resp = await captcha(_make_request())

    assert resp.status == 200
    parsed = json.loads(resp.body)
    assert parsed["captchaId"] == "cap-header-1"
    assert parsed["imageDataUrl"].startswith("data:image/jpeg;base64,")


@pytest.mark.asyncio
async def test_captcha_handles_data_nested_response(fake_feihe) -> None:
    """feihe 老版本把字段包在 data.* 里, Hub 也要能取到."""
    import json

    from openagent.api.http.controllers.auth_controller import captcha

    fake_feihe.responses.append(
        _feihe_response(
            200,
            body={
                "data": {
                    "captchaId": "cap-uuid-5678",
                    "image": "data:image/jpeg;base64,/9j/4AAQ=",
                }
            },
        )
    )

    resp = await captcha(_make_request())

    assert resp.status == 200
    parsed = json.loads(resp.body)
    assert parsed["captchaId"] == "cap-uuid-5678"
    assert "data:image/jpeg" in parsed["imageDataUrl"]


@pytest.mark.asyncio
async def test_captcha_missing_fields_returns_502(fake_feihe) -> None:
    """feihe 响应缺 captchaId / image → Hub 502."""
    import json

    from openagent.api.http.controllers.auth_controller import captcha

    fake_feihe.responses.append(_feihe_response(200, body={"unrelated": "field"}))

    resp = await captcha(_make_request())

    assert resp.status == 502
    parsed = json.loads(resp.body)
    assert parsed["code"] == "FEIHE_CAPTCHA_MISSING_FIELD"


@pytest.mark.asyncio
async def test_captcha_feihe_5xx_returns_502(fake_feihe) -> None:
    import json

    from openagent.api.http.controllers.auth_controller import captcha

    fake_feihe.responses.append(_feihe_response(500, body={"msg": "internal"}))

    resp = await captcha(_make_request())

    assert resp.status == 502
    parsed = json.loads(resp.body)
    assert parsed["code"] == "FEIHE_CAPTCHA_FAILED"


# ---------------------------------------------------------------------------
# 路径校验: 跟 nginx 协同工作, 必须挂在 /auth/* 才有真实 200
# ---------------------------------------------------------------------------


@pytest.fixture
def real_app(monkeypatch):
    """用真 Sanic app 挂 auth_bp, 验路径配置 (跟 nginx proxy_pass 协同)."""
    import openagent.config.settings as settings_mod

    settings_mod.get_settings.cache_clear()
    monkeypatch.setattr(
        "openagent.config.settings.get_settings",
        lambda: settings_mod.Settings(
            feihe_base_url="https://traveldev.feiheair.com",
            feihe_request_timeout=2.0,
        ),
    )

    from openagent.api.http.controllers.auth_controller import auth_bp

    app = Sanic(f"test-auth-route-{uuid.uuid4().hex[:8]}")
    app.blueprint(auth_bp)

    yield app

    # 恢复 get_settings (monkeypatch 自动) + 清 lru_cache
    if hasattr(settings_mod.get_settings, "cache_clear"):
        settings_mod.get_settings.cache_clear()


def test_auth_blueprint_url_prefix_is_nginx_compatible() -> None:
    """Regression: auth_bp url_prefix 必须是 '/auth' (不是 '/api/auth').

    nginx `location /api/ { proxy_pass http://hub:8000/; }` 会把 /api/ 替换
    成 /, 所以 Hub 真实路径去掉 /api/ 前缀. 其它 bp (chat/session) 都用
    /agent /session 这种 "去 /api/" 形式. auth_bp 必须跟齐, 否则 404.
    """
    from openagent.api.http.controllers.auth_controller import auth_bp

    assert auth_bp.url_prefix == "/auth", (
        f"auth_bp.url_prefix 必须是 '/auth' (被 nginx 替换前缀), 实际: {auth_bp.url_prefix!r}. "
        "改错会触发前端 GET /api/auth/captcha → 404."
    )


def test_auth_routes_real_path_no_api_prefix() -> None:
    """验挂在 app 上后, 真实路径是 /auth/logon 跟 /auth/captcha."""
    from openagent.api.http.controllers.auth_controller import auth_bp

    app = Sanic(f"test-routes-{uuid.uuid4().hex[:8]}")
    app.blueprint(auth_bp)

    paths = sorted(f"/{r.path.lstrip('/')}" for r in app.router.routes if hasattr(r, "path"))
    assert "/auth/logon" in paths, f"/auth/logon missing, got {paths}"
    assert "/auth/captcha" in paths, f"/auth/captcha missing, got {paths}"


def test_logon_via_real_app_returns_200(real_app, monkeypatch) -> None:
    """集成: 真 Sanic app + 替 httpx, 验 GET /auth/captcha 跟 POST /auth/logon 真返 200."""
    from openagent.api.http.controllers import auth_controller

    async def fake_get():
        return _feihe_response(200, body={
            "captchaId": "cap-1",
            "image": "data:image/png;base64,xxx",
        })

    async def fake_post(body):
        return _feihe_response(200, headers={"token": "abc"})

    monkeypatch.setattr(auth_controller, "_get_graphics_captcha", fake_get)
    monkeypatch.setattr(auth_controller, "_post_logon_v2", fake_post)

    # 真用 test client 调 (sanic 启独立 server)
    _, resp = real_app.test_client.get("/auth/captcha")
    assert resp.status_code == 200, (
        f"GET /auth/captcha 期望 200, 实际 {resp.status_code}: {resp.text[:200]}"
    )
    body = resp.json
    assert body["captchaId"] == "cap-1"

    _, resp = real_app.test_client.post(
        "/auth/logon",
        json={"company_code": "10043", "user_code": "013", "password": "pw"},
    )
    assert resp.status_code == 200, (
        f"POST /auth/logon 期望 200, 实际 {resp.status_code}: {resp.text[:200]}"
    )
    body = resp.json
    assert body["token"] == "abc"
