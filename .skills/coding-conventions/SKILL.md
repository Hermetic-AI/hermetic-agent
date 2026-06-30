---
name: coding-conventions
description: 项目的代码风格与可观测性约定 — 中文文档字符串 + structlog 关键步骤日志。Use when writing or reviewing code that needs to be production-debuggable and team-readable.
risk: safe
source: C:\WorkSpace\Coding\hermetic_agent\CLAUDE.md
date_added: 2026-06-02
---

# Coding Conventions — Agent Skill Guide

本项目的代码风格与可观测性约定。**违反这些约定的 PR 不应被合并。**

---

## 1. 中文文档字符串（强制）

### 1.1 适用对象

- 所有**类**
- 所有**公共方法**（名字不以 `_` 开头）
- 所有**公共模块级函数**

`_` 开头的方法（私有）可以省略，但**鼓励**也写。

### 1.2 模板

```python
class MyService:
    """一句话用途说明。

    更详细的设计意图、依赖关系、注意事项。
    不要在这里写 changelog — 那是 git log 的事。
    """

    def public_method(self, name: str, count: int = 0) -> bool:
        """一句话功能描述。

        Args:
            name: 含义说明。
            count: 默认值 0，含义。

        Returns:
            True 表示成功，False 表示业务失败（不是异常）。

        Raises:
            ValueError: 当 count 为负时。
        """
        ...
```

### 1.3 必须包含的标签

- **类**：至少 1 句话说明用途
- **方法**：`Args`（有参数时）、`Returns`（非 `None` 时）、`Raises`（会抛异常时）

### 1.4 风格

- 用中文句号「。」而不是英文「.」
- 短句优先
- 不要写"该方法用于..."这种废话开头
- 不要在 docstring 里复述方法名

### 1.5 反例

❌ `"""Chat method."""` — 没说明
❌ `"""This method chats with the agent and returns the result."""` — 复述方法名
❌ `"""聊天方法"""` — 没有 Args/Returns
✅ `"""向 Agent 发送消息并同步等待回复。

Args:
    session_id: 已有会话 ID；为空则创建新会话。
    message: 用户消息内容，至少 1 个字符。

Returns:
    ChatResult，其中 success 字段反映是否成功拿到模型回复。
"""`

---

## 2. structlog 关键步骤日志（强制）

### 2.1 何时打印

| 触发点 | 级别 | 命名约定 |
|--------|------|----------|
| 服务/方法入口 | `info` | `event="<verb>_<noun>"` |
| 状态切换 | `info` | `session_created`, `agent_registered` |
| 业务失败（可恢复） | `warning` | `event_failed` + error=str(e) |
| 异常抛出 | `error` | `event_crash` 或 `event_error` |
| 健康检查成功 | `debug` | `health_check_ok` |
| 健康检查失败 | `warning` | `health_check_failed` + status_code |

### 2.2 模板

```python
logger = structlog.get_logger(__name__)


async def create_session(self, agent_name: str) -> SessionInfo:
    """..."""
    logger.info("session_create_start", agent_name=agent_name)
    try:
        result = await client.session.create()
    except Exception as e:
        logger.error("session_create_failed", agent_name=agent_name, error=str(e))
        raise RuntimeError(...) from e
    logger.info("session_created", session_id=result.id, agent_name=agent_name)
    return ...
```

### 2.3 必须打的日志点（按模块）

- **`api/app.py`**: 启动入口 `application_startup`，每个子组件 ready 之后
- **`api/controllers/*`**: 每个路由入口（`info`），业务异常（`error`），Pydantic 校验失败（`warning`）
- **`core/agent_pool.py`**: `agent_registered` / `agent_unregistered` / `agent_acquired` / `agent_released` / `agent_marked_offline` / `health_check_ok` / `health_check_failed`
- **`core/scheduler.py`**: `task_completed` / `task_failed` / `chain_step` / `chain_completed` / `chain_failed`
- **`providers/agent_bridge.py`**: `chat_start` / `chat_completed` / `chat_failed` / `skills_injected_into_prompt` / `agent_registered`
- **`providers/*_chat.py`**: `chat_start` / `chat_failed` / `chat_completed`
- **`providers/*_lifecycle.py`**: `session_create_start` / `session_created` / `session_delete_start` / `session_deleted` / `abort_failed`
- **`skills/registry.py`**: `skills_loaded` / `skill_already_registered`
- **`mcp/registry.py`**: `tool_registered` / `tool_enabled_changed` / `calling_remote_tool`

### 2.4 禁止事项

❌ `print(...)` — 用 `logger.info(...)`
❌ `logger.info(f"User said: {message}")` — 可能泄露 PII / 长内容；用 `message_length` 替代
❌ 在循环里 `logger.info(...)` 打印每条 — 改成 `logger.debug` 或批处理
❌ 重复日志 — 一个事件只打一次

### 2.5 结构化字段

每个日志都带**结构化字段**，不要拼字符串：

```python
# ✅ 好
logger.info("agent_registered", name=name, base_url=base_url, sdk_type=sdk_type)

# ❌ 差
logger.info(f"Agent {name} registered at {base_url} with SDK {sdk_type}")
```

---

## 3. 入口文件

每个 Python 文件的**最顶部**必须有：

```python
"""<一句话模块用途>。

更详细说明模块的职责、关键依赖、设计意图。
"""
from __future__ import annotations

# imports...
```

---

## 4. 与其他 skill 的关系

- **architecture-enforcement**: 本 skill 是它的补充，不冲突
- **code-quality**: 函数 ≤ 40 行、模块 ≤ 300 行 — 仍然强制
- **ci-quality-gates**: 提交前必须通过 ruff + mypy + pytest

---

## 5. 检查清单（自审时用）

- [ ] 类都有中文 docstring
- [ ] 公共方法都有中文 docstring + Args/Returns/Raises
- [ ] 每个公共方法入口有 `logger.info`
- [ ] 每个异常路径有 `logger.error` 或 `logger.warning`
- [ ] 日志用结构化字段（不是 f-string）
- [ ] 没有 `print(...)`
- [ ] 没有 import 但未用的符号

---

## 6. When to Use This Skill

- 写新文件或新类时
- Code review 时检查规范
- 重构旧文件时补全 docstring
- 用户说"加注释"、"加日志"时
- CI 检查
