"""Scenarios package — L2 Scenario Orchestration Layer."""

from hermetic_agent.scenarios.config import ScenarioConfig
from hermetic_agent.scenarios.errors import ScenarioError
from hermetic_agent.scenarios.injector import (
    AuditLogger,
    InjectionResult,
    InMemoryAuditLogger,
    ScenarioInjector,
)
from hermetic_agent.scenarios.registry import ScenarioRegistry
from hermetic_agent.scenarios.router import RoutingContext, ScenarioRouter

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
