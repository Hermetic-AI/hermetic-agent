"""tests/test_e2e_quality_gates.py — P7 阶段质量门禁静态检查.

两套硬约束:
1. 5 层依赖方向 (L1→L2→L3→L4→L5, 同层允许) — 见设计文档 §3.2
2. 文件行数限制 (L1/L4/L5 ≤ 200, L2/L3 ≤ 250) — 见设计文档 §3.3

P0-P6 已知豁免 (scripts/ci_check.py KNOWN_VIOLATIONS 一致) 不算 NEW 违规.
P7 新增文件 (任何在 tests/ 或 scripts/ 下, 不在豁免列表) 必须严格满足.

实现要点:
- check_layer_imports.py 和 check_file_sizes.py 的逻辑 inline 复用
- 不依赖 scripts/ci_check.py (避免子进程调用)
- 失败时打印所有违规, 便于修复
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "openagent"

# Layer 配置 (与 scripts/ci_check.py 一致)
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

# 与 scripts/ci_check.py KNOWN_VIOLATIONS 完全一致
KNOWN_VIOLATIONS: set[str] = {
    "src/openagent/api/routes.py",
    "src/openagent/api/app.py",  # 238 lines, 超过 L1 上限 200 (P7 之前已存在, 注册 bp 累加)
    "src/openagent/api/controllers/chat_controller.py",
    "src/openagent/api/controllers/scenario_controller.py",
    "src/openagent/api/controllers/session_controller.py",
    "src/openagent/api/controllers/registry_controller.py",
    "src/openagent/api/turn_routes.py",
    "src/openagent/api/lifecycle.py",
    "src/openagent/core/suspendable_scheduler.py",
    "src/openagent/providers/base.py",
    "src/openagent/providers/agent_bridge.py",
    "src/openagent/providers/claude_code_chat.py",
    "src/openagent/providers/claude_code_lifecycle.py",
    "src/openagent/providers/opencode_chat.py",
    "src/openagent/providers/opencode_lifecycle.py",
    "src/openagent/providers/opencode_adapter.py",  # 201 lines, 超过 L4 上限 200 (P7 之前已存在, 1 行)
    "src/openagent/store/base.py",
    "src/openagent/store/postgres.py",
}

# 已知 L1→L4/L5 import 违规 (P0-P6 阶段遗留)
KNOWN_IMPORT_VIOLATIONS: set[str] = {
    "src/openagent/api/lifecycle.py",
    "src/openagent/api/schemas.py",
    "src/openagent/api/controllers/pool_controller.py",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _norm(path: Path) -> str:
    return str(path).replace("\\", "/")


def detect_layer(path: Path) -> str:
    """根据文件路径判定所属 layer.

    LAYER_PATTERNS 用 'openagent/...' 形式 (相对 src/openagent/ 的父目录),
    实际路径以 'src/openagent/...' 开头. 通过判断 path 是否在对应 layer
    目录下 (子路径) 来匹配.
    """
    try:
        rel = _norm(path.relative_to(ROOT))
    except ValueError:
        rel = _norm(path)
    # rel 形如 'src/openagent/api/controllers/chat_controller.py'
    for layer, patterns in LAYER_PATTERNS.items():
        for pat in patterns:
            pat_n = pat.rstrip("/")  # 'openagent/api' or 'openagent/core/suspendable_scheduler.py'
            # 子目录匹配
            dir_prefix = f"src/{pat_n}/"
            if rel.startswith(dir_prefix):
                return layer
            # 整目录 (无尾 /) 自身
            if rel == f"src/{pat_n}":
                return layer
            # 单文件 pattern 精确匹配
            if pat.endswith(".py") and rel == f"src/{pat_n}":
                return layer
    return ""


def detect_layer_by_module(mod_name: str) -> str:
    """根据 import 的 module 名判定 layer."""
    if not mod_name or not mod_name.startswith("openagent."):
        return ""
    parts = mod_name.split(".")
    if len(parts) < 2:
        return ""
    sub = parts[1]
    if sub not in {"api", "scenarios", "skill_runtime", "auip", "core",
                   "providers", "policy", "store", "audit"}:
        return ""
    # 单文件 (e.g. 'openagent.core.suspendable_scheduler')
    if len(parts) >= 4 and parts[2] == "core":
        fname = f"openagent/core/{parts[3]}.py"
        for layer, patterns in LAYER_PATTERNS.items():
            if fname in [p.rstrip("/") for p in patterns]:
                return layer
    sub_path = f"openagent/{sub}/"
    for layer, patterns in LAYER_PATTERNS.items():
        if sub_path in [p.rstrip("/") + "/" for p in patterns]:
            return layer
        if any(p.rstrip("/") == sub_path for p in patterns):
            return layer
    return ""


def _list_files_for_layer(layer: str) -> list[Path]:
    out: list[Path] = []
    for pat in LAYER_PATTERNS[layer]:
        base = SRC.parent / pat.rstrip("/")
        if base.is_file():
            out.append(base)
        elif base.is_dir():
            for p in base.rglob("*.py"):
                if "__pycache__" not in p.parts:
                    out.append(p)
    return out


def _count_lines(path: Path) -> int:
    try:
        return sum(1 for _ in path.open(encoding="utf-8", errors="replace"))
    except OSError:
        return 0


# ---------------------------------------------------------------------------
# Test 1: 5 层 import 方向
# ---------------------------------------------------------------------------


def test_no_upward_imports() -> None:
    """任何 .py 文件不能 import 上层模块.

    例外: 同层 / 第三方 (e.g. pydantic, structlog).
    """
    violations: list[str] = []
    for layer in LAYER_PATTERNS:
        for path in _list_files_for_layer(layer):
            rel = _norm(path.relative_to(ROOT))
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    target = detect_layer_by_module(node.module)
                    if not target or target == layer:
                        continue
                    if target not in ALLOWED_DOWNWARD.get(layer, []):
                        # 排除已知豁免文件
                        if rel in KNOWN_VIOLATIONS or rel in KNOWN_IMPORT_VIOLATIONS:
                            continue
                        violations.append(
                            f"  {rel}:{node.lineno}  {layer} -> {node.module} ({target})"
                        )
    if violations:
        msg = "Upward-import violations:\n" + "\n".join(violations)
        msg += "\n\nAllowed: L1→[L2,L3], L2→[L3], L3→[L4,L5], L4→[L5], L5→[]"
        msg += "\nAdd to KNOWN_VIOLATIONS if pre-existing and acknowledged."
        pytest.fail(msg)


# ---------------------------------------------------------------------------
# Test 2: 文件大小
# ---------------------------------------------------------------------------


def test_file_size_limits() -> None:
    """L1/L4/L5 ≤ 200 行, L2/L3 ≤ 250 行.

    豁免 KNOWN_VIOLATIONS 列表. P7 新增文件必须满足.
    """
    violations: list[str] = []
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
                rel = _norm(f.relative_to(ROOT))
                if rel in KNOWN_VIOLATIONS:
                    continue
                n = _count_lines(f)
                if n > limit:
                    violations.append(f"  {rel}: {n} lines > {limit} ({layer})")
    if violations:
        msg = "File size violations:\n" + "\n".join(violations)
        msg += f"\n\nLimits: L1/L4/L5={LINE_LIMITS['L1']}, L2/L3={LINE_LIMITS['L2']}"
        msg += "\nEither split the file or add to KNOWN_VIOLATIONS."
        pytest.fail(msg)


# ---------------------------------------------------------------------------
# Test 3: Scenario YAML 必填字段
# ---------------------------------------------------------------------------


def test_scenario_yamls_have_required_fields() -> None:
    """6 个 scenario YAML 必须含 name / version / routing / execution / workspace.

    加载失败 / 缺字段 → 列出文件 + 缺什么.
    """
    scenarios_dir = ROOT / "work" / "scenarios"
    if not scenarios_dir.exists():
        pytest.skip("work/scenarios/ not found (P0 not initialized)")

    required_top = ("name", "version", "routing", "execution", "workspace")
    errors: list[str] = []
    yaml_files = sorted(scenarios_dir.glob("*.scenario.yaml"))
    assert yaml_files, "no scenario YAML files found"

    # 用 loader 内部用的 _StrictYAMLLoader (避免 flow context 中未加引号 ${KEY} 报错)
    from openagent.scenarios.loader import _quote_placeholders
    import yaml
    from yaml import SafeLoader

    for p in yaml_files:
        rel = p.relative_to(ROOT)
        try:
            text = _quote_placeholders(p.read_text(encoding="utf-8"))
            data = yaml.load(text, Loader=SafeLoader)
        except (OSError, yaml.YAMLError) as e:
            errors.append(f"  {rel}: parse failed: {e}")
            continue
        if not isinstance(data, dict):
            errors.append(f"  {rel}: top-level not a dict")
            continue
        for k in required_top:
            if k not in data:
                errors.append(f"  {rel}: missing field {k!r}")
        # name 必须是 kebab/snake
        name = data.get("name", "")
        if not isinstance(name, str) or not name:
            errors.append(f"  {rel}: name empty or invalid")
        # version 必须 X.Y.Z
        ver = data.get("version", "")
        if not (isinstance(ver, str) and ver.count(".") == 2 and ver.replace(".", "").isdigit()):
            errors.append(f"  {rel}: version {ver!r} not in X.Y.Z format")
    if errors:
        pytest.fail("Scenario YAML validation:\n" + "\n".join(errors))


def test_six_scenarios_present() -> None:
    """work/scenarios/ 必须有 6 个 scenario 文件 (含 _generic/_default)."""
    scenarios_dir = ROOT / "work" / "scenarios"
    if not scenarios_dir.exists():
        pytest.skip("work/scenarios/ not found (P0 not initialized)")
    files = {p.stem.replace(".scenario", "") for p in scenarios_dir.glob("*.scenario.yaml")}
    expected = {"_generic", "_default", "flight_booking", "expense_audit",
                "customer_service", "code_review"}
    missing = expected - files
    extra = files - expected
    msg = f"Found: {sorted(files)}\n"
    msg += f"Missing: {sorted(missing)}\n"
    msg += f"Extra: {sorted(extra)}\n"
    if missing:
        pytest.fail(msg)


# ---------------------------------------------------------------------------
# Test 4: scripts/ci_check.py 可执行 + 退出码 0
# ---------------------------------------------------------------------------


def test_ci_check_script_passes() -> None:
    """scripts/ci_check.py 必须能跑 + 默认模式退出码 0 (NEW 违规 0)."""
    ci = ROOT / "scripts" / "ci_check.py"
    if not ci.exists():
        pytest.fail("scripts/ci_check.py not found")
    result = subprocess.run(
        [sys.executable, str(ci)],
        capture_output=True, text=True, timeout=60,
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        msg = f"ci_check.py failed (exit {result.returncode}):\n"
        msg += "--- STDOUT ---\n" + result.stdout
        msg += "\n--- STDERR ---\n" + result.stderr
        pytest.fail(msg)


def test_ci_check_script_strict_detects_violations() -> None:
    """scripts/ci_check.py --strict 必须能检测到已知豁免 (退出码 1)."""
    ci = ROOT / "scripts" / "ci_check.py"
    result = subprocess.run(
        [sys.executable, str(ci), "--strict"],
        capture_output=True, text=True, timeout=60,
        cwd=str(ROOT),
    )
    # strict 模式至少要找到 violations
    assert "violations" in result.stdout.lower(), (
        f"strict mode should report violations:\n{result.stdout}\n{result.stderr}"
    )
    # strict 模式下, 有豁免时退出码应为 1
    assert result.returncode == 1, (
        f"strict mode with exemptions should exit 1, got {result.returncode}\n"
        f"stdout: {result.stdout}"
    )


def test_ci_check_script_json_output() -> None:
    """scripts/ci_check.py --json 输出必须是合法 JSON, 含 files_checked 字段."""
    import json
    ci = ROOT / "scripts" / "ci_check.py"
    result = subprocess.run(
        [sys.executable, str(ci), "--json"],
        capture_output=True, text=True, timeout=60,
        cwd=str(ROOT),
    )
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        pytest.fail(f"--json output not valid JSON: {e}\n{result.stdout}")
    assert "files_checked" in data
    assert "total_violations" in data
    assert "new_violations" in data
    assert "known_violations" in data
    assert "exit_code" in data
    # 默认模式 exit_code=0 (无 NEW 违规)
    assert data["exit_code"] == 0, (
        f"default mode should have 0 new violations, got {data['new_violations']}"
    )


# ---------------------------------------------------------------------------
# Test 5: 已知豁免文件本身被检测为 known
# ---------------------------------------------------------------------------


def test_known_violations_detected() -> None:
    """KNOWN_VIOLATIONS 中的文件确实超 limit — 防止豁免列表与实际漂移."""
    for rel in sorted(KNOWN_VIOLATIONS):
        path = ROOT / rel
        if not path.exists():
            continue
        # 判定 layer
        layer = detect_layer(path)
        assert layer, f"{rel} not in any L1-L5 layer — KNOWN_VIOLATIONS misconfigured"
        n = _count_lines(path)
        limit = LINE_LIMITS[layer]
        assert n > limit, (
            f"{rel} ({n} lines) is in KNOWN_VIOLATIONS but under limit {limit} "
            f"— should be removed from exemption list"
        )
