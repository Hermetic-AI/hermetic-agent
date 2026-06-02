"""TaskResult — pure DTO returned by SchedulerService and ChatStepService.

Lives in its own module (not in scheduler.py) so that ChatStepService can
import it without creating a circular dependency on scheduler.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class TaskResult:
    """任务执行的统一结果 DTO。

    用于在 ``SchedulerService`` 与 ``ChatStepService`` 之间传递单次任务或任务链
    的执行结果；不依赖任何业务层对象，便于序列化与跨层传递。

    Attributes:
        success: 任务是否成功。
        result: 成功时的载荷（单任务为文本，任务链为结构化字典）。
        error: 失败时的错误描述字符串。
        agent_name: 实际被调用的 Agent 名。
        session_id: 后端会话 ID。
        duration: 任务耗时（秒）。
    """

    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None
    agent_name: Optional[str] = None
    session_id: Optional[str] = None
    duration: Optional[float] = None
