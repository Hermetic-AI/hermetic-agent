"""hermetic_agent.providers.opencode — opencode SDK 适配层子包.

物理位置: 本目录.
历史 P0-P7 期间, 这些代码以 ``opencode_*.py`` 形式散落在
``hermetic_agent.providers/`` 顶层, 跟 ``claude_code_*.py`` 不区分.
P0 重构: 按 SDK 拆子包, 文件名去掉 ``opencode_`` 前缀 (因为已经在
``opencode/`` 子包内, 路径里不需要重复 SDK 名).

历史兼容: 老 import 路径 ``from hermetic_agent.providers.opencode.chat import X``
仍工作, 通过同目录的 ``opencode_chat.py`` shim 转发 (DeprecationWarning).
新代码请直接 ``from hermetic_agent.providers.opencode.chat import X``.

包含:
  - ``chat``        — 阻塞 + 流式 chat 主逻辑 (历史 opencode_chat.py)
  - ``lifecycle``   — session 创建 / health / abort (历史 opencode_lifecycle.py)
  - ``adapter``     — OpenCodeAdapter 薄壳, 实现 AgentProvider 接口
  - ``event_hub``   — 长连接复用, 跨 N 个 chat 共享一个 SSE 订阅
  - ``native_sdk``  — opencode 原生 question / todo 端点代理
"""
from hermetic_agent.providers.opencode.adapter import *  # noqa: F401, F403
from hermetic_agent.providers.opencode.chat import *  # noqa: F401, F403
from hermetic_agent.providers.opencode.event_hub import *  # noqa: F401, F403
from hermetic_agent.providers.opencode.lifecycle import *  # noqa: F401, F403
from hermetic_agent.providers.opencode.native_sdk import *  # noqa: F401, F403
