"""Audit Logger — L5 Infrastructure Layer.

3 个实现:
  - AuditLogger (ABC)
  - StdoutAuditLogger  (structlog / print)
  - InMemoryAuditLogger  (测试用)

脱敏规则:
  1. **路径**: path 命中 path_check.BLOCKED_PATTERNS → 整个值替换为 `<redacted:env-file>`
     （识别方式: 用 fnmatch + path basename; 类型提示分类: env-file / ssh-key / pem / generic）
  2. **字段**: dict 字段名 (key) 含 password / token / secret → 值替换为 `<redacted>`
"""

from __future__ import annotations

import fnmatch
from abc import ABC, abstractmethod
from collections import deque
from datetime import datetime, timezone
from typing import Any

# 字段名黑名单 (case-insensitive)
_SENSITIVE_KEYS = ("password", "token", "secret", "apikey", "api_key", "auth")


def _classify_blocked(path: str) -> str | None:
    """判断 path 是哪一类敏感文件, 返回分类标签; 不敏感返回 None.

    分类 (与 BLOCKED_PATTERNS 顺序对应):
      - env-file: .env / .env.* / id_rsa / id_ed25519 / id_* / .ssh
      - pem:      *.pem / *.p12
      - ssh-key:  *.key (默认归 key 类)
      - generic:  其他 (secrets/credentials)
    """
    from openagent.policy.path_check import BLOCKED_PATTERNS, _to_posix

    posix = _to_posix(path)
    basename = posix.rsplit("/", 1)[-1]
    for pattern in BLOCKED_PATTERNS:
        matched = fnmatch.fnmatch(posix, pattern) or fnmatch.fnmatch(basename, pattern)
        if not matched:
            continue
        # 分类
        p = pattern.lower()
        if ".env" in p or "id_" in p or ".ssh" in p or "gcloud" in p:
            return "env-file"
        if ".pem" in p or ".p12" in p:
            return "pem"
        if ".key" in p:
            return "ssh-key"
        return "generic"
    return None


def redact_value(key: str, value: Any) -> Any:
    """字段名含敏感词 → 返回 `<redacted>`; 否则原样返回."""
    if isinstance(key, str):
        kl = key.lower()
        for s in _SENSITIVE_KEYS:
            if s in kl:
                return "<redacted>"
    return value


def redact_path(path: str) -> str:
    """path 是凭据类文件 → `<redacted:TYPE>`; 否则原样."""
    cls = _classify_blocked(path)
    if cls is None:
        return path
    return f"<redacted:{cls}>"


def _redact_obj(obj: Any) -> Any:
    """递归脱敏: dict / list / str."""
    if isinstance(obj, dict):
        return {k: _redact_obj(redact_value(k, v)) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        redacted = [_redact_obj(v) for v in obj]
        return type(obj)(redacted) if isinstance(obj, tuple) else redacted
    if isinstance(obj, str):
        return redact_path(obj)
    return obj


class AuditEvent:
    """一条审计事件的不可变快照."""

    __slots__ = ("timestamp", "actor", "action", "target", "result", "context")

    def __init__(
        self,
        actor: str,
        action: str,
        target: str,
        result: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.actor = actor
        self.action = action
        self.target = target
        self.result = result
        self.context = context or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "actor": self.actor,
            "action": self.action,
            "target": redact_path(self.target),
            "result": self.result,
            "context": _redact_obj(self.context),
        }


class AuditLogger(ABC):
    """审计 logger 抽象接口."""

    @abstractmethod
    def log(self, event: AuditEvent) -> None: ...

    def record(
        self,
        actor: str,
        action: str,
        target: str,
        result: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """便捷方法: 构造事件 + 写出."""
        self.log(AuditEvent(actor, action, target, result, context))


class StdoutAuditLogger(AuditLogger):
    """把审计事件写到 stdout (生产用, 配合 structlog / log shipper)."""

    def log(self, event: AuditEvent) -> None:
        import json
        print(json.dumps(event.to_dict(), ensure_ascii=False, default=str))


class InMemoryAuditLogger(AuditLogger):
    """把审计事件存到内存, 测试用.

    保留最近 max_events 条, 老的自动出队.
    """

    def __init__(self, max_events: int = 1000) -> None:
        self._events: deque[AuditEvent] = deque(maxlen=max_events)

    def log(self, event: AuditEvent) -> None:
        self._events.append(event)

    def all(self) -> list[AuditEvent]:
        return list(self._events)

    def clear(self) -> None:
        self._events.clear()


__all__ = [
    "AuditLogger",
    "AuditEvent",
    "StdoutAuditLogger",
    "InMemoryAuditLogger",
    "redact_path",
    "redact_value",
]
