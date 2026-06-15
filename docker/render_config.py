
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

    没 '/' 时走 OpenAI-compatible 默认 provider. Hub 发 chat 时固定使用
    providerID="openai", 所以 config 也必须把裸 model 注册到 provider.openai 下.
    """
    if "/" in model_string:
        provider, model_id = model_string.split("/", 1)
        return provider.strip(), model_id.strip()
    return "openai", model_string.strip()


# minimax 上游当前已知的 model 列表 — 当 policy.agent.models 没显式列时
# 兜底使用. 升级 / 新增 model 时改这里 (或 policy.agent.models 覆盖).
# 包含所有已部署的型号, 即便 policy 里 main model 只用 M2.7-highspeed, 也
# 把 M3 / M2 等列上 — 避免客户端发"M3"过来时 opencode 报 Unknown.
MINIMAX_KNOWN_MODELS = (
    "MiniMax-M2.7-highspeed",
    "MiniMax-M3",
)


def _resolve_known_models(agent: dict, *, default_model_id: str) -> list[str]:
    """Return model ids to register in ``provider.<p>.models``.

    优先级:
    1. ``agent.models`` 显式列表 (policy 可完全控制)
    2. ``MINIMAX_KNOWN_MODELS`` 兜底
    3. 至少包含 ``default_model_id`` (policy.agent.model)
    """
    raw = agent.get("models")
    if isinstance(raw, list) and raw:
        models = [str(m).strip() for m in raw if str(m).strip()]
    else:
        models = list(MINIMAX_KNOWN_MODELS)
    if default_model_id and default_model_id not in models:
        models.append(default_model_id)
    return models


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


def _truthy(value: Any) -> bool:
    """Return whether a policy/env value enables an optional feature."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _mcporter_config(policy: dict) -> dict:
    """Return normalized MCPorter policy config."""
    raw = policy.get("mcporter", {})
    return raw if isinstance(raw, dict) else {}


def _mcporter_enabled(policy: dict) -> bool:
    """Return whether the mcporter bridge should be rendered."""
    cfg = _mcporter_config(policy)
    return _truthy(cfg.get("enabled")) or _truthy(os.environ.get("MCPORTER_ENABLED"))


def _mcporter_bridge_server(policy: dict) -> dict:
    """Build the local MCP server entry that proxies through ``mcporter serve``."""
    cfg = _mcporter_config(policy)
    config_path = cfg.get("config") or os.environ.get("MCPORTER_CONFIG_PATH") or "/opt/sandbox/mcporter.json"
    upstream_servers = cfg.get("servers") or os.environ.get("MCPORTER_SERVERS") or "feihe-travel"
    if isinstance(upstream_servers, list):
        servers_arg = ",".join(str(server) for server in upstream_servers)
    else:
        servers_arg = str(upstream_servers)
    return {
        "type": "local",
        "command": [
            "mcporter",
            "serve",
            "--stdio",
            "--config",
            str(config_path),
            "--servers",
            servers_arg,
        ],
        "env": {
            "FLIGHT_API_KEY": "{env:FLIGHT_API_KEY}",
            "MCPORTER_CONFIG": str(config_path),
        },
        "enabled": True,
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
    servers.setdefault(
        "ask_user",
        {
            "type": "local",
            "command": ["python3", "/opt/sandbox/ask_user.py"],
            "enabled": True,
        },
    )
    if _mcporter_enabled(policy):
        servers.setdefault("mcporter", _mcporter_bridge_server(policy))
    flight = None if _mcporter_enabled(policy) else _flight_mcp_server_from_env()
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
        # opencode 1.16+ 解析 model 字段为 ``provider/modelID`` 格式 (slash 分隔).
        # 拆出来: provider = "openai", modelID = "MiniMax-M2.7-highspeed".
        # opencode 自己负责去 prefix, 把 modelID 单独发给 OPENAI_BASE_URL 上游.
        cfg["model"] = model_string
        # opencode 1.16.2 在没列出 model 时会硬抛 ProviderModelNotFoundError
        # (suggestions: []), 即便 OPENAI_BASE_URL 上游其实认 model. 因此我们
        # 把 policy.agent.models (或 MINIMAX_KNOWN_MODELS 兜底列表) 写进
        # provider.<provider>.models, 告诉 opencode "这些 model 我都认识".
        # 上游模型升级时, 改 MINIMAX_KNOWN_MODELS / policy.agent.models 即可.
        known_models = _resolve_known_models(agent, default_model_id=model_id)
        cfg["provider"] = {provider: {"models": {m: {"name": m} for m in known_models}}}

    # small_model: opencode 内置的 "title generator" / 轻量子任务 (例如
    # 给新 session 起标题) 默认 fallback 到一个"它认为便宜"的模型,
    # 在我们这里就是 gpt-5-nano (hardcoded fallback), minimax API 不识别
    # → 500 拉崩整个 chat 流 (opencode POST /session/{id}/message 返 500).
    # 显式把 small_model 设成 main model 同一型号, 避免 fallback.
    # policy 里 agent.small_model 不存在时默认走 main model.
    # 跟 cfg["model"] 一样: 写 ``provider/modelID`` 格式, opencode 自己拆.
    small_model_string = agent.get("small_model") or model_string
    if small_model_string:
        cfg["small_model"] = small_model_string

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
