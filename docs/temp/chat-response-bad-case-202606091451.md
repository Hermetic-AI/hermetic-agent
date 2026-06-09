data: {"type": "scenario", "data": {"name": "fh_domestic_flight_booking", "version": "1.0.0", "matched_by": "header", "orchestration": "single"}}

data: {"type": "session", "data": {"session_id": "ses_154df6011ffe8UTJ8vw8bFrdRC"}}

data: {"type": "session", "data": {"session_id": "ses_154df6011ffe8UTJ8vw8bFrdRC", "agent_name": "opencode-core"}}

data: {"type": "question_asked", "data": {"request_id": "que_eab20c0d6001M4gKJc0bQ33rYO", "session_id": "ses_154df6011ffe8UTJ8vw8bFrdRC", "questions": [{"question": "您需要查询什么舱位？", "header": "舱位选择", "options": [{"label": "经济舱", "description": "经济舱"}, {"label": "商务舱/头等舱", "description": "商务舱或头等舱"}]}]}}

data: {"type": "tool_use", "data": {"tool_name": "question", "input": {"questions": [{"question": "您需要查询什么舱位？", "header": "舱位选择", "options": [{"label": "经济舱", "description": "经济舱"}, {"label": "商务舱/头等舱", "description": "商务舱或头等舱"}]}]}}}

data: {"type": "question_replied", "data": {"session_id": "ses_154df6011ffe8UTJ8vw8bFrdRC", "request_id": "que_eab20c0d6001M4gKJc0bQ33rYO", "answers": [["经济舱"]]}}

data: {"type": "tool_result", "data": {"tool_name": "question", "output": "User has answered your questions: \"您需要查询什么舱位？\"=\"经济舱\". You can now continue with the user's answers in mind."}}

data: {"type": "question_asked", "data": {"request_id": "que_eab20e11b001yr5WjMJeD60vWl", "session_id": "ses_154df6011ffe8UTJ8vw8bFrdRC", "questions": [{"question": "请选择航程类型", "header": "航程类型", "options": [{"label": "单程", "description": "单程"}, {"label": "往返", "description": "往返"}]}]}}

data: {"type": "tool_use", "data": {"tool_name": "question", "input": {"questions": [{"question": "请选择航程类型", "header": "航程类型", "options": [{"label": "单程", "description": "单程"}, {"label": "往返", "description": "往返"}]}]}}}

data: {"type": "question_replied", "data": {"session_id": "ses_154df6011ffe8UTJ8vw8bFrdRC", "request_id": "que_eab20e11b001yr5WjMJeD60vWl", "answers": [["单程"]]}}

: keepalive

data: {"type": "tool_result", "data": {"tool_name": "question", "output": "User has answered your questions: \"请选择航程类型\"=\"单程\". You can now continue with the user's answers in mind."}}

data: {"type": "question_asked", "data": {"request_id": "que_eab2141f8001nO1CmN4DknyPa2", "session_id": "ses_154df6011ffe8UTJ8vw8bFrdRC", "questions": [{"question": "出发城市是？", "header": "出发城市", "options": [{"label": "北京", "description": "北京"}]}]}}

data: {"type": "tool_use", "data": {"tool_name": "question", "input": {"questions": [{"question": "出发城市是？", "header": "出发城市", "options": [{"label": "北京", "description": "北京"}]}]}}}

