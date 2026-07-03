// useChatSession — persists the active chat session id to localStorage
// and exposes helpers to start a new one or restore from history.

import { useCallback, useEffect, useState } from 'react';
import { sessionService, ApiError } from '../services';
import type { SessionInfo, ChatMessage } from '../types';

const STORAGE_KEY = 'hermetic_agent.session_id';

function readStoredId(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStoredId(id: string | null): void {
  try {
    if (id) window.localStorage.setItem(STORAGE_KEY, id);
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore quota / privacy errors
  }
}

export interface UseChatSessionResult {
  sessionId: string | null;
  info: SessionInfo | null;
  /** Push a freshly-issued session id into the hook (e.g. from a chat event). */
  setSessionId: (id: string | null) => void;
  /** Create a brand-new session on the backend and switch to it. */
  startNew: (agentName: string) => Promise<string>;
  /** Pull the stored messages and convert them into `ChatMessage[]`. */
  loadHistory: (id?: string) => Promise<ChatMessage[]>;
  /** Forget the current session locally; returns the id that was dropped. */
  clear: () => string | null;
}

export function useChatSession(): UseChatSessionResult {
  const [sessionId, setSessionIdState] = useState<string | null>(() => readStoredId());
  const [info, setInfo] = useState<SessionInfo | null>(null);

  const setSessionId = useCallback((id: string | null) => {
    writeStoredId(id);
    setSessionIdState(id);
    if (!id) setInfo(null);
  }, []);

  // When the id changes, try to fetch session info for display.
  useEffect(() => {
    if (!sessionId) {
      setInfo(null);
      return;
    }
    // NB: no abort signal — see HealthContext.tsx for the StrictMode
    // double-invocation rationale.  React 18 silently no-ops state updates
    // on unmounted components, so we don't need an `alive` flag.
    sessionService
      .get(sessionId)
      .then((res) => setInfo(res))
      .catch((err) => {
        setInfo(null);
        // Stale session (e.g. created before MySQL switch, or on a different
        // hub instance) returns 404 — clear the stored id so subsequent
        // refreshes don't keep retrying it.  Transient errors (network / 5xx)
        // are left alone so the next /health tick retries naturally.
        if (err instanceof ApiError && err.status === 404) {
          writeStoredId(null);
          setSessionIdState(null);
        }
      });
  }, [sessionId]);

  const startNew = useCallback(
    async (agentName: string) => {
      const res = await sessionService.create({ agent_name: agentName });
      setSessionId(res.session_id);
      setInfo(res);
      return res.session_id;
    },
    [setSessionId],
  );

  const loadHistory = useCallback(
    async (id?: string): Promise<ChatMessage[]> => {
      const target = id ?? sessionId;
      if (!target) return [];
      try {
        const res = await sessionService.getMessages(target);
        return (res.messages ?? []).map((m, idx) => ({
          id: `restored-${idx}-${Math.random().toString(36).slice(2, 8)}`,
          role:
            m.role === 'user' || m.role === 'assistant' || m.role === 'system' || m.role === 'tool'
              ? m.role
              : 'assistant',
          content: typeof m.content === 'string' ? m.content : JSON.stringify(m.content),
          timestamp: new Date().toISOString(),
          status: 'done' as const,
        }));
      } catch (e) {
        // Treat 404 as "no history" — let the user start fresh.
        if (e instanceof ApiError && e.status === 404) {
          setSessionId(null);
          return [];
        }
        throw e;
      }
    },
    [sessionId, setSessionId],
  );

  const clear = useCallback(() => {
    const dropped = sessionId;
    setSessionId(null);
    return dropped;
  }, [sessionId, setSessionId]);

  return { sessionId, info, setSessionId, startNew, loadHistory, clear };
}
