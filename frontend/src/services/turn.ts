// Turn service — wraps the `/agent/turn/*` endpoints used for HITL flows.
//
// Lifecycle:
//   1. Client sends a chat → backend emits a `suspend` SSE event with
//      { turn_id, checkpoint_id, correlation_id, card }.
//   2. User fills out the card and clicks submit.
//   3. Client posts to `/agent/turn/{turnId}/resume` with
//      { correlation_id, user_input, action_id }.
//   4. Backend replays the turn from the checkpoint, yielding a fresh SSE
//      stream (resume → tool_result → ... → next card / done).
//
// The streaming variant (`resumeStream`) reuses the SSE parser and
// supports an `AbortSignal` for cancellation.

import { http, ApiError, resolveAuthToken } from './http';
import { joinUrl } from './chat';
import { parseSSE } from './sse';
import { config } from '../config';
import type { ResumeRequest, StreamEvent, TurnInfo } from '../types';

const TURN_BASE = '/agent/turn';

export interface SendResumeStreamOptions {
  signal?: AbortSignal;
  onEvent: (event: StreamEvent) => void;
  onClose?: (info: { reason: 'done' | 'aborted' | 'error'; error?: ApiError | Error }) => void;
}

function buildResumeStreamUrl(turnId: string): string {
  const envBase = (
    (import.meta as unknown as { env: Record<string, string | undefined> }).env
      .VITE_API_BASE_URL ?? ''
  ).trim();
  const prefix = envBase ? envBase.replace(/\/+$/, '') : '/api';
  return joinUrl(prefix, `${TURN_BASE}/${turnId}/resume`);
}

export const turnService = {
  /** Query a turn's current state. */
  get(turnId: string, signal?: AbortSignal) {
    return http.get<{ success: boolean; turn: TurnInfo }>(
      `${TURN_BASE}/${turnId}`,
      { signal },
    );
  },

  /** Resume a suspended turn with the user's structured input. */
  resume(turnId: string, body: ResumeRequest, signal?: AbortSignal) {
    return http.post<{ success: boolean; turn_id: string; status?: string }>(
      `${TURN_BASE}/${turnId}/resume`,
      body,
      { signal },
    );
  },

  /** Stream the resume as SSE — receives `resume`, `tool_result`, next `card`, etc. */
  async resumeStream(turnId: string, body: ResumeRequest, opts: SendResumeStreamOptions): Promise<void> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    };
    // 跟 chat.ts 保持一致: 运行时 login token 优先, build-time 兜底
    const runtimeToken = resolveAuthToken();
    if (runtimeToken) {
      headers['X-MCP-Token'] = runtimeToken;
      headers.Authorization = `Bearer ${runtimeToken}`;
    } else if (config.mcpToken) {
      headers['X-MCP-Token'] = config.mcpToken;
    }
    let res: Response;
    try {
      res = await fetch(buildResumeStreamUrl(turnId), {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
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
      let responseBody: unknown = null;
      try {
        responseBody = await res.json();
      } catch {
        // ignore
      }
      const err = new ApiError(
        typeof responseBody === 'object' && responseBody && 'error' in responseBody
          ? String((responseBody as { error: unknown }).error)
          : `Request failed (HTTP ${res.status})`,
        res.status,
        responseBody,
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

  /** Extend a suspended turn's timeout (call every ~60s). */
  heartbeat(turnId: string, signal?: AbortSignal) {
    return http.post<{ success: boolean; turn_id: string; status: string; ts: number }>(
      `${TURN_BASE}/${turnId}/heartbeat`,
      undefined,
      { signal },
    );
  },

  /** Cancel a turn. */
  cancel(turnId: string, signal?: AbortSignal) {
    return http.post<{ success: boolean; turn_id: string; status: string }>(
      `${TURN_BASE}/${turnId}/cancel`,
      undefined,
      { signal },
    );
  },

  /** Replay missed events (seq > `after`). */
  eventsStreamUrl(turnId: string, after?: number): string {
    const envBase = (
      (import.meta as unknown as { env: Record<string, string | undefined> }).env
        .VITE_API_BASE_URL ?? ''
    ).trim();
    const prefix = envBase ? envBase.replace(/\/+$/, '') : '/api';
    const base = joinUrl(prefix, `${TURN_BASE}/${turnId}/events`);
    return after != null ? `${base}?after=${after}` : base;
  },
};
