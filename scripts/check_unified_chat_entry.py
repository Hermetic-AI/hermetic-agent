"""scripts/check_unified_chat_entry.py — 校验 统一对话入口 约束.

P0 永远禁止: 任何 controller 文件里出现 per-scenario chat 路由.

跑: python scripts/check_unified_chat_entry.py
返回 0 = 干净, 1 = 有违规 (打印路径+行号)
"""
import re
import sys
from pathlib import Path

# 禁止的路由模式
FORBIDDEN_PATTERNS = [
    re.compile(r'@.*\.post\(\s*["\']?/<[^>]+>/chat["\']?\s*\)'),
    re.compile(r'@.*\.post\(\s*["\']?/<[^>]+>/chat/stream["\']?\s*\)'),
]

# 例外: 这个约束文档本身 + 显式豁免
ALLOWED_FILES = {
    Path("scripts/check_unified_chat_entry.py"),
}

CONTROLLER_DIRS = [
    Path("src/openagent/api/controllers/"),
    Path("src/openagent/api/"),
]


def main() -> int:
    violations: list[str] = []
    files_scanned = 0
    for d in CONTROLLER_DIRS:
        if not d.exists():
            continue
        for path in d.rglob("*.py"):
            if "__pycache__" in str(path):
                continue
            if path in ALLOWED_FILES:
                continue
            files_scanned += 1
            src = path.read_text(encoding="utf-8")
            for i, line in enumerate(src.splitlines(), 1):
                for pat in FORBIDDEN_PATTERNS:
                    if pat.search(line):
                        violations.append(f"  {path}:{i}  {line.strip()}")

    print(f"[unified-chat-entry] Scanned {files_scanned} files")
    if violations:
        print(f"[FAIL] {len(violations)} forbidden per-scenario chat endpoint(s):")
        for v in violations:
            print(v)
        print()
        print("所有 chat 入口必须统一在 src/openagent/api/controllers/chat_controller.py")
        print("详见 CLAUDE.md §Key Implementation Notes 末尾的 🚨 HARD CONSTRAINT")
        return 1
    print("[PASS] No per-scenario chat endpoint found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
