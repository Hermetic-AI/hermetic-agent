"""WorkTrace Model — 1 行 / turn, events 存 JSON.

对应表: ``turn_work_trace`` (Tortoise generate_schemas 自动建)
字段语义详见 ``docs/superpowers/specs/2026-06-30-persistent-work-trace-design.md §2``.
"""
from __future__ import annotations

from tortoise import fields
from tortoise.models import Model


class TurnWorkTrace(Model):
    """单 turn 的工作轨迹 (Activity + Files + Plan 全量)."""

    turn_id = fields.UUIDField(pk=True, binary=False, description="对齐 chat_turns.id")
    session_id = fields.UUIDField(binary=False, description="所属 session")
    scenario = fields.CharField(
        max_length=128, null=True, description="scenario 名 (flight_booking / _generic)"
    )
    status = fields.CharField(
        max_length=32, default="running",
        description="running / suspended / done / error",
    )
    started_at = fields.DatetimeField(null=True, description="turn 开始")
    finished_at = fields.DatetimeField(null=True, description="turn 结束")
    summary = fields.JSONField(default=dict, description="聚合指标")
    events = fields.JSONField(default=list, description="TraceEvent[] 数组")
    is_deleted = fields.BooleanField(default=False, description="软删除标记")
    deleted_at = fields.DatetimeField(null=True, description="软删除时间")
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "turn_work_trace"
        indexes = [
            ("session_id", "started_at"),
            ("status",),
        ]


__all__ = ["TurnWorkTrace"]
