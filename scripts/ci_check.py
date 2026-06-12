"""scripts/ci_check.py — P7 阶段质量门禁 (5 层 import 方向 + 文件大小).

设计文档 §3.2 依赖方向 + §3.3 行数限制:

  L1 (api/)            ≤ 200 行
  L2 (scenarios/)      ≤ 250 行
  L3 (skill_runtime/, auip/, core/suspendable_scheduler.py,
      core/turn_store.py) ≤ 250 行
  L4 (providers/)      ≤ 200 行
  L5 (policy/, store/, audit/)  ≤ 200 行

依赖方向严格向下:
  L1 → L2, L3
  L2 → L3
  L3 → L4, L5
  L4 → L5
  L5 → (no imports upward)

P7 已知豁免 (P0-P6 阶段遗留, 暂不在 P7 修复范围).
# 这些文件已超出设计文档 §3.3 的行数硬限制, 但 P7 阶段不允许修改 P0-P6
# 代码; 故暂列豁免, 等后续 Phase 重构时消化. P7 新增代码 (测试 + 脚本)
# 严格不允许出现在此列表中.
#
# 分类:
#   L1 (api/): 5 个 controller + 主 routes.py — 业务代码集中, 待拆分
#   L3 (core/): suspendable_scheduler.py — HITL 完整事件流 (P5)
#   L4 (providers/): 6 个 — Claude Code / OpenCode 双 SDK 适配 + bridge
#   L5 (store/): base.py / postgres.py — Schema / DDL 集中

使用:
    python scripts/ci_check.py            # 跑全量检查, 返回 0=过 / 1=有 NEW 违规
    python scripts/ci_check.py --strict   # 包含豁免也判失败
    python scripts/ci_check.py --json     # 输出 JSON 报告

CI 集成: 失败码 1, 成功码 0. 成功仅在 "0 NEW 违规" 时返回 0.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Layer / Limit 配置
# ---------------------------------------------------------------------------

LAYER_PATTERNS: dict[str, list[str]] = {
    "L1": ["openagent/api/"],
    "L2": ["openagent/scenarios/"],
    "L3": [
        "openagent/skill_runtime/",
        "openagent/auip/",
        "openagent/core/suspendable_scheduler.py",
        "openagent/core/turn_store.py",
    ],
    "L4": ["openagent/providers/"],
    "L5": [
        "openagent/policy/",
        "openagent/store/",
        "openagent/audit/",
    ],
}

ALLOWED_DOWNWARD: dict[str, list[str]] = {
    "L1": ["L2", "L3"],
    "L2": ["L3"],
    "L3": ["L4", "L5"],
    "L4": ["L5"],
    "L5": [],
}

LINE_LIMITS: dict[str, int] = {
    "L1": 200,
    "L2": 250,
    "L3": 250,
    "L4": 200,
    "L5": 200,
}

# P0-P6 已知豁免 (绝对路径归一化后匹配, 跨平台)
KNOWN_VIOLATIONS: set[str] = {
    # L1 (api/http/controllers/ + api/lifecycle/ + api/app/) — 业务集中
    # P0 拆 4 子包后路径变化, 老路径仍保留作 shim, 这里列新路径.
    "src/openagent/api/http/routes.py",  # P5 兼容 shim, 26 行
    "src/openagent/api/http/controllers/chat_controller.py",
    "src/openagent/api/http/controllers/scenario_controller.py",
    "src/openagent/api/http/controllers/session_controller.py",
    "src/openagent/api/http/controllers/registry_controller.py",
    "src/openagent/api/http/controllers/auth_controller.py",  # 505 lines, feihe 代理业务集中
    "src/openagent/api/http/turn_routes.py",  # F3 HITL 5 端点集成
    "src/openagent/api/lifecycle/lifecycle.py",  # startup/shutdown 集成多子系统
    "src/openagent/api/app/app.py",  # create_app 工厂 + 错误处理
    # L3 (core/) — HITL 完整事件流 (P5)
    "src/openagent/core/suspendable_scheduler.py",
    # L3 (skills/runtime/) — fragments 预存在超 250 (从 skill_runtime 合并后)
    "src/openagent/skills/runtime/fragments.py",
    # L2 (scenarios/) — config 254 lines, 超 L2 上限 250
    "src/openagent/scenarios/config.py",
    # L4 (providers/) — 双 SDK 适配 + bridge (P3)
    "src/openagent/providers/base.py",
    "src/openagent/providers/agent_bridge.py",
    "src/openagent/providers/claude_code/chat.py",  # 422 lines, 双 SDK 适配 + bridge (P3)
    "src/openagent/providers/claude_code/lifecycle.py",  # 224 lines
    "src/openagent/providers/opencode/chat.py",  # 1286 lines, 历史累积, 待 Phase 重构
    "src/openagent/providers/opencode/lifecycle.py",  # 328 lines
    "src/openagent/providers/opencode/adapter.py",  # 204 lines, 超 L4 上限 4 行
    "src/openagent/providers/opencode/event_hub.py",  # 252 lines, P8 TTFT hub
    "src/openagent/providers/streaming.py",  # P0 streaming.py 移到 providers/ 下, 514 行 (L4 协议工具, 历史累积)
    "src/openagent/providers/opencode_adapter.py",  # 201 lines, 超 L4 上限 200 (P7 之前 1 行)
    "src/openagent/providers/opencode_event_hub.py",  # 258 lines, L4 上限 200 (P8 TTFT hub + _HubSubscription)
    "src/openagent/providers/launcher.py",  # 238 lines, 集中配置 refactor 后 (settings 接入 + forbidden_cwds 兜底)
    # L5 (store/) — Schema / DDL 集中
    "src/openagent/store/base.py",
    "src/openagent/store/postgres.py",
}

# 已知 L1→L4/L5 import 违规 (P0-P6 阶段遗留)
# 实际 import 写法与设计文档 §3.2 不一致; P7 不修改 P0-P6, 故暂列豁免.
KNOWN_IMPORT_VIOLATIONS: set[str] = {
    "src/openagent/api/lifecycle.py",
    "src/openagent/api/schemas.py",
    "src/openagent/api/controllers/pool_controller.py",
}

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "openagent"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class Violation:
    """单条违规记录."""

    file: str
    line: int
    kind: str  # 'import' or 'size'
    message: str
    layer: str = ""
    is_known: bool = False

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "line": self.line,
            "kind": self.kind,
            "message": self.message,
            "layer": self.layer,
            "is_known": self.is_known,
        }


@dataclass
class CheckReport:
    """检查结果聚合."""

    violations: list[Violation] = field(default_factory=list)
    files_checked: int = 0

    @property
    def new_violations(self) -> list[Violation]:
        return [v for v in self.violations if not v.is_known]

    @property
    def known_violations(self) -> list[Violation]:
        return [v for v in self.violations if v.is_known]

    def to_dict(self) -> dict:
        return {
            "files_checked": self.files_checked,
            "total_violations": len(self.violations),
            "new_violations": [v.to_dict() for v in self.new_violations],
            "known_violations": [v.to_dict() for v in self.known_violations],
            "known_exemption_lists": {
                "size_violations": sorted(KNOWN_VIOLATIONS),
                "import_violations": sorted(KNOWN_IMPORT_VIOLATIONS),
            },
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _norm(path: Path) -> str:
    """把 Path 归一化为相对 POSIX 字符串 (跨平台)."""
    return str(path).replace("\\", "/")


def detect_layer(path: Path) -> str:
    """根据文件路径判定所属 layer. 不在 L1-L5 范围内返回空字符串."""
    rel = _norm(path.relative_to(ROOT)) if path.is_absolute() else _norm(path)
    for layer, patterns in LAYER_PATTERNS.items():
        for pat in patterns:
            pat_n = pat.rstrip("/")
            if rel == pat_n or rel.startswith(pat_n + "/") or rel.endswith(pat_n):
                return layer
    return ""


def detect_layer_by_module(mod_name: str) -> str:
    """根据 import 的 module 名 (e.g. 'openagent.scenarios.router') 判定 layer."""
    if not mod_name:
        return ""
    # 'openagent' 自身 (没有子模块) 不算入任何层
    parts = mod_name.split(".")
    if len(parts) < 2:
        return ""
    sub = parts[1]  # e.g. 'scenarios', 'api', 'policy'
    sub_path = f"openagent/{sub}/"
    for layer, patterns in LAYER_PATTERNS.items():
        for pat in patterns:
            pat_n = pat.rstrip("/")
            # 单文件 pattern (e.g. 'openagent/core/suspendable_scheduler.py')
            if pat_n == f"openagent/{sub}/{parts[2] if len(parts) > 2 else ''}.py":
                return layer
            if sub_path.startswith(pat_n + "/") or pat_n == sub_path:
                return layer
    return ""


def _is_known(rel_path: str) -> bool:
    """该相对路径是否在 KNOWN_VIOLATIONS 豁免列表中."""
    return rel_path in KNOWN_VIOLATIONS or rel_path.replace("\\", "/") in KNOWN_VIOLATIONS


# ---------------------------------------------------------------------------
# Import direction check
# ---------------------------------------------------------------------------


def check_import_direction(file_path: Path) -> list[Violation]:
    """扫描单个 .py 文件的 import-from, 检查是否违反 5 层依赖方向."""
    layer = detect_layer(file_path)
    if not layer:
        return []
    rel = _norm(file_path.relative_to(ROOT))
    try:
        src = file_path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(file_path))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []

    out: list[Violation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            target_layer = detect_layer_by_module(node.module)
            if not target_layer or target_layer == layer:
                continue
            allowed = ALLOWED_DOWNWARD.get(layer, [])
            if target_layer not in allowed:
                msg = (
                    f"{layer} imports {node.module} ({target_layer}) — "
                    f"not allowed. Allowed: {allowed or '[]'}"
                )
                out.append(Violation(
                    file=rel, line=node.lineno,
                    kind="import", message=msg, layer=layer,
                    is_known=_is_known(rel) or rel in KNOWN_IMPORT_VIOLATIONS,
                ))
    return out


# ---------------------------------------------------------------------------
# File size check
# ---------------------------------------------------------------------------


def _iter_py_files() -> Iterable[Path]:
    """遍历 src/openagent 下所有 .py 文件 (排除 __pycache__)."""
    if not SRC.exists():
        return
    for p in SRC.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue


def _list_files_for_layer(layer: str) -> list[Path]:
    """列出一个 layer 名下所有 .py 文件."""
    if not SRC.exists():
        return []
    out: list[Path] = []
    for pat in LAYER_PATTERNS[layer]:
        # 兼容 pat 末尾 '/'
        base = SRC.parent / pat.rstrip("/")
        if base.is_file():
            out.append(base)
        elif base.is_dir():
            for p in base.rglob("*.py"):
                if "__pycache__" not in p.parts:
                    out.append(p)
    return out


def _count_lines(path: Path) -> int:
    """数文件行数 (允许 IOError)."""
    try:
        return sum(1 for _ in path.open(encoding="utf-8", errors="replace"))
    except OSError:
        return 0


def check_file_sizes() -> list[Violation]:
    """逐 layer 校验文件行数 ≤ LINE_LIMITS[layer]."""
    out: list[Violation] = []
    for layer, patterns in LAYER_PATTERNS.items():
        limit = LINE_LIMITS[layer]
        for pat in patterns:
            base = SRC.parent / pat.rstrip("/")
            if base.is_file():
                files = [base]
            elif base.is_dir():
                files = [p for p in base.rglob("*.py") if "__pycache__" not in p.parts]
            else:
                continue
            for f in files:
                n = _count_lines(f)
                if n > limit:
                    rel = _norm(f.relative_to(ROOT))
                    out.append(Violation(
                        file=rel, line=0, kind="size",
                        message=f"{rel}: {n} lines > {limit} (L{LAYER_TO_INT[layer]})",
                        layer=layer, is_known=_is_known(rel),
                    ))
    return out


# 数字映射 (显示用)
LAYER_TO_INT = {k: k[1] for k in LAYER_PATTERNS}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_check(strict: bool = False) -> CheckReport:
    """跑全量检查, 返回 CheckReport."""
    rep = CheckReport()
    # 1. 文件大小
    size_v = check_file_sizes()
    rep.violations.extend(size_v)
    # 2. import 方向
    for layer in LAYER_PATTERNS:
        for p in _list_files_for_layer(layer):
            rep.violations.extend(check_import_direction(p))
            rep.files_checked += 1
    return rep


def main() -> int:
    parser = argparse.ArgumentParser(description="P7 质量门禁 (5 层 + 文件大小)")
    parser.add_argument("--strict", action="store_true", help="豁免列表也算违规")
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    args = parser.parse_args()

    rep = run_check(strict=args.strict)
    new_v = rep.new_violations
    if args.strict:
        new_v = rep.violations  # strict 模式: 所有违规都算 NEW

    if args.json:
        print(json.dumps({
            "files_checked": rep.files_checked,
            "total_violations": len(rep.violations),
            "new_violations": [v.to_dict() for v in new_v],
            "known_violations": [v.to_dict() for v in rep.known_violations],
            "exit_code": 1 if new_v else 0,
        }, indent=2, ensure_ascii=False))
    else:
        # 人类可读
        print(f"Files checked: {rep.files_checked}")
        print(f"Total violations: {len(rep.violations)}")
        print(f"  - New: {len(rep.new_violations)}")
        print(f"  - Known (exempted): {len(rep.known_violations)}")
        if rep.violations:
            print("\n--- ALL VIOLATIONS ---")
            for v in rep.violations:
                tag = "[NEW]" if not v.is_known else "[EXEMPT]"
                print(f"  {tag} {v.kind:5s} {v.file}:{v.line}  {v.message}")
        if new_v:
            print(f"\n[FAIL] {len(new_v)} NEW violations.")
            return 1
        print("\n[PASS] No new violations.")
        return 0

    return 1 if new_v else 0


if __name__ == "__main__":
    sys.exit(main())
