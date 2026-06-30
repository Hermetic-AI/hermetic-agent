// Chat service — wraps the streaming and sync chat endpoints.
//
// The backend exposes a unified entry point (`/agent/chat`, `/agent/chat/stream`).
// Domain-specific routing is configured server-side; the generic frontend
// just sends the user message and lets the backend decide.

import { http, ApiError, resolveAuthToken } from './http';
import { parseSSE } from './sse';
import { config } from '../config';
import type { StreamEvent } from '../types';

// --- Request / response shapes (mirror ChatRequest / ChatResponse) ---

export interface ChatRequest {
  message: string;
  session_id?: string;
  agent_name?: string;
  model?: string;
  system_prompt?: string;
  timeout?: number;
}

export interface ChatToolCall {
  id: string;
  name: string;
  input: Record<string, unknown>;
}

export interface ChatSyncResult {
  message: { role: string; content: string };
  tool_calls: ChatToolCall[];
  stop_reason?: string | null;
}

export interface ChatResponse {
  success: boolean;
  session_id: string;
  agent_name: string;
  result: ChatSyncResult | null;
  error: string | null;
  duration: number | null;
}

export interface SendStreamOptions {
  signal?: AbortSignal;
  /** Called for every event as it arrives from the SSE stream. */
  onEvent: (event: StreamEvent) => void;
  /** Called when the stream ends (either `done` event, network close, or abort). */
  onClose?: (info: { reason: 'done' | 'aborted' | 'error'; error?: ApiError | Error }) => void;
}

const CHAT_PATH = '/agent/chat';
const CHAT_STREAM_PATH = '/agent/chat/stream';

export const chatService = {
  /**
   * Synchronous chat.  Returns the full response when the agent finishes.
   * Prefer the streaming variant for any user-facing interaction.
   */
  async send(payload: ChatRequest, signal?: AbortSignal): Promise<ChatResponse> {
    return http.post<ChatResponse>(CHAT_PATH, payload, { signal });
  },

  /**
   * Streaming chat.  Subscribes to the SSE endpoint and forwards each
   * `StreamEvent` to `onEvent`.  Resolves when the stream terminates.
   */
  async sendStream(payload: ChatRequest, opts: SendStreamOptions): Promise<void> {
    let res: Response;
    try {
      res = await fetch(buildStreamUrl(), {
        method: 'POST',
        headers: buildHeaders({ accept: 'text/event-stream' }),
        body: JSON.stringify(payload),
        signal: opts.signal,
        credentials: 'omit',
      });
    } catch (e) {
      const err =
        e instanceof DOMException && e.name === 'AbortError'
          ? new ApiError('Request aborted', 0, null)
          : new ApiError(e instanceof Error ? e.message : 'Network error', 0, null);
      opts.onClose?.({ reason: 'aborted', error: err });
      throw err;
    }

    if (!res.ok) {
      let body: unknown = null;
      try {
        body = await res.json();
      } catch {
        // ignore
      }
      const err = new ApiError(
        typeof body === 'object' && body && 'error' in body
          ? String((body as { error: unknown }).error)
          : `Request failed (HTTP ${res.status})`,
        res.status,
        body,
      );
      opts.onClose?.({ reason: 'error', error: err });
      throw err;
    }

    let lastEvent: StreamEvent | null = null;
    try {
      for await (const event of parseSSE(res)) {
        lastEvent = event;
        opts.onEvent(event);
        if (event.type === 'done') break;
      }
      // If the server terminated without an explicit `done` event, signal
      // a clean completion.  Any unmatched events on the wire are silently
      // dropped by useChatStream's switch default branch.
      const reason: 'done' | 'aborted' =
        opts.signal?.aborted
          ? 'aborted'
          : lastEvent?.type === 'done'
            ? 'done'
            : 'done';
      opts.onClose?.({ reason });
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError(e instanceof Error ? e.message : 'Stream error', 0, null);
      opts.onClose?.({ reason: 'error', error: err });
    }
  },
};

// --- Header / URL helpers (extracted so callers can reuse them) ---

export function buildStreamHeaders(_payload: ChatRequest): Record<string, string> {
  return buildHeaders({ accept: 'text/event-stream' });
}

export function buildStreamUrl(): string {
  // We have to hand-build the URL because `http.post` cannot return a
  // Response object — it auto-parses JSON.  For SSE we need the raw stream.
  const envBase = (
    (import.meta as unknown as { env: Record<string, string | undefined> }).env
      .VITE_API_BASE_URL ?? ''
  ).trim();
  const prefix = envBase ? envBase.replace(/\/+$/, '') : '/api';
  return joinUrl(prefix, CHAT_STREAM_PATH);
}

export function joinUrl(base: string, path: string): string {
  const b = base.replace(/\/+$/, '');
  const p = path.startsWith('/') ? path : `/${path}`;
  return `${b}${p}`;
}

function buildHeaders(extra: { accept: string }): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: extra.accept,
  };
  // Runtime login token preferred, build-time VITE_MCP_TOKEN fallback.
  const runtimeToken = resolveAuthToken();
  if (runtimeToken) {
    headers['X-MCP-Token'] = runtimeToken;
    headers.Authorization = `Bearer ${runtimeToken}`;
  } else if (config.mcpToken) {
    headers['X-MCP-Token'] = config.mcpToken;
  }
  return headers;
}