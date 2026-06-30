"""core/_hitl_defs.py — HITL 调度器共享定义 + 工具函数.

从 ``suspendable_scheduler.py`` 抽出的常量 + 默认卡片构建器,
帮助将主文件控制在 L3 250 行限制内.
"""

from __future__ import annotations

from typing import Any

from hermetic_agent.auip.cards import CARD_TYPES_SET

# ask_user 工具 schema (暴露给 provider, 让 LLM 知道有哪些 card_type 可选)
ASK_USER_TOOL: dict[str, Any] = {
    "name": "ask_user",
    "description": (
        "Pause the current turn and ask the user for structured input via a UI card."
    ),
    "input_schema": {
        "type": "object",
        "required": ["card_type"],
        "properties": {
            "card_type": {
                "type": "string",
                "enum": sorted(CARD_TYPES_SET),
                "description": "Which kind of UI card to show the user",
            },
            "title": {"type": "string"},
            "body": {"type": "object"},
            "options": {"type": "array"},
            "decision_buttons": {"type": "array"},
            "actions": {"type": "array"},
        },
    },
}


def build_default_card_input(prompt: str) -> dict[str, Any]:
    """P5 测试模式默认 ask_user 参数 (通用 INPUT 卡片).

    Phase 2 泛化: 移除飞鹤机票-specific 字段,
    替换为通用 field1/field2/field3 表单.
    业务 SKILL 应通过 skill_ctx 提供自己的卡片模板, 不走此默认.
    """
    return {
        "card_type": "OD_INPUT",
        "title": "请输入以下信息",
        "body": {
            "message": prompt or "请填写表单",
        },
        "fields": [
            {"id": "field1", "label": "字段 1", "type": "text", "required": True},
            {"id": "field2", "label": "字段 2", "type": "text", "required": True},
            {"id": "field3", "label": "字段 3", "type": "text", "required": False},
        ],
    }


__all__ = ["ASK_USER_TOOL", "build_default_card_input"]
