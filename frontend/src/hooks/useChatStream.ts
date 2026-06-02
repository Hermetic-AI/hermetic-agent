// useChatStream — drives a single chat turn against the streaming endpoint.
//
// State machine:
//   idle  ──send()──▶ sending ──first event──▶ streaming
//   streaming       ──event:text──▶ streaming (text appended)
//                   ──event:tool_use/result──▶ streaming (tool event recorded)
//                   ──event:done / abort / error──▶ idle
//
// The hook owns its own AbortController and exposes:
//   - messages: ChatMessage[] (excludes transient `streaming` state)
//   - status: 'idle' | 'sending' | 'streaming' | 'error'
//   - error: string | null
//   - send(content): void
//   - abort(): void
//   - reset(): void
//
// The `sessionId` argument is optional; when provided, every message is
// sent with that session.  When omitted, the backend auto-creates one
// and the resulting id is exposed via `serverSessionId`.

import { useCallback, useEffect, useRef, useState } from 'react';
import { chatService, ApiError } from '../services';
import type { ChatMessage, StreamEvent, ToolEventView, ReasoningEventView } from '../types';

export type ChatStatus = 'idle' | 'sending' | 'streaming' | 'error';

export interface UseChatStreamOptions {
  sessionId?: string;
  /** Called with the backend-issued session id once known. */
  onSessionChange?: (sessionId: string) => void;
  /** Optional prompt prefix / system context appended to every user message. */
  systemPrompt?: string;
  /** Skills to enable for the run. */
  skills?: string[];
  /** Tools to enable for the run. */
  tools?: string[];
  /** Per-request timeout (seconds). */
  timeout?: number;
  /** Model hint forwarded to the backend. */
  model?: string;
  /** Agent instance to target. */
  agentName?: string;
}

export interface UseChatStreamResult {
  messages: ChatMessage[];
  status: ChatStatus;
  error: string | null;
  serverSessionId: string | null;
  send: (content: string) => void;
  abort: () => void;
  reset: () => void;
}

const EMPTY_MESSAGES: ChatMessage[] = [];

