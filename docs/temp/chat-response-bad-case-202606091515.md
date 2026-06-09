data: {"type": "scenario", "data": {"name": "fh_domestic_flight_booking", "version": "1.0.0", "matched_by": "header", "orchestration": "single"}}

data: {"type": "session", "data": {"session_id": "ses_154c4c0e5ffexykPlfPFfztxe3"}}

data: {"type": "session", "data": {"session_id": "ses_154c4c0e5ffexykPlfPFfztxe3", "agent_name": "opencode-core"}}

data: {"type": "todo_updated", "data": {"session_id": "ses_154c4c0e5ffexykPlfPFfztxe3", "todos": [{"content": "查询北京到上海2026-06-10单程机票", "status": "in_progress", "priority": "high"}]}}

data: {"type": "tool_use", "data": {"tool_name": "todowrite", "input": {"todos": [{"content": "查询北京到上海2026-06-10单程机票", "status": "in_progress", "priority": "high"}]}}}

data: {"type": "tool_result", "data": {"tool_name": "todowrite", "output": "[\n  {\n    \"content\": \"查询北京到上海2026-06-10单程机票\",\n    \"status\": \"in_progress\",\n    \"priority\": \"high\"\n  }\n]"}}

data: {"type": "tool_use", "data": {"tool_name": "invalid", "input": {"tool": "call_mcp_tool", "error": "Model tried to call unavailable tool 'call_mcp_tool'. Available tools: invalid, todowrite."}}}

data: {"type": "tool_result", "data": {"tool_name": "invalid", "output": "The arguments provided to the tool are invalid: Model tried to call unavailable tool 'call_mcp_tool'. Available tools: invalid, todowrite."}}

data: {"type": "text", "data": {"content": "抱歉，当前环境未配置航班查询MCP工具，无法完成查询。请联系管理员检查opencode MCP配置。"}}

data: {"type": "done", "data": {}}

data: {"type": "done", "data": {}}

