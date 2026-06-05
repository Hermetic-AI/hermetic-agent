data: {"type": "scenario", "data": {"name": "flight_query", "version": "1.1.0", "matched_by": "header", "orchestration": "single"}}

data: {"type": "session", "data": {"session_id": "ses_1697c3a70ffeYWADFa771vuHK0"}}

data: {"type": "session", "data": {"session_id": "ses_1697c3a70ffeYWADFa771vuHK0", "agent_name": "opencode-core"}}

data: {"type": "text", "data": {"content": "好的,正在查询 2026-06-06 北京→上海、2026-06-12 上海→北京 的航班。"}}

data: {"type": "tool_use", "data": {"tool_name": "invalid", "input": {"tool": "bash", "error": "Model tried to call unavailable tool 'bash'. Available tools: glob, grep, invalid, question, read, skill, task, todowrite."}}}

data: {"type": "tool_result", "data": {"tool_name": "invalid", "output": "The arguments provided to the tool are invalid: Model tried to call unavailable tool 'bash'. Available tools: glob, grep, invalid, question, read, skill, task, todowrite."}}

data: {"type": "tool_use", "data": {"tool_name": "invalid", "input": {"tool": "bash", "error": "Model tried to call unavailable tool 'bash'. Available tools: glob, grep, invalid, question, read, skill, task, todowrite."}}}

data: {"type": "tool_result", "data": {"tool_name": "invalid", "output": "The arguments provided to the tool are invalid: Model tried to call unavailable tool 'bash'. Available tools: glob, grep, invalid, question, read, skill, task, todowrite."}}

data: {"type": "text", "data": {"content": ""}}

data: {"type": "text", "data": {"content": "抱歉,当前会话没有 `bash` 工具,无法直接发起 curl 调用 MCP。\n\n请确认环境配置(`ask_user` MCP 节点 / native MCP 工具)是否启用,或由 Hub 侧完成 MCP 调用后再让我整理结果卡片。"}}

data: {"type": "done", "data": {}}





data: {"type": "scenario", "data": {"name": "flight_query_v3", "version": "1.0.0", "matched_by": "header", "orchestration": "single"}}

data: {"type": "session", "data": {"session_id": "ses_1697c3a70ffeYWADFa771vuHK0"}}

data: {"type": "session", "data": {"session_id": "ses_1697c3a70ffeYWADFa771vuHK0", "agent_name": "opencode-core"}}

data: {"type": "text", "data": {"content": "好的,已按 2026-06-06 北京→上海 查询。"}}

data: {"type": "tool_use", "data": {"tool_name": "skill", "input": {"name": "flight-query"}}}

data: {"type": "text", "data": {"content": ""}}

data: {"type": "text", "data": {"content": "抱歉,当前会话环境没有加载到 `queryFlightBasic` / `ask_user` 工具,也未提供 `bash`(无法 curl MCP)。请确认:\n\n- `work/mcp/servers.json` 中 `feihe-travel` 是否已配置\n- opencode 启动时 MCP 工具是否成功注入(检查 `mcp` 节点日志)\n\n环境就绪后我再发起查询并返回 FLIGHT_RESULT 卡片。"}}

data: {"type": "done", "data": {}}

