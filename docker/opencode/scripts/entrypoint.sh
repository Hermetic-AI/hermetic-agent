#!/bin/bash
# opencode-sandbox 容器入口
#
# 流程:
#   1. 启动 health_server.py (后台, 端口 7777) — 供 Hub 探活
#   2. 启动 admin_server.py  (后台, 端口 7778) — 供 Hub 改 policy / reload opencode
#   3. 读 /opt/sandbox/policy.json (+ runtime overlay) → 渲染 config.json
#   4. supervisor 循环启 opencode serve (前台子进程) — admin 发 SIGTERM 触发重启
#
# 设计原则:
#   - health + admin 先启, 跟 opencode 进程独立 (opencode 挂了, sidecar 还能报状态)
#   - policy.json 走 ro bind mount / image bake, 不可写 (内核 EROFS)
#   - config.json 写在容器层, stop 保留, rm 才清
#   - 所有 LLM key 从 env 读 (docker run -e 注入), 不进 policy.json
#   - admin_server 通过 SIGTERM opencode 触发 reload; supervisor 自动拉起
#
# 退出码:
#   0  = 正常 SIGTERM
#   1  = 配置错误 (policy 缺字段, opencode 装错等)
#   143 = SIGTERM (docker stop 发的)
#   137 = SIGKILL (OOM 等)

set -e

OPENCODE_PORT="${OPENCODE_PORT:-14096}"
# 默认 0.0.0.0: 容器是给 Hub 在同 docker 网络里调的, 只绑 127.0.0.1 Hub ping 不通
# 想只绑 loopback (调试用): docker run -e OPENCODE_HOST=127.0.0.1
OPENCODE_HOST="${OPENCODE_HOST:-0.0.0.0}"
HEALTH_PORT="${HEALTH_PORT:-7777}"
ADMIN_PORT="${ADMIN_PORT:-7778}"
POLICY_PATH="${POLICY_PATH:-/opt/sandbox/policy.json}"
POLICY_RUNTIME_PATH="${POLICY_RUNTIME_PATH:-/tmp/opencode-sandbox/policy.runtime.json}"
ENV_RUNTIME_PATH="${ENV_RUNTIME_PATH:-/tmp/opencode-sandbox/env.runtime}"
CONFIG_PATH="${CONFIG_PATH:-/root/.config/opencode/config.json}"
WORKSPACE_CWD="${WORKSPACE_CWD:-/work/tenant-A/project-1}"

echo "[entrypoint] starting opencode-sandbox"
echo "[entrypoint] opencode: ${OPENCODE_HOST}:${OPENCODE_PORT}"
echo "[entrypoint] health:   ${OPENCODE_HOST}:${HEALTH_PORT}"
echo "[entrypoint] admin:    ${OPENCODE_HOST}:${ADMIN_PORT}"
echo "[entrypoint] policy:   ${POLICY_PATH} (+ overlay ${POLICY_RUNTIME_PATH})"
echo "[entrypoint] env:      ${ENV_RUNTIME_PATH} (admin API 写的 KEY=VALUE, source 后启 opencode; named volume, recreate 保留)"
echo "[entrypoint] config:   ${CONFIG_PATH}"
echo "[entrypoint] cwd:      ${WORKSPACE_CWD}"

# 0. 容器启动时 source 一次 env (为了 health_server / admin_server 也能读到新 key,
#    例如 admin 自身如果想验证 key 是否生效, 或者 health 探活时调一次 opencode health)
#    注意: **真正的 opencode serve 在 supervisor 循环里会 re-source** (line 137+),
#    所以 reload 后的新 env 一定生效.
if [ -f "${ENV_RUNTIME_PATH}" ]; then
    echo "[entrypoint] sourcing runtime env from ${ENV_RUNTIME_PATH}"
    # shellcheck disable=SC1090
    set -a  # auto-export 所有赋值的变量
    # shellcheck disable=SC1090
    . "${ENV_RUNTIME_PATH}"
    set +a
fi

