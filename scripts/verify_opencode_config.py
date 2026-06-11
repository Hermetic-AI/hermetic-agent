"""scripts/verify_opencode_config.py — 端到端验证 opencode chat 真的 work.

2026-06-10 P8 之后, opencode 容器在以下情况都会报 ProviderModelNotFoundError:
  - 跑老 render_config.py (model 字段格式不对)
  - opencode 1.16.2 旧版处理 provider 拆 prefix 有 bug
  - 跨 opencode 版本升级时, 内置 provider 表改了, 跟我们 cfg 撞了

手动复现的坑:
  1. 改源码后只 ``docker compose restart`` 不 ``docker compose build`` →
     容器跑老 render_config.py, 报错但 cfg 看不出来
  2. opencode 升级 1.16→1.17 后, 多了 minimax 内置 provider, 跟我们的 openai
     provider 撞了 → 模型查找走错 provider
  3. opencode 跑成功 + cfg 看起来对 ≠ chat 真的 work (ProviderModelNotFoundError
     可能在 title generation 阶段触发, 用户 chat 路径没机会跑)

所以这个脚本做 3 件事:
  1. 验源码 (cfg["model"] = model_string 形式)
  2. 验运行中容器的 cfg (provider/models 列表)
  3. 实际发一次 chat, 看是否返回 content (这才是终极判定)

退出码 0 = OK, 1 = 失败 (含详细修复命令).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RENDER_CONFIG = REPO_ROOT / "docker" / "render_config.py"

EXPECTED_LINE_RE = re.compile(
    r'cfg\[["\']model["\']\]\s*=\s*model_string\b'
)


def verify_source() -> int:
    if not RENDER_CONFIG.exists():
        print(f"FAIL: {RENDER_CONFIG} not found")
        return 1
    text = RENDER_CONFIG.read_text(encoding="utf-8")
    if EXPECTED_LINE_RE.search(text):
        print("OK   docker/render_config.py is the fixed version (cfg[model] = model_string)")
        return 0
    print("FAIL docker/render_config.py looks like the OLD version")
    print("     expected: cfg[\"model\"] = model_string")
    print()
    print("Fix: rebuild the opencode image (you probably already did this,")
    print("      the source file just needs to be re-checked after edits)")
    return 1


def verify_container(container: str) -> int:
    try:
        result = subprocess.run(
            ["docker", "exec", container, "cat", "/root/.config/opencode/config.json"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"FAIL: docker exec failed: {e.stderr.strip()}")
        return 1
    except FileNotFoundError:
        print("FAIL: docker CLI not found")
        return 1

    try:
        cfg = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"FAIL: config.json is not valid JSON: {e}")
        return 1

    model = cfg.get("model", "<missing>")
    provider_models = (
        cfg.get("provider", {}).get("openai", {}).get("models", {})
    )
    known_models = list(provider_models.keys())

    issues: list[str] = []
    if "/" not in model:
        issues.append(
            f'cfg["model"] = {model!r} — missing provider/ prefix. '
            "opencode will treat the model name as provider ID and fail."
        )
    if "MiniMax-M2.7-highspeed" not in known_models:
        issues.append(
            f'cfg["provider.openai.models] does not list "MiniMax-M2.7-highspeed". '
            "opencode will reject requests with ProviderModelNotFoundError."
        )

    if issues:
        print(f"FAIL opencode config in {container} is wrong:")
        for issue in issues:
            print(f"     - {issue}")
        print()
        print("Fix: rebuild the opencode image")
        print("  $ docker compose build opencode-1 --no-cache")
        print("  $ docker compose up -d --force-recreate opencode-1")
        return 1

    print(f"OK   {container} opencode config is correct:")
    print(f"     cfg[model] = {model!r}")
    print(f"     cfg[provider.openai.models] = {known_models}")
    return 0


def verify_chat(hub_url: str = "http://localhost:18000") -> int:
    """实际发一次 chat, 验证 LLM 真的返回 content."""
    try:
        import httpx
    except ImportError:
        print("FAIL: httpx not installed; cannot run chat test")
        return 1

    try:
        r = httpx.post(
            f"{hub_url}/agent/chat",
            json={"message": "ping"},
            timeout=30.0,
        )
    except Exception as e:
        print(f"FAIL: chat request failed: {e}")
        return 1

    if r.status_code != 200:
        print(f"FAIL: chat returned HTTP {r.status_code}: {r.text[:200]}")
        return 1

    try:
        data = r.json()
    except json.JSONDecodeError:
        print(f"FAIL: chat response not JSON: {r.text[:200]}")
        return 1

    if not data.get("success"):
        print(f"FAIL: chat success=False: {data.get('error')}")
        return 1

    content = (data.get("result", {}).get("message", {}).get("content", "") or "").strip()
    if not content:
        print(f"FAIL: chat returned empty content: {data}")
        return 1

    scenario = (data.get("scenario") or {}).get("name", "?")
    print(f"OK   chat works end-to-end:")
    print(f"     scenario = {scenario}")
    print(f"     content  = {content[:80]!r}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--container",
        metavar="NAME",
        default="fh-openagent-opencode-1-1",
        help="opencode container name to inspect (default: %(default)s)",
    )
    parser.add_argument(
        "--hub-url",
        metavar="URL",
        default="http://localhost:18000",
        help="Hub URL for chat smoke test (default: %(default)s)",
    )
    parser.add_argument(
        "--source",
        action="store_true",
        help="only check the source file (skip container + chat)",
    )
    parser.add_argument(
        "--container-only",
        action="store_true",
        help="only check the running container (skip source + chat)",
    )
    parser.add_argument(
        "--chat-only",
        action="store_true",
        help="only run the chat smoke test (skip source + container)",
    )
    parser.add_argument(
        "--no-chat",
        action="store_true",
        help="skip the chat smoke test (source + container only)",
    )
    args = parser.parse_args()

    if args.chat_only:
        return verify_chat(args.hub_url)
    if args.source:
        return verify_source()
    if args.container_only:
        return verify_container(args.container)

    rc = 0
    if verify_source() != 0:
        rc = 1
    print()
    if verify_container(args.container) != 0:
        rc = 1
    if not args.no_chat:
        print()
        if verify_chat(args.hub_url) != 0:
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
