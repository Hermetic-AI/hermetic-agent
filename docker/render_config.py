"""policy.json → opencode config.json 渲染器.

输入: /opt/sandbox/policy.json (ro bind mount, Hub 注入)
输出: /root/.config/opencode/config.json (容器层, stop 保留 / rm 才清)

policy.json schema (跟 agent-sandbox-overview.md §3.4 一致):
{
  "policy_version": "v1",
  "scenario": "flight_booking",
  "agent": {
    "name": "opencode",
    "model": "openai/deepseek-chat"     # ★ provider/model-id
  },
  "skills": ["flight-query"],
  "workspace_mode": "direct",
  "tool_level": "standard",              # safe / standard / full
  "max_turns": 30,
  "max_budget_usd": 2.0
}

opencode config.json (简化版, 只覆盖我们关心的字段):
{
  "$schema": "https://opencode.ai/config.json",
  "model": "openai/deepseek-chat",
  "provider": {
    "openai": {
      "options": { "baseURL": "https://api.deepseek.com/v1" }
    }
  },
  "permission": { ... },
  "skills": { "paths": [...] }            # 由 workspace_mode 决定
}

LLM 凭证从 env 读 (OPENAI_API_KEY / ANTHROPIC_API_KEY / OPENAI_BASE_URL),
不进 config.json. opencode serve 自己从进程 env 读.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="[%(levelname)s] %(message)s",
)


# tool_level → opencode permission 映射
_TOOL_PERMISSIONS = {
    "safe": {
        "edit": "deny",
        "bash": "deny",
        "webfetch": "deny",
    },
    "standard": {
        "edit": "allow",
        "bash": "ask",
        "webfetch": "ask",
    },
    "full": {
        "edit": "allow",
        "bash": "allow",
        "webfetch": "allow",
    },
}


def _read_policy(path: Path) -> dict:
    if not path.exists():
        print(f"[render_config] WARN: policy not found at {path}, using empty", file=sys.stderr)
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _deep_merge(base: dict, overlay: dict) -> dict:
    """浅覆深的 dict 合并. list 字段整体替换. 专给 policy.json 合并用."""
    out = dict(base)
    for k, v in overlay.items():
        if (
            k in out
            and isinstance(out[k], dict)
            and isinstance(v, dict)
        ):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _resolve_provider(model_string: str) -> tuple[str, str]:
    """从 'openai/deepseek-chat' 拆出 ('openai', 'deepseek-chat').

    没 '/' 时: provider=model_string, model_id=model_string (opencode 自己处理).
    """
    if "/" in model_string:
        provider, model_id = model_string.split("/", 1)
        return provider.strip(), model_id.strip()
    return model_string, model_string


def _build_provider_block(policy: dict) -> dict:
    """从 env 构造 provider 配置 (OpenAI 兼容 + Anthropic).

    OpenAI 兼容: OPENAI_API_KEY + OPENAI_BASE_URL
    Anthropic: ANTHROPIC_API_KEY

    注意 env 占位符用 opencode 自己的 ``{env:VAR}`` 语法 (见
    relate_project/opencode/packages/opencode/src/config/variable.ts:34-38),
    不是 shell 的 ``${VAR}`` — 后者会被 opencode 当字面量原样发出去。
    """
    provider_block: dict = {}

    # OpenAI 兼容 (DeepSeek/Qwen/GLM/Minimax/Ollama/自建)
    if os.environ.get("OPENAI_API_KEY"):
        openai_opts: dict = {"apiKey": "{env:OPENAI_API_KEY}"}
        if os.environ.get("OPENAI_BASE_URL"):
            openai_opts["baseURL"] = "{env:OPENAI_BASE_URL}"
        provider_block["openai"] = {"options": openai_opts}

    # Anthropic (备选, 不填不影响)
    if os.environ.get("ANTHROPIC_API_KEY"):
        provider_block["anthropic"] = {"options": {"apiKey": "{env:ANTHROPIC_API_KEY}"}}

    return provider_block


def _build_skills_block(skills: list[str], workspace_cwd: str) -> dict:
    """skill 列表 → opencode skills.paths.

    假设 skill 已经通过 ro bind mount 挂到 workspace 下的 .skills/<name>/
    (由 Hub 端 docker create 时 -v ...:ro 完成).
    """
    if not skills:
        return {}
    paths = [f"{workspace_cwd}/.skills/{name}" for name in skills]
    return {"skills": {"paths": paths}}


def render(policy: dict) -> dict:
    """policy → opencode config dict."""
    agent = policy.get("agent", {})
    model_string = agent.get("model", "")
    workspace_cwd = os.environ.get("WORKSPACE_CWD", "/work/tenant-A/project-1")
    tool_level = policy.get("tool_level", "standard")
    skills = policy.get("skills", [])

    cfg: dict = {
        "$schema": "https://opencode.ai/config.json",
    }

    if model_string:
        provider, model_id = _resolve_provider(model_string)
        cfg["model"] = f"{provider}/{model_id}" if "/" not in model_string else model_string
        # 同时设 provider + model (opencode 两种格式都支持)
        cfg["provider"] = {provider: {"models": {model_id: {"name": model_id}}}}

    # env-based provider 配置 (key, baseURL) — 浅更新会盖掉上面设的 models 块,
    # 这里 deep merge: 把 options 合并进已有 provider, models 保留.
    env_provider = _build_provider_block(policy)
    if env_provider:
        providers = cfg.setdefault("provider", {})
        for prov_name, prov_cfg in env_provider.items():
            existing = providers.setdefault(prov_name, {})
            existing.update(prov_cfg)

    # permission
    cfg["permission"] = _TOOL_PERMISSIONS.get(tool_level, _TOOL_PERMISSIONS["standard"])

    # skills (ro bind mount 后的路径)
    if skills:
        skill_paths = [f"{workspace_cwd}/.skills/{name}" for name in skills]
        cfg["skills"] = {"paths": skill_paths}

    # MCP servers (Phase 1 v3: opencode 启动时加载, 把 LLM 调用 MCP 工具
    # 当作原生 tool, 不再走 bash+curl). 翻译自 policy["mcp_servers"] 段,
    # 严格遵循 opencode config schema (type: remote/local + url + headers).
    mcp_servers = policy.get("mcp_servers", {})
    if mcp_servers:
        cfg["mcp"] = mcp_servers
        logger.info(
            f"mcp_servers_rendered count={len(mcp_servers)} names={list(mcp_servers.keys())}"
        )

    return cfg


def main() -> int:
    parser = argparse.ArgumentParser(description="Render opencode config from policy.json")
    parser.add_argument(
        "--policy", required=True, type=Path,
        help="path to policy.runtime.json (baked + runtime overlay merged)",
    )
    parser.add_argument(
        "--policy-baked", type=Path, default=Path("/opt/sandbox/policy.json"),
        help="path to baked (immutable) policy.json, used as base layer",
    )
    parser.add_argument("--output", required=True, type=Path, help="path to write config.json")
    args = parser.parse_args()

    # 1. 读 baked 政策 (底, Dockerfile COPY 进来, ro)
    baked = _read_policy(args.policy_baked)
    # 2. 读 runtime overlay (顶, admin API 写的, rw)
    #    args.policy 一般就是 runtime overlay
    if args.policy == args.policy_baked:
        # admin server 可能传同一个 baked 路径 (没 runtime 时), 别 merge 自己
        runtime = {}
    else:
        runtime = _read_policy(args.policy)
    # 3. 合并: baked 上叠 runtime (deep merge, 浅覆深)
    policy = _deep_merge(baked, runtime)
    if runtime:
        logger.info(
            f"policy merged: baked={len(baked)} keys, runtime={len(runtime)} keys, "
            f"effective={len(policy)} keys"
        )

    cfg = render(policy)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"[render_config] wrote {args.output} ({len(cfg)} top-level keys)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
