// Todo service — wraps ``GET /agent/sessions/:id/todo`` (opencode 原生 todo
// 端点的代理). 任务清单由 LLM 通过 todowrite 工具写入, 前端用 TodoListCard
// 渲染, 用户**只读**——不提供 reply/reject。

import { http, ApiError } from './http';
import { config } from '../config';
import type { TodoItem } from '../types';

const TODO_BASE = '/agent/sessions';

function authHeaders(): Record<string, string> {
  return config.mcpToken ? { 'X-MCP-Token': config.mcpToken } : {};
}

export interface TodoListResponse {
  success: boolean;
  session_id: string;
  todos: TodoItem[];
}

export const todoService = {
  list(sessionId: string, signal?: AbortSignal) {
    return http.get<TodoListResponse>(
      `${TODO_BASE}/${encodeURIComponent(sessionId)}/todo`,
      { signal, headers: authHeaders() },
    );
  },
};

export type { ApiError };
