"""scripts/export_openapi.py — 启 server, curl /openapi/spec.json, 落 docs/openapi.json.

sanic-ext 25 的 openapi builder 不会自动挂 /openapi/spec.json 路由, 需要在
跑起来的 server 上抓. 用 subprocess 启 server, sleep 1s, 用 httpx 抓.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx


def main() -> int:
    out = Path("docs/openapi.json")
    out.parent.mkdir(parents=True, exist_ok=True)

    # 1. 启 server
    print("Starting server in background...")
    proc = subprocess.Popen(
        ["python", "-m", "hermetic_agent.main"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        # 2. 等启动
        time.sleep(3)

        # 3. 尝试抓 /openapi/spec.json
        for path in ["/openapi/spec.json", "/openapi.json", "/openapi.json/openapi.json"]:
            try:
                resp = httpx.get(f"http://127.0.0.1:8000{path}", timeout=5)
                if resp.status_code == 200 and "openapi" in resp.text:
                    spec = resp.json()
                    out.write_text(
                        json.dumps(spec, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    print(f"OK via {path}: {len(spec.get('paths', {}))} paths → {out}")
                    return 0
            except Exception as e:
                print(f"  {path}: {e}")
                continue

        # fallback: 写一个手写的 spec 包含所有已知路由
        print("Falling back to hand-written spec (server didn't expose /openapi)")
        spec = _build_handwritten_spec()
        out.write_text(
            json.dumps(spec, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"OK hand-written: {len(spec['paths'])} paths → {out}")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _build_handwritten_spec() -> dict:
    """手写 spec: 列出所有真实路由 + 文档 + 错误码 + 示例."""
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "hermetic-agent API",
            "version": "0.1.0",
            "description": (
                "OpenCode / Claude Code 双 SDK Agent 调度平台.\n\n"
                "**事件流式端点**: SSE (Content-Type: text/event-stream). 事件格式:\n"
                "`data: {\"type\": \"...\", \"data\": {...}}\\n\\n`.\n\n"
                "**Scenario 路由**: 客户端在 body.scenario 或 X-Scenario header 指定 scenario;\n"
                "否则由 ScenarioRouter 按 keyword 推断 (URL > Header > Body > Keyword > Intent > Default).\n"
                "6 个内置 scenario: `_generic` / `_default` / `flight_booking` / `expense_audit` / `customer_service` / `code_review`."
            ),
        },
        "servers": [
            {"url": "http://localhost:8000", "description": "本地开发"},
        ],
        "tags": [
            {"name": "System", "description": "健康 / 就绪检查"},
            {"name": "Chat", "description": "同步 / 流式 chat (P6: 已接 scenario + injection + HITL)"},
            {"name": "Session", "description": "Agent 会话管理"},
            {"name": "Turn", "description": "HITL Turn 生命周期 (F3)"},
            {"name": "Skills", "description": "Skill 注册与查询"},
            {"name": "Tools", "description": "MCP 工具管理"},
            {"name": "Pool", "description": "Agent 实例池"},
            {"name": "Scenarios", "description": "Scenario CRUD + 路由 (P6)"},
        ],
        "paths": {
            "/health": {
                "get": _health(),
            },
            "/ready": {
                "get": _ready(),
            },
            "/agent/chat": _chat(),
            "/agent/chat/stream": _chat_stream(),
            "/agent/session": _create_session(),
            "/agent/session/{session_id}": _get_session(),
            "/agent/session/{session_id}/messages": _get_messages(),
            "/agent/session/{session_id}": _get_session(),  # GET + DELETE 同路径
            "/agent/session/{session_id}/abort": _abort_session(),
            "/agent/skills": _skills_list(),
            "/agent/skills": _skills_register(),
            "/agent/tools": _tools_list(),
            "/agent/tools/{name}/enabled": _tool_toggle(),
            "/agent/pool/stats": _pool_stats(),
            "/agent/pool/register": _pool_register(),
            "/agent/pool/{name}": _pool_unregister(),
            "/agent/scenarios": _scenarios_list(),
            "/agent/scenarios/{name}": _scenarios_get(),
            "/agent/scenarios": _scenarios_register(),
            "/agent/scenarios/{name}": _scenarios_delete(),
            "/agent/scenarios/reload": _scenarios_reload(),
            "/agent/scenarios/{name}/validate": _scenarios_validate(),
            # 注意: 不开 /agent/scenarios/{name}/chat 入口. 全部对话统一在 /agent/chat (chat_controller.py).
            "/agent/scenarios/routing-log": _routing_log(),
            "/agent/turn/{turn_id}": _turn_get(),
            "/agent/turn/{turn_id}/events": _turn_events(),
            "/agent/turn/{turn_id}/resume": _turn_resume(),
            "/agent/turn/{turn_id}/heartbeat": _turn_heartbeat(),
            "/agent/turn/{turn_id}/cancel": _turn_cancel(),
        },
        "components": _components(),
    }


# ---- Endpoint specs (concise) ----

def _health():
    return {
        "tags": ["System"],
        "summary": "健康检查 (进程存活)",
        "responses": {"200": {"description": "{\"status\": \"ok\"}"}},
    }


def _ready():
    return {
        "tags": ["System"],
        "summary": "就绪检查 (聚合 storage / bridge / registry / scenario / turn_store / hitl)",
        "responses": {
            "200": {"description": "全部就绪"},
            "503": {"description": "missing 数组列出未就绪项"},
        },
    }


def _chat():
    return {
        "post": {
            "tags": ["Chat"],
            "summary": "发送消息并同步等待 Agent 回复 (F2: 已接 scenario + injection)",
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ChatRequest"}}},
            },
            "responses": {
                "200": {
                    "description": "成功",
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ChatResponse"}}},
                },
                "400": {"description": "scenario 路由失败 / 入参非法"},
                "500": {"description": "服务器内部错误"},
            },
        }
    }


def _chat_stream():
    return {
        "post": {
            "tags": ["Chat"],
            "summary": "发送消息并以 SSE 流式返回 (F2: 开头 emit scenario 事件, HITL 走 SuspendableScheduler)",
            "description": (
                "**事件序列**:\n"
                "1. `scenario` 事件 (matched_by / name / version / orchestration)\n"
                "2. `session` 事件 (session_id)\n"
                "3. 业务事件 (text / reasoning / tool_use / tool_result / state)\n"
                "4. 若 orchestration=hitl: `card` + `suspend` 事件后停流\n"
                "5. `done` 事件结束\n\n"
                "若 scenario 路由失败: 第一个事件是 `error` (code 字段含 12 个 code 之一)。"
            ),
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ChatRequest"}}},
            },
            "responses": {
                "200": {
                    "description": "SSE 流 (Content-Type: text/event-stream)",
                    "content": {"text/event-stream": {"schema": {"type": "string"}}},
                },
                "400": {"description": "scenario 不可用"},
            },
        }
    }


def _create_session():
    return {
        "post": {
            "tags": ["Session"],
            "summary": "创建新会话",
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/CreateSessionRequest"}}},
            },
            "responses": {"201": {"description": "会话创建成功"}},
        }
    }


def _get_session():
    return {
        "get": {"tags": ["Session"], "summary": "查询会话元信息"},
        "delete": {"tags": ["Session"], "summary": "删除会话"},
    }


def _get_messages():
    return {"get": {"tags": ["Session"], "summary": "获取会话历史消息"}}


def _abort_session():
    return {"post": {"tags": ["Session"], "summary": "中止正在运行的会话"}}


def _skills_list():
    return {"get": {"tags": ["Skills"], "summary": "列出已注册的所有 skill"}}


def _skills_register():
    return {"post": {"tags": ["Skills"], "summary": "注册/覆盖一个 skill"}}


def _tools_list():
    return {"get": {"tags": ["Tools"], "summary": "列出 MCP 工具"}}


def _tool_toggle():
    return {"patch": {"tags": ["Tools"], "summary": "启用/禁用工具"}}


def _pool_stats():
    return {"get": {"tags": ["Pool"], "summary": "Agent 实例池统计"}}


def _pool_register():
    return {"post": {"tags": ["Pool"], "summary": "注册 Agent 实例"}}


def _pool_unregister():
    return {"delete": {"tags": ["Pool"], "summary": "注销 Agent 实例"}}


def _scenarios_list():
    return {
        "get": {
            "tags": ["Scenarios"],
            "summary": "列出所有 scenario (?tag=travel 过滤)",
            "responses": {"200": {"description": "{success, total, scenarios: [...]}"}},
        }
    }


def _scenarios_get():
    return {
        "get": {
            "tags": ["Scenarios"],
            "summary": "查询单个 scenario 详情",
            "parameters": [{"name": "name", "in": "path", "required": True, "schema": {"type": "string"}}],
            "responses": {
                "200": {"description": "{success, scenario}"},
                "404": {"description": "SCENARIO_NOT_FOUND"},
            },
        }
    }


def _scenarios_register():
    return {
        "post": {
            "tags": ["Scenarios"],
            "summary": "注册/覆盖一个 scenario (YAML 或 dict body)",
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "required": ["name"],
                            "properties": {
                                "name": {"type": "string"},
                                "version": {"type": "string"},
                                "routing": {"type": "object"},
                                "execution": {"type": "object"},
                                "security": {"type": "object"},
                                "workspace": {"type": "object"},
                                "a2ui": {"type": "object"},
                                "progressive_skill": {"type": "object"},
                                "resource_dirs": {"type": "object"},
                                "resources": {"type": "object"},
                            },
                        }
                    }
                },
            },
            "responses": {
                "201": {"description": "{success, scenario, source: 'api'|'yaml'|'db'}"},
                "400": {"description": "SCENARIO_VALIDATION_FAILED / SCENARIO_WORKSPACE_FORBIDDEN"},
            },
        }
    }


def _scenarios_delete():
    return {
        "delete": {
            "tags": ["Scenarios"],
            "summary": "注销 scenario",
            "parameters": [{"name": "name", "in": "path", "required": True, "schema": {"type": "string"}}],
            "responses": {
                "200": {"description": "{success, name}"},
                "404": {"description": "SCENARIO_NOT_FOUND"},
            },
        }
    }


def _scenarios_reload():
    return {
        "post": {
            "tags": ["Scenarios"],
            "summary": "从 settings.scenario_paths 重载所有 scenario (热重载)",
            "responses": {"200": {"description": "{success, loaded: 6}"}},
        }
    }


def _scenarios_validate():
    return {
        "get": {
            "tags": ["Scenarios"],
            "summary": "校验一个 scenario (不注册) — 主要给 CI 用",
            "parameters": [{"name": "name", "in": "path", "required": True, "schema": {"type": "string"}}],
            "responses": {
                "200": {"description": "{valid: true, scenario}"},
                "400": {"description": "SCENARIO_VALIDATION_FAILED"},
            },
        }
    }




def _routing_log():
    return {
        "get": {
            "tags": ["Scenarios"],
            "summary": "查询 routing 历史 (暂 stub → 501)",
            "responses": {"501": {"description": "未实现"}},
        }
    }


def _turn_get():
    return {
        "get": {
            "tags": ["Turn"],
            "summary": "查询 Turn 状态 (session_id / skill_name / skill_version / status / created_at)",
            "parameters": [{"name": "turn_id", "in": "path", "required": True, "schema": {"type": "string"}}],
            "responses": {
                "200": {
                    "description": "{success, turn}",
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/TurnStateResponse"}}},
                },
                "404": {"description": "TURN_NOT_FOUND"},
                "503": {"description": "TURN_STORE_UNAVAILABLE"},
            },
        }
    }


def _turn_events():
    return {
        "get": {
            "tags": ["Turn"],
            "summary": "补拉 Turn 事件 (SSE, from ?after=N)",
            "description": (
                "每个事件 `data: {\"type\": \"...\", \"data\": {...}}`. 最后以 `done` "
                "(reason=replay_end, replayed=N) 结束. 用于前端 reconnect / replay."
            ),
            "parameters": [
                {"name": "turn_id", "in": "path", "required": True, "schema": {"type": "string"}},
                {"name": "after", "in": "query", "required": False, "schema": {"type": "integer", "default": 0}},
            ],
            "responses": {
                "200": {"description": "SSE 流"},
                "404": {"description": "TURN_NOT_FOUND"},
                "503": {"description": "TURN_STORE_UNAVAILABLE"},
            },
        }
    }


def _turn_resume():
    return {
        "post": {
            "tags": ["Turn"],
            "summary": "恢复一个被挂起的 Turn (HITL)",
            "description": (
                "Body: `{correlation_id, user_input, action_id}`.\n\n"
                "**事件序列** (HITL 恢复):\n"
                "1. `resume` (含 checkpoint_id)\n"
                "2. `tool_result` (ask_user 工具被回填 user_input)\n"
                "3. `state` (resume transition)\n"
                "4. `done` (end_turn)\n\n"
                "错误情况: 推送一个 `error` 事件后立即结束流."
            ),
            "parameters": [{"name": "turn_id", "in": "path", "required": True, "schema": {"type": "string"}}],
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ResumeTurnRequest"}}},
            },
            "responses": {
                "200": {"description": "SSE 流"},
                "400": {"description": "缺 correlation_id / scenario 不存在"},
                "404": {"description": "TURN_NOT_FOUND"},
                "503": {"description": "TURN_STORE_UNAVAILABLE / SCENARIO_REGISTRY_UNAVAILABLE / HITL_NOT_READY"},
            },
        }
    }


def _turn_heartbeat():
    return {
        "post": {
            "tags": ["Turn"],
            "summary": "延长 Turn 挂起超时 (前端每 60s 调一次)",
            "parameters": [{"name": "turn_id", "in": "path", "required": True, "schema": {"type": "string"}}],
            "responses": {
                "200": {"description": "{success, turn_id, status, ts}"},
                "404": {"description": "TURN_NOT_FOUND"},
            },
        }
    }


def _turn_cancel():
    return {
        "post": {
            "tags": ["Turn"],
            "summary": "取消 Turn (已 suspend 的 turn 不会再被 resume)",
            "parameters": [{"name": "turn_id", "in": "path", "required": True, "schema": {"type": "string"}}],
            "responses": {
                "200": {"description": "{success, turn_id, status: cancelled}"},
                "404": {"description": "TURN_NOT_FOUND"},
                "500": {"description": "CANCEL_FAILED"},
            },
        }
    }


def _components() -> dict:
    return {
        "schemas": {
            "ChatRequest": {
                "type": "object",
                "required": ["message"],
                "properties": {
                    "message": {"type": "string", "minLength": 1, "description": "用户消息"},
                    "session_id": {"type": "string", "description": "继续已有会话"},
                    "agent_name": {"type": "string", "description": "指定 Agent"},
                    "model": {"type": "string", "description": "指定模型 (claude-sonnet-4-5 等)"},
                    "system_prompt": {"type": "string", "description": "(被 scenario 注入覆盖)"},
                    "skills": {"type": "array", "items": {"type": "string"}, "description": "(被 scenario 白名单过滤)"},
                    "tools": {"type": "array", "items": {"type": "string"}, "description": "(被 scenario 白名单过滤)"},
                    "timeout": {"type": "number", "description": "超时秒"},
                    "scenario": {"type": "string", "description": "显式指定 scenario (URL/Header 也可)"},
                },
            },
            "ChatResponse": {
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "session_id": {"type": "string"},
                    "agent_name": {"type": "string"},
                    "result": {
                        "type": "object",
                        "properties": {
                            "message": {
                                "type": "object",
                                "properties": {
                                    "role": {"type": "string"},
                                    "content": {"type": "string"},
                                },
                            },
                            "tool_calls": {"type": "array"},
                            "stop_reason": {"type": "string"},
                        },
                    },
                    "error": {"type": "string"},
                    "duration": {"type": "number"},
                    "scenario": {
                        "type": "object",
                        "description": "F2 新增: scenario 命中信息",
                        "properties": {
                            "name": {"type": "string"},
                            "version": {"type": "string"},
                            "orchestration": {"type": "string"},
                            "matched_by": {"type": "string", "enum": ["url", "header", "body", "keyword", "intent", "default"]},
                        },
                    },
                    "routing": {
                        "type": "object",
                        "description": "F2 新增: 注入器过滤结果",
                        "properties": {
                            "matched_by": {"type": "string"},
                            "rejected_skills": {"type": "array", "items": {"type": "string"}},
                            "rejected_tools": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
            },
            "CreateSessionRequest": {
                "type": "object",
                "required": ["agent_name"],
                "properties": {
                    "agent_name": {"type": "string"},
                    "model": {"type": "string"},
                    "system_prompt": {"type": "string"},
                    "session_id": {"type": "string", "description": "指定会话 ID (用于恢复)"},
                },
            },
            "ResumeTurnRequest": {
                "type": "object",
                "required": ["correlation_id"],
                "properties": {
                    "correlation_id": {"type": "string", "description": "来自 SUSPEND 事件"},
                    "user_input": {"type": "object", "description": "用户输入 (结构由 SUSPEND.input_schema 决定)"},
                    "action_id": {"type": "string", "description": "触发的动作按钮 id"},
                },
            },
            "TurnStateResponse": {
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "turn": {
                        "type": "object",
                        "properties": {
                            "session_id": {"type": "string"},
                            "skill_name": {"type": "string"},
                            "skill_version": {"type": "string"},
                            "status": {"type": "string", "enum": ["running", "suspended", "done", "error", "cancelled"]},
                            "created_at": {"type": "string", "format": "date-time"},
                        },
                    },
                },
            },
            "ErrorResponse": {
                "type": "object",
                "properties": {
                    "success": {"type": "boolean", "default": False},
                    "code": {"type": "string", "description": "12 个 code 之一, 见 ERROR_CODES"},
                    "error": {"type": "string"},
                    "action": {"type": "string", "description": "可行动信息"},
                },
            },
        },
        "ERROR_CODES": {
            "type": "object",
            "description": "12 个 error code (见 docs/design/integrated-orchestration-plan.md §10)",
            "example": {
                "SCENARIO_NOT_FOUND": "scenario 不存在",
                "SCENARIO_DISABLED": "scenario 关闭",
                "SCENARIO_VALIDATION_FAILED": "YAML schema 校验失败",
                "SCENARIO_RESOURCE_UNAVAILABLE": "物理资源缺失 (cards_dir / SKILL.md 不存在)",
                "SCENARIO_WORKSPACE_FORBIDDEN": "workspace_dirs[0] 是 / 或 ~",
                "SKILL_NOT_ALLOWED": "caller_skills 越权",
                "TOOL_NOT_ALLOWED": "caller_tools 越权",
                "POLICY_VIOLATION": "path/command/network 违规",
                "SKILL_BUDGET_EXCEEDED": "progressive_skill 片段超 budget",
                "YAML_PLACEHOLDER_UNRESOLVED": "${...} 占位符未注入",
                "LAUNCH_FAILED": "opencode/claude_code 启动失败",
                "ROUTING_FAILED": "无 default 兜底",
            },
        },
    }


if __name__ == "__main__":
    sys.exit(main())
