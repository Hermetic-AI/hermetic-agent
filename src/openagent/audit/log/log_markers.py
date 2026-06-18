"""log_markers — 日志事件名常量 (对齐 Java fh-travel-ai LogMarkers.java).

所有业务日志的 event 名必须引用本模块常量, **禁止**自造字面量.
平台消费侧 / 运维 grep / 告警规则均依赖这些字面量.

用法::

    from openagent.audit.log.log_markers import LM

    logger.info(LM.CHAT_REQUEST, session_id="s1", model="qwen-max")
    logger.info(LM.TOOL_CALL, tool="query_flight", status="SUCCESS")
"""
from __future__ import annotations


class _LogMarkers:
    """日志事件名常量命名空间.

    命名规则:
    - 全大写 snake_case
    - 值 = ``[CamelCase]`` 形式, 便于 grep
    """

    CHAT_REQUEST = "[ChatRequest]"
    CHAT_RESPONSE = "[ChatResponse]"
    CHAT_STREAM = "[ChatStream]"

    TOOL_CALL = "[ToolCall]"
    TOOL_CALL_BOUNDS = "[ToolCallBounds]"

    LLM_CALL = "[LlmCall]"
    LLM_PAYLOAD = "[LlmPayload]"

    SCENARIO_ROUTE = "[ScenarioRoute]"
    SCENARIO_LOAD = "[ScenarioLoad]"

    SESSION_CREATE = "[SessionCreate]"
    SESSION_CLOSE = "[SessionClose]"

    AGENT_ACQUIRE = "[AgentAcquire]"
    AGENT_RELEASE = "[AgentRelease]"

    SANDBOX_LOG = "[SandboxLog]"
    SANDBOX_HEALTH = "[SandboxHealth]"

    APP_STARTUP = "[AppStartup]"
    APP_SHUTDOWN = "[AppShutdown]"
    APP_READY = "[AppReady]"

    STORAGE_INIT = "[StorageInit]"
    STORAGE_ERROR = "[StorageError]"

    MCP_REGISTRY = "[McpRegistry]"

    SKILL_LOAD = "[SkillLoad]"

    AUTH_CHECK = "[AuthCheck]"

    ERROR_UNHANDLED = "[ErrorUnhandled]"


LM = _LogMarkers()
