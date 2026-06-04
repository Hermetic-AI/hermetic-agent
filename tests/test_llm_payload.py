"""tests/test_llm_payload.py — LLM 请求体序列化与日志工具单测.

覆盖 4 类:
  * mask_sensitive_text: 屏蔽 MCP_TOKEN / Bearer / token:xxx; None / 无敏感 → 原样
  * build_opencode_payload / build_claude_payload: 字段填充 + 屏蔽
  * log_*: 默认设置下确实发出一条 ``llm_request`` 事件 (INFO 级, 含完整 payload)
  * log_*: settings.log_llm_payload=False 时不发出
  * JSON 序列化往返 (运维/排障场景: 直接 json.dumps(payload) 喂日志)
"""
from __future__ import annotations

import json

import structlog

from openagent.config.settings import Settings
from openagent.providers.llm_payload import (
    _is_enabled,
    build_claude_payload,
    build_opencode_payload,
    log_claude_request,
    log_opencode_request,
    mask_sensitive_text,
)

# ---------------------------------------------------------------------------
# mask_sensitive_text
# ---------------------------------------------------------------------------


def test_mask_mcp_token() -> None:
    text = "MCP_TOKEN: abc123def456"
    assert mask_sensitive_text(text) == "MCP_TOKEN: ***MASKED***"


def test_mask_bearer() -> None:
    text = "Authorization: Bearer eyJhbGc.payload.sig"
    out = mask_sensitive_text(text)
    assert "Bearer ***MASKED***" in out
    assert "eyJhbGc" not in out


def test_mask_token_field() -> None:
    text = "set token: sk-abc123_xyz in header"
    out = mask_sensitive_text(text)
    assert "token: ***MASKED***" in out
    assert "sk-abc123_xyz" not in out


def test_mask_preserves_untouched_text() -> None:
    text = "Hello, please call the flight tool."
    assert mask_sensitive_text(text) == text


def test_mask_handles_none_and_empty() -> None:
    assert mask_sensitive_text(None) is None
    assert mask_sensitive_text("") is None or mask_sensitive_text("") == ""


def test_mask_multiple_in_one_string() -> None:
    text = (
        "first MCP_TOKEN: foo\n"
        "second Bearer bar.baz.qux\n"
        "third token: alpha_beta\n"
    )
    out = mask_sensitive_text(text)
    assert "foo" not in out or "***MASKED***" in out
    assert "bar.baz.qux" not in out
    assert "alpha_beta" not in out


# ---------------------------------------------------------------------------
# build_opencode_payload
# ---------------------------------------------------------------------------


def test_build_opencode_payload_basic() -> None:
    payload = build_opencode_payload(
        session_id="sess-1",
        model_id="claude-sonnet",
        provider_id="opencode",
        parts=[{"type": "text", "text": "hi", "id": "p1"}],
        system="you are a helper",
        tools=None,
        timeout=30.0,
        extra_query={"directory": "/work/proj"},
    )
    assert payload["endpoint"] == "opencode.session.chat"
    assert payload["session_id"] == "sess-1"
    assert payload["model_id"] == "claude-sonnet"
    assert payload["provider_id"] == "opencode"
    assert payload["parts"] == [{"type": "text", "text": "hi", "id": "p1"}]
    assert payload["system"] == "you are a helper"
    assert payload["tools"] is None
    assert payload["timeout"] == 30.0
    assert payload["extra_query"] == {"directory": "/work/proj"}


def test_build_opencode_payload_masks_system() -> None:
    payload = build_opencode_payload(
        session_id="sess-1",
        model_id="m",
        provider_id="opencode",
        parts=[],
        system="prefix\nMCP_TOKEN: SECRET-XYZ\nsuffix",
        tools=None,
        timeout=None,
        extra_query=None,
    )
    assert "SECRET-XYZ" not in payload["system"]
    assert "***MASKED***" in payload["system"]
    # extra_query 为空 dict (None → {})
    assert payload["extra_query"] == {}


