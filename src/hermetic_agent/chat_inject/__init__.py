"""chat_inject — Hub-side asset resolution + injection layer.

L3 module that hooks into the existing chat_controller flow without
modifying its signatures. Reads ServiceContainer (assets + DB), transforms
into chat_request fields, persists snapshot on Session.
"""

from hermetic_agent.chat_inject.agent_resolver import AgentResolver
from hermetic_agent.chat_inject.asset_renderer import AssetRenderer
from hermetic_agent.chat_inject.injector_adapter import inject_agent_into_chat
from hermetic_agent.chat_inject.overlay_builder import OverlayBuilder
from hermetic_agent.chat_inject.reload_queue import ReloadQueue, ReloadTask
from hermetic_agent.chat_inject.skill_overlay_manager import (
    SkillFingerprint,
    SkillOverlayManager,
)

__all__ = [
    "AgentResolver",
    "AssetRenderer",
    "OverlayBuilder",
    "ReloadQueue",
    "ReloadTask",
    "SkillFingerprint",
    "SkillOverlayManager",
    "inject_agent_into_chat",
]
