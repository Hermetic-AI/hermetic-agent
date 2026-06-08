我已经更改了docker内部opencode的模型
curl --location --request POST '/agent/admin/opencode/opencode-core/env' \
--header 'Content-Type: */*' \
--data-raw '{
    "exists": true,
    "env": {
        "OPENAI_API_KEY": "sk-0623774bb5694418ab7335ce2b466439",
        "OPENAI_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "model":"openai/qwen3.6-flash"
    }
}'
{
    "ok": true,
    "wrote": 2,
    "next": "POST /admin/reload to apply (kills opencode, supervisor re-sources env.runtime and restarts)"
}
并且触发了重载接口
curl --location --request POST 'http://localhost:18000/agent/admin/opencode/opencode-core/policy/reload'
{
    "ok": true,
    "render": "ok",
    "restart": "sent SIGTERM to opencode pid=12",
    "next": "opencode will restart in ~1s with the new config + env"
}
curl --location --request POST 'http://localhost:7778/admin/reload'
{
    "ok": true,
    "render": "ok",
    "restart": "sent SIGTERM to opencode pid=594",
    "next": "opencode will restart in ~1s with the new config + env"
}

但是查询查当前生效的 policy (baked + runtime overlay) 还是minimax
curl --location --request GET 'http://localhost:7778/admin/policy'
{
    "baked": {
        "_comment": "Phase 1 静态 policy 文件, Hub 启动时 ro bind 进 opencode-1 容器. Phase 2 由 Hub 动态生成. 字段说明见 docker/render_config.py.",
        "policy_version": "v1",
        "scenario": "_default",
        "agent": {
            "name": "opencode",
            "model": "openai/MiniMax-M3"
        },
        "skills": [],
        "workspace_mode": "direct",
        "tool_level": "safe",
        "max_turns": 30,
        "max_budget_usd": 2.0,
查看 查当前 env.runtime 里的变量 (secret 值遮蔽为 '***') 就没问题
curl --location --request GET 'http://localhost:7778/admin/env'
{
    "runtime_path": "/tmp/opencode-sandbox/env.runtime",
    "exists": true,
    "env": {
        "exists": "True",
        "env": "{'\\''OPENAI_API_KEY'\\'': '\\''sk-0623774bb5694418ab7335ce2b466439'\\'', '\\''OPENAI_BASE_URL'\\'': '\\''https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions'\\'', '\\''model'\\'': '\\''openai/qwen3.6-flash'\\''}"
    },
    "next": "POST /admin/reload to apply (kills opencode, supervisor re-sources env and restarts)"
}