# 1. 启动 health_server (后台)
echo "[entrypoint] starting health_server.py on :${HEALTH_PORT}"
python3 /opt/sandbox/health_server.py "${HEALTH_PORT}" &
HEALTH_PID=$!
echo "[entrypoint] health_server pid=${HEALTH_PID}"

# 2. 启动 admin_server (后台)
echo "[entrypoint] starting admin_server.py on :${ADMIN_PORT}"
python3 /opt/sandbox/admin_server.py "${ADMIN_PORT}" &
ADMIN_PID=$!
echo "[entrypoint] admin_server pid=${ADMIN_PID}"

# 3. 渲染 opencode config (baked + runtime overlay)
#
# 防御要点: 区分"policy 不存在"和"policy 不是 regular file".
# 历史踩坑: docker Desktop + WSL2 路径下, bind mount 一个文件到
# 已存在的目录路径时, 目标会被建为**空目录**而不是覆盖原文件,
# entrypoint 的 `[ -f ]` 测试会返回 false, 触发 silent fall back
# 到 opencode defaults — opencode defaults 走它自己的模型表
# (gpt-5.3-chat-latest 等 Zen 专用), 然后被 LLM provider 拒.
# 这里显式检查, 任何"路径存在但不是 regular file"的情况都报错退出.
if [ -e "${POLICY_PATH}" ]; then
    if [ ! -f "${POLICY_PATH}" ]; then
        echo "[entrypoint] ERROR: ${POLICY_PATH} exists but is not a regular file"
        echo "[entrypoint]   type: $(stat -c '%F' "${POLICY_PATH}" 2>/dev/null || stat -f '%HT' "${POLICY_PATH}")"
        echo "[entrypoint]   likely cause: docker Desktop + WSL2 bind mount quirk,"
        echo "[entrypoint]   the target path was a directory and the source file failed to mount over it."
        echo "[entrypoint]   fix: docker compose up -d --force-recreate --no-deps opencode-1"
        exit 1
    fi
    echo "[entrypoint] rendering config from policy.json (+ runtime overlay if any)"
    # render_config.py 现在会自己合并 baked + runtime; 直接传 runtime 路径即可
    if ! python3 /opt/sandbox/render_config.py \
        --policy "${POLICY_RUNTIME_PATH}" \
        --policy-baked "${POLICY_PATH}" \
        --output "${CONFIG_PATH}"; then
        echo "[entrypoint] ERROR: render_config.py failed, refusing to start opencode with default config"
        echo "[entrypoint]   fix: check policy.json schema (see docker/opencode/scripts/render_config.py docstring)"
        exit 1
    fi
    # 防御: 渲染后的 config 必须存在 + 非空 + 合法 JSON + 含 model 字段
    if [ ! -s "${CONFIG_PATH}" ]; then
        echo "[entrypoint] ERROR: ${CONFIG_PATH} is missing or empty after render"
        exit 1
    fi
    if ! python3 -c "import json,sys; c=json.load(open('${CONFIG_PATH}')); assert 'model' in c, 'no model field'" 2>/dev/null; then
        echo "[entrypoint] ERROR: ${CONFIG_PATH} is not valid JSON or has no 'model' field"
        echo "[entrypoint]   content (first 200 chars):"
        head -c 200 "${CONFIG_PATH}" 2>/dev/null | sed 's/^/[entrypoint]     /'
        exit 1
    fi
    echo "[entrypoint] config rendered OK: ${CONFIG_PATH}"
else
    echo "[entrypoint] WARN: policy.json not found at ${POLICY_PATH}, using opencode defaults"
    echo "[entrypoint]   this is OK for ad-hoc docker run, but in compose the bind mount may have failed"
fi

