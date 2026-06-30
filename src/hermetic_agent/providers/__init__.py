"""Provider 包——Agent 后端适配层的统一入口。

提供：
- 抽象接口与数据模型（``AgentProvider``、``ChatMessage``、``ChatResult``、
  ``SessionInfo``、``AgentConfig``、``ToolCall``、``SDKType``）。
- 双 SDK 适配器（``OpenCodeAdapter``、``ClaudeCodeAdapter``）及其底层
  生命周期 / 对话分拆模块。
- ``AgentBridge`` 统一代理——按 AgentConfig.sdk_type 路由到对应适配器。

上层模块（API 路由、调度器等）只需面向 ``AgentBridge`` 与数据模型编程，
无需关心具体 SDK 差异。
"""

from hermetic_agent.providers.agent_bridge import AgentBridge
from hermetic_agent.providers.base import (
    AgentConfig,
    AgentProvider,
    ChatMessage,
    ChatResult,
    SDKType,
    SessionInfo,
    ToolCall,
)
from hermetic_agent.providers.claude_code.adapter import ClaudeCodeAdapter
from hermetic_agent.providers.opencode.adapter import OpenCodeAdapter

__all__ = [
    "AgentProvider",
    "SDKType",
    "ChatMessage",
    "ChatResult",
    "SessionInfo",
    "AgentConfig",
    "ToolCall",
    "OpenCodeAdapter",
    "ClaudeCodeAdapter",
    "AgentBridge",
]
