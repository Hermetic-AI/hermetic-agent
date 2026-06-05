#!/bin/bash
# opencode-sandbox 容器入口
#
# 流程:
#   1. 启动 health_server.py (后台, 端口 7777) — 供 Hub 探活
#   2. 读 /opt/sandbox/policy.json → 渲染 /root/.config/opencode/config.json
#   3. exec opencode serve (前台, 端口 14096) — 供 Hub 调 SDK
#
# 设计原则:
#   - health_server 先启, 跟 opencode 进程独立 (opencode 挂了, health 还能报状态)
#   - policy.json 走 ro bind mount, 不可写 (内核 EROFS)
#   - config.json 写在容器层, stop 保留, rm 才清
#   - 所有 LLM key 从 env 读 (docker run -e 注入), 不进 policy.json
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
POLICY_PATH="${POLICY_PATH:-/opt/sandbox/policy.json}"
CONFIG_PATH="${CONFIG_PATH:-/root/.config/opencode/config.json}"
WORKSPACE_CWD="${WORKSPACE_CWD:-/work/tenant-A/project-1}"

echo "[entrypoint] starting opencode-sandbox"
echo "[entrypoint] opencode: ${OPENCODE_HOST}:${OPENCODE_PORT}"
echo "[entrypoint] health:   ${OPENCODE_HOST}:${HEALTH_PORT}"
echo "[entrypoint] policy:   ${POLICY_PATH}"
echo "[entrypoint] config:   ${CONFIG_PATH}"
echo "[entrypoint] cwd:      ${WORKSPACE_CWD}"

# 1. 启动 health_server (后台)
echo "[entrypoint] starting health_server.py on :${HEALTH_PORT}"
python3 /opt/sandbox/health_server.py "${HEALTH_PORT}" &
HEALTH_PID=$!
echo "[entrypoint] health_server pid=${HEALTH_PID}"

# 2. 渲染 opencode config
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
    echo "[entrypoint] rendering config from policy.json"
    if ! python3 /opt/sandbox/render_config.py \
        --policy "${POLICY_PATH}" \
        --output "${CONFIG_PATH}"; then
        echo "[entrypoint] ERROR: render_config.py failed, refusing to start opencode with default config"
        echo "[entrypoint]   fix: check policy.json schema (see docker/render_config.py docstring)"
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

# 3. 确保 cwd 存在 (bind mount 一定存在, 但防止空目录导致 opencode 启动失败)
if [ ! -d "${WORKSPACE_CWD}" ]; then
    echo "[entrypoint] ERROR: workspace cwd ${WORKSPACE_CWD} does not exist"
    echo "[entrypoint] check that workspace volume mount is correct"
    exit 1
fi

# 4. 启 opencode serve (前台, 占住容器主进程)
# 注意: opencode serve 不支持 --config / --cwd 参数 (v0.1.0a36)
# - config 走默认 ~/.config/opencode/config.json (== ${CONFIG_PATH})
# - cwd 靠 cd 设
echo "[entrypoint] starting opencode serve (foreground) on :${OPENCODE_PORT}"
cd "${WORKSPACE_CWD}"
exec opencode serve \
    --port "${OPENCODE_PORT}" \
    --hostname "${OPENCODE_HOST}"