# 防御: 如果 config 里有 model 字段 (即走了 policy.json 路径), 但
# OPENAI_API_KEY 没设, opencode 会带空 key 调 LLM → 401. 显式告警.
if [ -s "${CONFIG_PATH}" ] && [ -z "${OPENAI_API_KEY:-}" ] && [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo "[entrypoint] WARN: model config rendered but neither OPENAI_API_KEY nor ANTHROPIC_API_KEY is set"
    echo "[entrypoint]   opencode will start but every LLM call will return 401"
fi

# 3.5. mcporter 初始化: 注册业务 MCP 服务器 (mcporter call 模式)
# --transport http: 业务 MCP 端点使用 Streamable HTTP (非 SSE)
# --scope home: 写入 ~/.mcporter/mcporter.json (容器 tmpfs, restart 清空后会重新注册)
# MCP_TOKEN 由 docker-compose env 注入
# MCPORTER_SERVERS 是个 list, e.g. "my-mcp-1,my-mcp-2"
if command -v mcporter &> /dev/null && [ -n "${MCPORTER_SERVERS:-}" ]; then
    IFS=',' read -ra SERVERS <<< "$MCPORTER_SERVERS"
    for srv in "${SERVERS[@]}"; do
        srv=$(echo "$srv" | xargs)  # trim
        [ -z "$srv" ] && continue
        endpoint_var="MCPORTER_${srv^^}_ENDPOINT"
        endpoint="${!endpoint_var}"
        if [ -z "$endpoint" ]; then
            echo "[entrypoint] WARN: no endpoint for mcporter server '$srv' (set $endpoint_var)"
            continue
        fi
        echo "[entrypoint] initializing mcporter for $srv ($endpoint)"
        mcporter config add "$srv" "$endpoint" \
            --header "token=${MCP_TOKEN:-}" \
            --transport http \
            --scope home 2>/dev/null || {
            echo "[entrypoint] WARN: mcporter config add failed; 'mcporter call $srv ...' will not work"
        }
    done
    echo "[entrypoint] mcporter servers registered:"
    mcporter list 2>&1 | head -5 || true
else
    echo "[entrypoint] WARN: mcporter not found or MCPORTER_SERVERS empty; 'mcporter call' commands will fail"
fi

# 3.6. 确保 cwd 存在 (bind mount 一定存在, 但防止空目录导致 opencode 启动失败)
if [ ! -d "${WORKSPACE_CWD}" ]; then
    echo "[entrypoint] ERROR: workspace cwd ${WORKSPACE_CWD} does not exist"
    echo "[entrypoint] check that workspace volume mount is correct"
    exit 1
fi

# 4. supervisor 循环: 启 opencode serve, 死掉自动拉起
# 这样 admin_server 可以发 SIGTERM 触发 reload (新的 config 生效),
# supervisor 会立刻 restart opencode, 整个 reload 流程 ~1s.
#
# 注意: opencode serve 不支持 --config / --cwd 参数 (v0.1.0a36)
# - config 走默认 ~/.config/opencode/config.json (== ${CONFIG_PATH})
# - cwd 靠 cd 设
cd "${WORKSPACE_CWD}"
echo "[entrypoint] supervisor starting; opencode will run on :${OPENCODE_PORT}"
while true; do
    # 每次重启前重新 source 一次 env.runtime, 确保 admin 写的新 KEY/URL 生效.
    # 没文件就静默跳过 (用 docker-compose 注入的 env).
    if [ -f "${ENV_RUNTIME_PATH}" ]; then
        # shellcheck disable=SC1090
        set -a
        # shellcheck disable=SC1090
        . "${ENV_RUNTIME_PATH}"
        set +a
    fi
    # 也 re-render 一次 config (baked + runtime overlay 合并)
    if [ -f "${POLICY_PATH}" ]; then
        python3 /opt/sandbox/render_config.py \
            --policy "${POLICY_RUNTIME_PATH}" \
            --policy-baked "${POLICY_PATH}" \
            --output "${CONFIG_PATH}" >/dev/null 2>&1 || true
    fi
    echo "[entrypoint] (re)starting opencode serve on :${OPENCODE_PORT}"
    opencode serve \
        --port "${OPENCODE_PORT}" \
        --hostname "${OPENCODE_HOST}" \
        --print-logs \
        --log-level "${OPENCODE_LOG_LEVEL:-DEBUG}" || true
    echo "[entrypoint] opencode exited, restarting in 1s (config + env will be re-read on next start)"
    sleep 1
done
