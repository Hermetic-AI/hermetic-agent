// Question service — wraps ``/agent/questions/*`` endpoints (opencode 原生
// question system 的代理). 命名上独立于 chatService/turnService, 因为
// ``question`` 是 opencode 的独立子系统, 不走 HITL turn flow。

import { http, ApiError } from './http';
import { config } from '../config';
import type { QuestionItem } from '../types';

const QUESTIONS_BASE = '/agent/questions';

export interface QuestionReplyRequest {
  /** 会话 ID (用于定位 opencode client + directory) */
  session_id: string;
  /** 二维数组, 顺序与 questions[] 对应, 每项是 option label 列表 */
  answers: string[][];
}

export interface QuestionListResponse {
  success: boolean;
  session_id: string;
  questions: Array<{
    id: string;
    sessionID: string;
    questions: QuestionItem[];
    tool?: { messageID: string; callID: string };
  }>;
}

function authHeaders(): Record<string, string> {
  return config.mcpToken ? { 'X-MCP-Token': config.mcpToken } : {};
}

export const questionService = {
  /** 列出 opencode 当前 session 的 pending questions. */
  list(sessionId: string, signal?: AbortSignal) {
    return http.get<QuestionListResponse>(
      QUESTIONS_BASE,
      { query: { session_id: sessionId }, signal, headers: authHeaders() },
    );
  },

  /** 提交答案. 成功 (200) 表示 opencode 接受了. */
  reply(requestId: string, body: QuestionReplyRequest, signal?: AbortSignal) {
    return http.post<{ success: boolean; request_id: string; replied: boolean }>(
      `${QUESTIONS_BASE}/${encodeURIComponent(requestId)}/reply`,
      body,
      { signal, headers: authHeaders() },
    );
  },

  /** 忽略/拒绝 (前端"忽略"按钮). */
  reject(requestId: string, sessionId: string, signal?: AbortSignal) {
    return http.post<{ success: boolean; request_id: string; rejected: boolean }>(
      `${QUESTIONS_BASE}/${encodeURIComponent(requestId)}/reject`,
      { session_id: sessionId },
      { signal, headers: authHeaders() },
    );
  },
};

export type { ApiError };
