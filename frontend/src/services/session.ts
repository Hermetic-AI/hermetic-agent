// Session service — wraps the /agent/session endpoints.

import { http } from './http';
import type { SessionInfo } from '../types';

export interface CreateSessionRequest {
  agent_name: string;
  model?: string;
  system_prompt?: string;
  session_id?: string;
}

export interface CreateSessionResponse extends SessionInfo {
  success: true;
}

export interface SessionMessagesResponse {
  success: true;
  session_id: string;
  /** Backend returns each message as `{role, content}` objects. */
  messages: Array<{ role: string; content: string }>;
}

export interface DeleteSessionResponse {
  success: boolean;
  session_id: string;
}

const BASE = '/agent/session';

export const sessionService = {
  create(payload: CreateSessionRequest, signal?: AbortSignal) {
    return http.post<CreateSessionResponse>(BASE, payload, { signal });
  },

  get(sessionId: string, signal?: AbortSignal) {
    return http.get<SessionInfo & { success: true }>(`${BASE}/${sessionId}`, { signal });
  },

  async getMessages(sessionId: string, signal?: AbortSignal): Promise<SessionMessagesResponse> {
    return http.get<SessionMessagesResponse>(`${BASE}/${sessionId}/messages`, { signal });
  },

  delete(sessionId: string, signal?: AbortSignal) {
    return http.delete<DeleteSessionResponse>(`${BASE}/${sessionId}`, { signal });
  },

  abort(sessionId: string, signal?: AbortSignal) {
    return http.post<DeleteSessionResponse>(`${BASE}/${sessionId}/abort`, undefined, { signal });
  },
};
