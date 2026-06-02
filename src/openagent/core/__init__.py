"""Core module - 核心调度组件

聚合 Agent 实例池（``AgentPoolService``）、任务调度服务（``SchedulerService``）
及其拆出的 chat 步骤服务（``ChatStepService``），并向上层 API 暴露统一的
``TaskResult`` 类型。文件中保留了 ``Scheduler`` / ``AgentPoolManager``
旧名字作为兼容别名。
"""

from openagent.core.agent_pool import AgentPoolService, AgentInstance
from openagent.core.scheduler import SchedulerService
from openagent.core.services.chat_step_service import ChatStepService
from openagent.core.task_result import TaskResult

# Back-compat aliases: callers importing the old names continue to work.
Scheduler = SchedulerService
AgentPoolManager = AgentPoolService

__all__ = [
    "AgentPoolService",
    "AgentPoolManager",  # back-compat alias
    "AgentInstance",
    "SchedulerService",
    "Scheduler",  # back-compat alias
    "TaskResult",
    "ChatStepService",
]
