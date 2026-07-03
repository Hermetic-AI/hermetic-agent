"""api/http/streaming/ — SSE / 流式响应基础设施.

P0 重构: 把 chat_controller.py 里 836 行的 SSE 相关逻辑下沉到这个子包,
按关注点拆分:
  - keepalive.py   SSE 心跳拦截器
  - ask_user.py    ask_user 合成工具 → card 拦截器
  - done_gate.py   done 事件单写哨兵 (修状态机 race)
  - turn_bridge.py auip.TurnEvent → StreamEvent 翻译 (chat_controller +
                  turn_routes 共享)
  - route_hints.py 飞鹤航线启发式 (路由正则 + 日期校验, 修 P0 #4)

P1 重构: 随 api/ 拆 4 子包, 本模块从 ``hermetic_agent.api.streaming`` 移到
``hermetic_agent.api.http.streaming``. 新代码直接 ``from hermetic_agent.api.http.streaming import ...``;
旧 ``hermetic_agent.api.streaming`` 仍通过 ``api/http/routes.py`` (原 shim) 兼容
(其实它现在指 ``hermetic_agent.api.http.routes``, 不再是 streaming shim — 见
``api/http/routes.py`` 顶部 docstring).
"""
from hermetic_agent.api.http.streaming.ask_user import (
    ASK_USER_TOOL_NAMES,
    is_ask_user_tool,
    stream_with_ask_user_intercept,
)
from hermetic_agent.api.http.streaming.done_gate import DoneGate
from hermetic_agent.api.http.streaming.keepalive import (
    DEFAULT_KEEPALIVE_INTERVAL,
    KEEPALIVE_SSE_LINE,
    stream_with_keepalive,
)
from hermetic_agent.api.http.streaming.route_hints import (
    has_complete_route_hint,
    should_bypass_hitl_placeholder,
)
from hermetic_agent.api.http.streaming.turn_bridge import turn_event_to_sse
from hermetic_agent.api.http.streaming.card_message_rewriter import rewrite_card_message

__all__ = [
    # ask_user
    "ASK_USER_TOOL_NAMES",
    "is_ask_user_tool",
    "stream_with_ask_user_intercept",
    # done gate
    "DoneGate",
    # keepalive
    "DEFAULT_KEEPALIVE_INTERVAL",
    "KEEPALIVE_SSE_LINE",
    "stream_with_keepalive",
    # route hints
    "has_complete_route_hint",
    "should_bypass_hitl_placeholder",
    # turn bridge
    "turn_event_to_sse",
    # card message rewriter
    "rewrite_card_message",
]
