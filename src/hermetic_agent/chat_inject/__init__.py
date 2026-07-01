"""chat_inject — Hub-side asset resolution + injection layer.

L3 module that hooks into the existing chat_controller flow without
modifying its signatures. Reads ServiceContainer (assets + DB), transforms
into chat_request fields, persists snapshot on Session.
"""

from hermetic_agent.chat_inject.agent_resolver import AgentResolver
from hermetic_agent.chat_inject.asset_renderer import AssetRenderer

__all__ = ["AgentResolver", "AssetRenderer"]