def test_build_opencode_payload_json_roundtrip() -> None:
    payload = build_opencode_payload(
        session_id="s1",
        model_id="m",
        provider_id="opencode",
        parts=[{"type": "text", "text": "hi"}],
        system="sys",
        tools=[{"name": "t", "description": "d"}],
        timeout=10.0,
        extra_query={"directory": "/d"},
    )
    # 整个 payload 必须能直接 json.dumps (运维常见操作)
    encoded = json.dumps(payload, ensure_ascii=False)
    decoded = json.loads(encoded)
    assert decoded == payload


# ---------------------------------------------------------------------------
# build_claude_payload
# ---------------------------------------------------------------------------


def test_build_claude_payload_basic() -> None:
    payload = build_claude_payload(
        session_id="sess-2",
        prompt="user prompt",
        options={"model": "claude-opus", "system_prompt": "be helpful"},
    )
    assert payload["endpoint"] == "claude.query"
    assert payload["session_id"] == "sess-2"
    assert payload["prompt"] == "user prompt"
    assert payload["options"]["model"] == "claude-opus"
    assert payload["options"]["system_prompt"] == "be helpful"


def test_build_claude_payload_masks_nested_strings() -> None:
    payload = build_claude_payload(
        session_id="s1",
        prompt="MCP_TOKEN: HIDDEN",
        options={
            "system_prompt": "Bearer abc.def.ghi",
            "metadata": {"auth": "token: top_secret_value"},
            "model": "m",
            "max_tokens": 1024,
        },
    )
    assert "HIDDEN" not in payload["prompt"]
    assert "abc.def.ghi" not in payload["options"]["system_prompt"]
    assert "top_secret_value" not in payload["options"]["metadata"]["auth"]
    # 非 str 值原样透传
    assert payload["options"]["max_tokens"] == 1024


def test_build_claude_payload_options_none() -> None:
    payload = build_claude_payload(session_id="s", prompt="p", options=None)
    assert payload["options"] is None


# ---------------------------------------------------------------------------
# log_opencode_request — happy path / disabled
# ---------------------------------------------------------------------------


def _settings(enabled: bool) -> Settings:
    return Settings(log_llm_payload=enabled)


def test_is_enabled_default() -> None:
    # 不传 → 走 get_settings() (Settings 默认 True)
    assert _is_enabled(None) is True


def test_log_opencode_request_emits() -> None:
    payload = build_opencode_payload(
        session_id="sx",
        model_id="m",
        provider_id="opencode",
        parts=[{"type": "text", "text": "hello"}],
        system="sys",
        tools=None,
        timeout=None,
        extra_query=None,
    )
    with structlog.testing.capture_logs() as cap:
        log_opencode_request(payload, settings=_settings(True))
    ev = next((e for e in cap if e.get("event") == "llm_request"), None)
    assert ev is not None, f"llm_request not found in {cap}"
    assert ev.get("session_id") == "sx"
    assert ev.get("endpoint") == "opencode.session.chat"
    assert ev.get("log_level") == "info"


def test_log_opencode_request_disabled_no_emit() -> None:
    payload = build_opencode_payload(
        session_id="sx",
        model_id="m",
        provider_id="opencode",
        parts=[],
        system=None,
        tools=None,
        timeout=None,
        extra_query=None,
    )
    with structlog.testing.capture_logs() as cap:
        log_opencode_request(payload, settings=_settings(False))
    assert not any(e.get("event") == "llm_request" for e in cap)


def test_log_claude_request_emits() -> None:
    payload = build_claude_payload(
        session_id="sx",
        prompt="hello",
        options={"model": "m"},
    )
    with structlog.testing.capture_logs() as cap:
        log_claude_request(payload, settings=_settings(True))
    ev = next((e for e in cap if e.get("event") == "llm_request"), None)
    assert ev is not None
    assert ev.get("endpoint") == "claude.query"
    assert ev.get("prompt") == "hello"


def test_log_claude_request_disabled_no_emit() -> None:
    payload = build_claude_payload(session_id="sx", prompt="p", options=None)
    with structlog.testing.capture_logs() as cap:
        log_claude_request(payload, settings=_settings(False))
    assert not any(e.get("event") == "llm_request" for e in cap)
