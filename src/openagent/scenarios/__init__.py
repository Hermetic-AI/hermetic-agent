"""Scenarios package — L2 Scenario Orchestration Layer."""

from openagent.scenarios.config import ScenarioConfig
from openagent.scenarios.errors import ScenarioError
from openagent.scenarios.injector import (
    AuditLogger,
    InjectionResult,
    InMemoryAuditLogger,
    ScenarioInjector,
)
from openagent.scenarios.registry import ScenarioRegistry
from openagent.scenarios.router import RoutingContext, ScenarioRouter

__all__ = [
    "ScenarioRegistry",
    "ScenarioRouter",
    "ScenarioInjector",
    "RoutingContext",
    "ScenarioConfig",
    "ScenarioError",
    "InjectionResult",
    "InMemoryAuditLogger",
    "AuditLogger",
]