function newId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export function useChatStream(options: UseChatStreamOptions = {}): UseChatStreamResult {
  const [messages, setMessages] = useState<ChatMessage[]>(EMPTY_MESSAGES);
  const [status, setStatus] = useState<ChatStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const [serverSessionId, setServerSessionId] = useState<string | null>(
    options.sessionId ?? null,
  );

  // Keep a ref of mutable inputs so abort() can run after unmount.
  const abortRef = useRef<AbortController | null>(null);
  const activeMsgIdRef = useRef<string | null>(null);

  // Track the latest options in a ref so callbacks don't need to re-bind
  // every time the parent re-renders.
  const optionsRef = useRef(options);
  useEffect(() => {
    optionsRef.current = options;
  }, [options]);

  // Keep serverSessionId in sync with the input prop, but only when idle
  // (so we don't clobber a session the backend just returned mid-stream).
  useEffect(() => {
    if (options.sessionId && !serverSessionId && status === 'idle') {
      setServerSessionId(options.sessionId);
    }
  }, [options.sessionId, serverSessionId, status]);

  const abort = useCallback(() => {
    const ctrl = abortRef.current;
    if (ctrl) {
      ctrl.abort();
      abortRef.current = null;
    }
  }, []);

  const reset = useCallback(() => {
    abort();
    setMessages(EMPTY_MESSAGES);
    setStatus('idle');
    setError(null);
    setServerSessionId(null);
  }, [abort]);

  const send = useCallback(
    (content: string) => {
      const trimmed = content.trim();
      if (!trimmed) return;
      if (status === 'sending' || status === 'streaming') return;

      const ctrl = new AbortController();
      abortRef.current = ctrl;
      setError(null);

      const userMsg: ChatMessage = {
        id: newId('user'),
        role: 'user',
        content: trimmed,
        timestamp: new Date().toISOString(),
      };
      const assistantId = newId('assistant');
      activeMsgIdRef.current = assistantId;
      const assistantMsg: ChatMessage = {
        id: assistantId,
        role: 'assistant',
        content: '',
        timestamp: new Date().toISOString(),
        streaming: true,
        status: 'sending',
        toolEvents: [],
        reasoningEvents: [],
      };
      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setStatus('sending');

      const opts = optionsRef.current;
      const reqSessionId = serverSessionId ?? opts.sessionId;

      chatService
        .sendStream(
          {
            message: trimmed,
            ...(reqSessionId ? { session_id: reqSessionId } : {}),
            ...(opts.agentName ? { agent_name: opts.agentName } : {}),
            ...(opts.model ? { model: opts.model } : {}),
            ...(opts.systemPrompt ? { system_prompt: opts.systemPrompt } : {}),
            ...(opts.timeout ? { timeout: opts.timeout } : {}),
            ...(opts.skills?.length ? { skills: opts.skills } : {}),
            ...(opts.tools?.length ? { tools: opts.tools } : {}),
          },
          {
            signal: ctrl.signal,
            onEvent: (event) => handleEvent(event, assistantId, opts.onSessionChange),
            onClose: ({ reason, error: closeErr }) =>
              handleClose(reason, closeErr, assistantId),
          },
        )
        .catch((e: unknown) => {
          // Network/parse errors.  `handleClose` is the source of truth
          // for the visible state; this catch is a safety net.
          if (e instanceof ApiError) {
            setError(e.message);
          } else if (e instanceof Error) {
            setError(e.message);
          }
        });
    },
    // `handleEvent` and `handleClose` intentionally read mutable refs and
    // do not need to be re-bound on every render; pinning the dep array
    // keeps `send` stable for consumers.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [serverSessionId, status],
  );

  function handleEvent(
    event: StreamEvent,
    assistantId: string,
    onSess?: (id: string) => void,
  ): void {
    switch (event.type) {
      case 'session': {
        const sid = event.data.session_id;
        if (sid) {
          setServerSessionId(sid);
          onSess?.(sid);
        }
        setStatus('streaming');
        patchAssistant(assistantId, (m) => ({ ...m, status: 'streaming' }));
        return;
      }
      case 'text': {
        const chunk = event.data.content ?? '';
        if (!chunk) return;
        setStatus('streaming');
        patchAssistant(assistantId, (m) => ({
          ...m,
          content: m.content + chunk,
          status: 'streaming',
        }));
        return;
      }
      case 'reasoning': {
        const content = event.data.content ?? '';
        const item: ReasoningEventView = {
          id: newId('reasoning'),
          content,
          at: new Date().toISOString(),
        };
        patchAssistant(assistantId, (m) => ({
          ...m,
          reasoningEvents: [...(m.reasoningEvents ?? []), item],
        }));
        return;
      }
      case 'tool_use': {
        const item: ToolEventView = {
          id: newId('tool'),
          name: event.data.tool_name,
          phase: 'call',
          input: event.data.input ?? {},
          at: new Date().toISOString(),
        };
        patchAssistant(assistantId, (m) => ({
          ...m,
          toolEvents: [...(m.toolEvents ?? []), item],
        }));
        return;
      }
      case 'tool_result': {
        const toolName = event.data.tool_name;
        const output = event.data.output;
        patchAssistant(assistantId, (m) => {
          // Attach the result to the most recent matching `call`.
          const events = (m.toolEvents ?? []).slice();
          for (let i = events.length - 1; i >= 0; i -= 1) {
            if (events[i].name === toolName && events[i].phase === 'call') {
              events[i] = { ...events[i], phase: 'result', output };
              return { ...m, toolEvents: events };
            }
          }
          // No preceding call — append a synthetic result.
          events.push({
            id: newId('tool'),
            name: toolName,
            phase: 'result',
            output,
            at: new Date().toISOString(),
          });
          return { ...m, toolEvents: events };
        });
        return;
      }
      case 'error': {
        const message = event.data.message ?? 'Unknown error';
        setError(message);
        patchAssistant(assistantId, (m) => ({
          ...m,
          status: 'error',
          errorMessage: message,
        }));
        return;
      }
      case 'done':
        // Final state is set in `handleClose`.
        return;
    }
  }

  function handleClose(
    reason: 'done' | 'aborted' | 'error',
    closeErr: ApiError | Error | undefined,
    assistantId: string,
  ): void {
    abortRef.current = null;
    activeMsgIdRef.current = null;
    if (reason === 'aborted') {
      patchAssistant(assistantId, (m) => ({ ...m, status: 'aborted', streaming: false }));
      setStatus('idle');
      return;
    }
    if (reason === 'error') {
      const msg = closeErr?.message ?? 'Stream error';
      setError(msg);
      patchAssistant(assistantId, (m) => ({
        ...m,
        status: 'error',
        errorMessage: msg,
        streaming: false,
      }));
      setStatus('error');
      return;
    }
    // 'done'
    patchAssistant(assistantId, (m) => ({ ...m, status: 'done', streaming: false }));
    setStatus('idle');
  }

  function patchAssistant(
    id: string,
    updater: (m: ChatMessage) => ChatMessage,
  ): void {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? updater(m) : m)),
    );
  }

  // Cancel any active stream on unmount.
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      abortRef.current = null;
    };
  }, []);

  return { messages, status, error, serverSessionId, send, abort, reset };
}
