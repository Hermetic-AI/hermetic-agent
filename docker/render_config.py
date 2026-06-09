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
        "task": "deny",
        "todowrite": "deny",
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


def _flight_auth_header_value(header_name: str) -> str:
    """Return the opencode config value for the flight MCP auth header."""
    if header_name.lower() == "authorization":
        prefix = os.environ.get("FLIGHT_API_KEY_AUTH_PREFIX", "Bearer").strip()
        return f"{prefix} {{env:FLIGHT_API_KEY}}" if prefix else "{env:FLIGHT_API_KEY}"
    return "{env:FLIGHT_API_KEY}"


def _flight_mcp_server_from_env() -> dict | None:
    """Build the default feihe-travel MCP server.

    Always register the server. Auth is still read through
    ``{env:FLIGHT_API_KEY}``, but the model must be able to see the native MCP
    tools before the first per-request token write/reload succeeds.
    """
    header_name = os.environ.get("FLIGHT_API_KEY_HEADER", "token").strip() or "token"
    endpoint = os.environ.get(
        "FLIGHT_MCP_ENDPOINT",
        "https://traveldev.feiheair.com/api/mcp",
    ).strip()
    return {
        "type": "remote",
        "url": endpoint,
        "headers": {
            "Accept": "application/json,text/event-stream",
            header_name: _flight_auth_header_value(header_name),
        },
        "oauth": False,
        "enabled": True,
        "timeout": int(os.environ.get("FLIGHT_MCP_TIMEOUT_MS", "30000")),
    }


def _normalize_mcp_servers(raw: Any) -> dict:
    """Normalize project MCP config into opencode's flat v1 ``mcp`` map."""
    if not isinstance(raw, dict):
        return {}
    servers = raw.get("mcpServers") if isinstance(raw.get("mcpServers"), dict) else raw
    out: dict = {}
    for name, server in servers.items():
        if not isinstance(server, dict):
            continue
        item = dict(server)
        if item.get("type") == "http":
            item["type"] = "remote"
        if "disabled" in item and "enabled" not in item:
            item["enabled"] = not bool(item.pop("disabled"))
        out[str(name)] = item
    return out


def _build_mcp_servers(policy: dict) -> dict:
    """Merge policy MCP servers with env-driven defaults."""
    servers = _normalize_mcp_servers(policy.get("mcp_servers", {}))
    flight = _flight_mcp_server_from_env()
    if flight:
        current = servers.get("feihe-travel", {})
        if isinstance(current, dict):
            merged = {**flight, **current}
            merged_headers = {
                **flight.get("headers", {}),
                **(current.get("headers", {}) if isinstance(current.get("headers"), dict) else {}),
            }
            merged["headers"] = merged_headers
            if merged.get("type") == "http":
                merged["type"] = "remote"
            servers["feihe-travel"] = merged
        else:
            servers["feihe-travel"] = flight
    return servers


def _build_tool_output(policy: dict, *, has_mcp_servers: bool) -> dict | None:
    """Return opencode tool output limits.

    Flight MCP search can return hundreds of KB. If opencode truncates that
    output, Hub cannot assemble the AUIP FLIGHT_RESULT card from flightList.
    """
    raw = policy.get("tool_output")
    if isinstance(raw, dict):
        return raw
    if not has_mcp_servers:
        return None
    return {
        "max_lines": int(os.environ.get("OPENCODE_TOOL_OUTPUT_MAX_LINES", "12000")),
        "max_bytes": int(os.environ.get("OPENCODE_TOOL_OUTPUT_MAX_BYTES", "1048576")),
    }


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

    # MCP servers: opencode loads these as native tools, so the model calls
    # queryFlightBasic/filterFlightList directly instead of writing curl.
    mcp_servers = _build_mcp_servers(policy)
    if mcp_servers:
        cfg["mcp"] = mcp_servers
        logger.info(
            f"mcp_servers_rendered count={len(mcp_servers)} names={list(mcp_servers.keys())}"
        )
    tool_output = _build_tool_output(policy, has_mcp_servers=bool(mcp_servers))
    if tool_output:
        cfg["tool_output"] = tool_output

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
    # admin server 可能传同一个 baked 路径 (没 runtime 时), 别 merge 自己
    runtime = {} if args.policy == args.policy_baked else _read_policy(args.policy)
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
