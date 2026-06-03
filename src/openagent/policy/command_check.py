"""Shell 命令白/黑名单 — L5 Infrastructure Layer.

简单 bash 子命令前缀校验, 拆分 `&&` / `||` / `;` / `|` 后逐个判定.

不解析完整 shell 语法; 故意**保守**——任何 metacharacter 在 safe 档直接拒绝.
"""

from __future__ import annotations

# 拆分命令用的分隔符 (按这个顺序 split, 保留原 token)
_SEPARATORS = ("&&", "||", ";", "|")


# shell metacharacter, 在 safe 档里禁止
METACHARACTERS = (">", "<", "&", "`", "$", "(", ")")


def _split_command(command: str) -> list[str]:
    """把 `a && b | c; d` 拆成 ['a', 'b', 'c', 'd'].

    忽略空 token 和两端的空白.
    """
    if not command:
        return []
    # 先按最长的分隔符 split, 避免 `&&` 被 `&` 抢先吃掉
    parts = [command]
    for sep in _SEPARATORS:
        new_parts: list[str] = []
        for p in parts:
            new_parts.extend(p.split(sep))
        parts = new_parts
    return [p.strip() for p in parts if p.strip()]


def _first_token(subcmd: str) -> str:
    """提取子命令的第一个 token（命令名）.

    跳过 env var 前缀 (FOO=bar cmd), 用空白切.
    """
    # 按空白切, 跳过前导的 KEY=VAL 形式
    tokens = subcmd.split()
    for t in tokens:
        if "=" in t and not t.startswith("="):
            # 可能是 KEY=VAL 形式, 继续
            continue
        return t
    return tokens[0] if tokens else ""


def has_metacharacter(command: str) -> bool:
    """command 是否包含 shell metacharacter（> < & ` $()）."""
    return any(ch in command for ch in METACHARACTERS)


def is_command_allowed(
    command: str,
    allowed: list[str] | None = None,
    denied: list[str] | None = None,
    *,
    tool_level: str = "standard",
) -> tuple[bool, str]:
    """判定一条 shell 命令是否被允许.

    规则:
      1. tool_level=safe 且含 metacharacter → 拒绝
      2. 子命令拆分, **每个**都得通过
      3. 黑名单 (denied) 永远优先, 命中即拒绝
      4. 白名单 (allowed) 非空时, 子命令首 token 必须在 allowed 里
    """
    if not command or not command.strip():
        return False, "empty command"

    if tool_level == "safe" and has_metacharacter(command):
        return False, "metacharacters are blocked in safe tool_level"

    denied = denied or []
    allowed = allowed or []
    subcmds = _split_command(command)
    if not subcmds:
        return False, "no executable subcommand after splitting"

    for sub in subcmds:
        first = _first_token(sub)
        # 1) 黑名单永远优先: 完整子命令包含任一 denied 模式
        for d in denied:
            if d and d in sub:
                return False, f"subcommand {sub!r} matches denied pattern {d!r}"
        # 2) 白名单: 非空时, 首 token 必须在白名单里
        if allowed and (not first or first not in allowed):
            return False, f"subcommand {sub!r} not in allowed_commands"

    return True, "ok"


__all__ = [
    "METACHARACTERS",
    "has_metacharacter",
    "is_command_allowed",
]
