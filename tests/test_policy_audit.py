"""audit 模块单测."""

from __future__ import annotations

import io
import json
import sys

import pytest

from hermetic_agent.policy.audit import (
    AuditEvent,
    AuditLogger,
    InMemoryAuditLogger,
    StdoutAuditLogger,
    redact_path,
    redact_value,
)


def test_audit_redacts_env_file() -> None:
    assert redact_path("/work/proj/.env") == "<redacted:env-file>"
    assert redact_path("/work/proj/.env.production") == "<redacted:env-file>"


def test_audit_redacts_ssh_key() -> None:
    assert redact_path("/home/u/.ssh/id_rsa") == "<redacted:env-file>"
    assert redact_path("/home/u/.ssh/id_ed25519") == "<redacted:env-file>"


def test_audit_redacts_pem() -> None:
    assert redact_path("/work/cert.pem") == "<redacted:pem>"


def test_audit_redacts_key() -> None:
    assert redact_path("/work/cert.key") == "<redacted:ssh-key>"


def test_audit_does_not_redact_normal_paths() -> None:
    assert redact_path("/work/proj/src/main.py") == "/work/proj/src/main.py"
    assert redact_path("/tmp/scratch.txt") == "/tmp/scratch.txt"


def test_audit_redacts_password_field() -> None:
    assert redact_value("password", "hunter2") == "<redacted>"
    assert redact_value("Password", "x") == "<redacted>"
    assert redact_value("user_password", "x") == "<redacted>"


def test_audit_redacts_token_field() -> None:
    assert redact_value("api_token", "abc") == "<redacted>"
    assert redact_value("accessToken", "abc") == "<redacted>"


def test_audit_redacts_secret_field() -> None:
    assert redact_value("client_secret", "x") == "<redacted>"


def test_audit_does_not_redact_safe_field() -> None:
    assert redact_value("username", "alice") == "alice"
    assert redact_value("email", "a@b.c") == "a@b.c"


def test_audit_redacts_nested_dict() -> None:
    event = {
        "username": "alice",
        "password": "hunter2",
        "config": {"api_key": "sk-xxx", "host": "example.com"},
    }
    from hermetic_agent.policy.audit import _redact_obj
    redacted = _redact_obj(event)
    assert redacted["username"] == "alice"
    assert redacted["password"] == "<redacted>"
    assert redacted["config"]["api_key"] == "<redacted>"
    assert redacted["config"]["host"] == "example.com"


def test_audit_redacts_list_of_strings() -> None:
    paths = ["/work/proj/.env", "/work/proj/README.md"]
    from hermetic_agent.policy.audit import _redact_obj
    redacted = _redact_obj(paths)
    assert redacted[0] == "<redacted:env-file>"
    assert redacted[1] == "/work/proj/README.md"


def test_audit_in_memory_records() -> None:
    logger = InMemoryAuditLogger()
    logger.record("a", "act", "/etc/passwd", "denied")
    logger.record("a", "act", "/work/x", "allowed")
    events = logger.all()
    assert len(events) == 2
    assert events[0].actor == "a"
    assert events[0].result == "denied"


def test_audit_in_memory_max_events() -> None:
    logger = InMemoryAuditLogger(max_events=3)
    for i in range(10):
        logger.record("a", "act", f"/path/{i}", "ok")
    assert len(logger.all()) == 3


def test_audit_in_memory_clear() -> None:
    logger = InMemoryAuditLogger()
    logger.record("a", "act", "/x", "ok")
    logger.clear()
    assert logger.all() == []


def test_audit_event_to_dict_redacts() -> None:
    event = AuditEvent(
        actor="agent-1",
        action="path_check",
        target="/work/.env",
        result="denied",
        context={"password": "secret"},
    )
    d = event.to_dict()
    assert d["target"] == "<redacted:env-file>"
    assert d["context"]["password"] == "<redacted>"
    assert d["actor"] == "agent-1"
    assert "timestamp" in d


def test_audit_stdout_logger(capsys: pytest.CaptureFixture[str]) -> None:
    logger = StdoutAuditLogger()
    logger.record("a", "act", "/work/x", "ok", {"k": "v"})
    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip())
    assert payload["actor"] == "a"
    assert payload["action"] == "act"
    assert payload["result"] == "ok"


def test_audit_logger_is_abstract() -> None:
    """AuditLogger 是 ABC, 不能直接实例化."""
    with pytest.raises(TypeError):
        AuditLogger()  # type: ignore[abstract]
