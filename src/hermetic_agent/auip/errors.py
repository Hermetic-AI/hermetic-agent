"""AUIP (Agent-User Interaction Protocol) exceptions.

对应设计文档 §10 错误码 (CARD_SCHEMA_INVALID / TURN_NOT_FOUND /
TURN_ALREADY_TERMINATED), 所有异常带 ``action`` 字段以满足 P9
(可行动信息) 原则.
"""

from __future__ import annotations


class AUIPError(Exception):
    """AUIP 异常的基类.

    所有 AUIP 异常都携带一个 ``action`` 字段, 告诉调用者"接下来该怎么做".
    """

    def __init__(self, message: str, *, action: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.action = action or "Check AUIP configuration"

    def __str__(self) -> str:  # pragma: no cover - debug only
        return f"{self.message} | Action: {self.action}" if self.action else self.message


class CardSchemaInvalid(AUIPError):  # noqa: N818 (domain name per spec §10)
    """Card YAML / dict 不符合 schema."""

    def __init__(self, message: str, *, action: str | None = None) -> None:
        super().__init__(
            message,
            action=action or "Fix the card YAML to match the expected schema.",
        )


class TurnNotFound(AUIPError):  # noqa: N818 (domain name per spec §10)
    """指定的 turn_id 不存在或已无挂起 suspend."""

    def __init__(self, message: str, *, action: str | None = None) -> None:
        super().__init__(
            message,
            action=action or "Check turn_id or start a new turn.",
        )
        self.turn_id: str | None = None


class TurnAlreadyTerminated(AUIPError):  # noqa: N818 (domain name per spec §10)
    """尝试对已 done/errored 的 turn 调 resume()."""

    def __init__(self, turn_id: str, current_status: str) -> None:
        super().__init__(
            f"Turn {turn_id!r} is already terminated (status={current_status!r}); "
            f"cannot resume.",
            action="Start a new turn for the same session.",
        )
        self.turn_id = turn_id
        self.current_status = current_status


__all__ = [
    "AUIPError",
    "CardSchemaInvalid",
    "TurnNotFound",
    "TurnAlreadyTerminated",
]
