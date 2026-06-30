"""ScenarioRouter — 6 优先级路由: URL > Header > Body > Keyword > Intent > Default."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import structlog

from hermetic_agent.scenarios.config import ScenarioConfig
from hermetic_agent.scenarios.errors import (
    RoutingFailedError,
    ScenarioDisabledError,
)
from hermetic_agent.scenarios.registry import ScenarioRegistry

logger = structlog.get_logger(__name__)

URL_PATH_RE = re.compile(r"^/agent/scenarios/([^/]+)/chat")


@dataclass
class RoutingContext:
    """路由结果."""

    scenario: ScenarioConfig
    matched_by: str
    candidates: list[ScenarioConfig] = field(default_factory=list)
    rejected: list[tuple[ScenarioConfig, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_name": self.scenario.name,
            "matched_by": self.matched_by,
            "candidate_names": [c.name for c in self.candidates],
            "rejected": [{"name": c.name, "reason": r} for c, r in self.rejected],
        }


def _from_url(path: str) -> str | None:
    m = URL_PATH_RE.match(path or "")
    return m.group(1) if m else None


def _from_header(headers: dict[str, str]) -> str | None:
    return headers.get("X-Scenario") or headers.get("x-scenario")


def _from_body(body: dict[str, Any]) -> str | None:
    n = body.get("scenario")
    return n if isinstance(n, str) and n else None


class ScenarioRouter:
    """按 6 优先级把请求路由到 ScenarioConfig.

    1. URL: /agent/scenarios/{name}/chat
    2. Header: X-Scenario
    3. Body: {"scenario": "name"}
    4. Keyword: trigger_keywords 命中 + priority 升序 + 分数降序
    5. Intent: stub (P3/P4 接 LLM classifier)
    6. Default: settings.default_scenario
    """

    def __init__(
        self,
        registry: ScenarioRegistry,
        default_scenario: str = "_default",
        enable_intent_router: bool = False,
    ) -> None:
        self._registry = registry
        self._default = default_scenario
        self._enable_intent = enable_intent_router
        # keyword 阶段收集的 rejected, 跨阶段保留 (供 default 阶段回填)
        self._last_keyword_rejected: list[tuple[ScenarioConfig, str]] = []

    def route(
        self,
        request_path: str = "",
        headers: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> RoutingContext:
        """按 6 优先级选 scenario."""
        headers = headers or {}
        body = body or {}
        message = str(body.get("message", ""))

        # 显式指定 (URL/header/body) 路径: 直接拿 cfg, 但**仍走一遍 keyword**
        # 阶段以收集 rejected 列表. 这样 4xx 响应能告诉前端"我之前已经
        # 被 keyword 拒过 N 个 scenario 了, 不要再重复建议".
        for label, name in (
            ("url", _from_url(request_path)),
            ("header", _from_header(headers)),
            ("body", _from_body(body)),
        ):
            if name:
                cfg = self._try_get_enabled(name)
                if cfg is not None:
                    # 顺手跑 keyword 收集 rejected (不参与决策)
                    self._route_keyword(message)
                    all_rejected = list(self._last_keyword_rejected)
                    ctx = RoutingContext(
                        scenario=cfg, matched_by=label, candidates=[cfg]
                    )
                    if all_rejected:
                        ctx.rejected = all_rejected
                    return ctx

        ctx = self._route_keyword(message)
        if ctx is not None:
            return ctx
        all_rejected = list(self._last_keyword_rejected)

        if self._route_intent(message) is not None:  # pragma: no cover - stub
            pass  # unreachable in stub

        ctx = self._route_default()
        if ctx is not None:
            ctx.rejected = all_rejected
            return ctx

        available = [c.name for c in self._registry.list_all()]
        raise RoutingFailedError(
            f"Routing failed: no scenario matched (path={request_path!r}, "
            f"message={message[:80]!r}).",
            action=f"Available scenarios: {available}. "
            f"Or set default_scenario to a valid one.",
        )

    def _route_keyword(self, message: str) -> RoutingContext | None:
        if not message:
            self._last_keyword_rejected = []
            return None
        scored: list[tuple[ScenarioConfig, int]] = []
        rejected: list[tuple[ScenarioConfig, str]] = []
        for cfg in self._registry.list_all():
            if not cfg.enabled:
                if cfg.routing.trigger_keywords and any(
                    k in message for k in cfg.routing.trigger_keywords
                ):
                    rejected.append((cfg, "disabled"))
                continue
            kw = cfg.routing.trigger_keywords
            if not kw:
                continue
            score = sum(1 for k in kw if k in message)
            if score > 0:
                scored.append((cfg, score))
        self._last_keyword_rejected = rejected
        if not scored:
            return None
        scored.sort(key=lambda x: (x[0].routing.priority, -x[1]))
        winner = scored[0][0]
        return RoutingContext(
            scenario=winner,
            matched_by="keyword",
            candidates=[c for c, _ in scored],
            rejected=rejected,
        )

    def _route_intent(self, message: str) -> RoutingContext | None:
        if not self._enable_intent or not message:  # pragma: no cover - stub
            return None
        return None  # stub: P3/P4 接 LLM classifier

    def _route_default(self) -> RoutingContext | None:
        cfg = self._registry.get(self._default)
        if cfg is None or not cfg.enabled:
            return None
        return RoutingContext(scenario=cfg, matched_by="default", candidates=[cfg])

    def _try_get_enabled(self, name: str) -> ScenarioConfig | None:
        cfg = self._registry.get(name)
        if cfg is None:
            return None
        if not cfg.enabled:
            raise ScenarioDisabledError(
                f"Scenario {name!r} is disabled",
                action=f"Enable it: PATCH /agent/scenarios/{name} {{enabled: true}}",
            )
        return cfg


__all__ = ["ScenarioRouter", "RoutingContext"]
