"""openagent.streaming — 兼容 shim (历史路径).

P0 架构调整: ``streaming.py`` 物理合并到 ``openagent.providers.streaming``.
新代码请用 ``from openagent.providers.streaming import ...`` 直接 import;
老 import 路径 ``from openagent.providers.streaming import ...`` 仍可用, 但会
产生 ``DeprecationWarning``, 后续 Phase 删.

历史原因: streaming.py 是"LLM/SDK 适配层 → 上层 controller"的统一事件协议,
跟 providers 关系最紧 (被 4 个 provider adapter / 5 个上层 controller import).
移到 providers/ 下后, L4 内部依赖闭环, 上层 controller 仍可 import (跨层 import
是 L1→L4 标准方向, 允许).

API 100% 兼容, 不引入新符号.

注意: 不能直接 ``from openagent.providers.streaming import ...`` — 因为
``openagent/providers/__init__.py`` 会再 import agent_bridge → claude_code_*,
那些模块**也** import 本 shim, 触发循环. 这里用 ``importlib.util`` 直接
按文件路径加载, 完全绕开 ``openagent.providers`` 包的 ``__init__``.
"""
from __future__ import annotations

import importlib.util as _importlib_util
import warnings as _warnings
from pathlib import Path as _Path

_warnings.warn(
    "Importing from 'openagent.streaming' is deprecated. "
    "Use 'openagent.providers.streaming' instead. This shim will be removed in a future release.",
    DeprecationWarning,
    stacklevel=2,
)

# 直接按文件路径加载 ``providers/streaming.py``, 不触发 providers 包的 __init__
# (避免 agent_bridge → claude_code_* → 回这里 的循环).
_STREAMING_FILE = _Path(__file__).resolve().parent / "providers" / "streaming.py"
_spec = _importlib_util.spec_from_file_location("openagent.providers.streaming", _STREAMING_FILE)
_mod = _importlib_util.module_from_spec(_spec)
# 先把模块注册到 sys.modules, 避免内部 import 再次走 spec_from_file_location
import sys as _sys

_sys.modules["openagent.providers.streaming"] = _mod
_spec.loader.exec_module(_mod)

# 把符号 re-export 出来
OPENCODE_STREAM_END = _mod.OPENCODE_STREAM_END
StreamEvent = _mod.StreamEvent
StreamEventType = _mod.StreamEventType
_get = _mod._get
_json_default = _mod._json_default
_normalize = _mod._normalize
_to_dict = _mod._to_dict
map_opencode_event = _mod.map_opencode_event
map_opencode_part = _mod.map_opencode_part

__all__ = [
    "OPENCODE_STREAM_END",
    "StreamEvent",
    "StreamEventType",
    "map_opencode_event",
    "map_opencode_part",
]
