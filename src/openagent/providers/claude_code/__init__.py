"""openagent.providers.claude_code — Claude Code SDK 适配层子包.

物理位置: 本目录.
历史兼容: 老 import 路径 ``from openagent.providers.claude_code.chat import X``
仍工作, 通过同目录的 ``claude_code_chat.py`` shim 转发 (DeprecationWarning).
新代码请直接 ``from openagent.providers.claude_code.chat import X``.

包含:
  - ``chat``        — Claude Code SDK 阻塞 + 流式 chat 主逻辑
  - ``lifecycle``   — per-session 子进程管理 (per-session, 无 prelaunch)
  - ``adapter``     — ClaudeCodeAdapter 薄壳, 实现 AgentProvider 接口
"""
from openagent.providers.claude_code.adapter import *  # noqa: F401, F403
from openagent.providers.claude_code.chat import *  # noqa: F401, F403
from openagent.providers.claude_code.lifecycle import *  # noqa: F401, F403
