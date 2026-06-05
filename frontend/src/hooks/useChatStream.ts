// useChatStream — drives a single chat turn against the streaming endpoint.
//
// State machine (12 SSE event types, see docs/api/scenarios.md §2.3):
//   idle       ──send()──▶ sending
//   sending    ──event:session──▶ streaming
//   streaming  ──event:text/reasoning/tool_use/tool_result──▶ streaming
//              ──event:scenario──▶ streaming (+attach scenario info)
//              ──event:card──▶ streaming/suspended (+append card)
//              ──event:state──▶ streaming (+record state transition)
//              ──event:suspend──▶ suspended (turn waiting on user input)
//              ──event:resume──▶ streaming/resuming
//              ──event:done / abort / network close──▶ idle
//              ──event:error──▶ error
//
//   suspended  ──resumeTurn(userInput, actionId)──▶ resuming ──events──▶ ...
//
// The hook owns its own AbortController.  When the backend emits a
// `suspend` event, the controller is cleared and the caller is expected
// to call `resumeTurn(...)` once the user fills out the card.

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  chatService,
  turnService,
  ApiError,
  type SendStreamOptions,
  type SendResumeStreamOptions,
} from '../services';
import type {
  ChatMessage,
  CardView,
  CardDescriptor,
  StateView,
  ScenarioView,
  StreamEvent,
  ToolEventView,
  ReasoningEventView,
} from '../types';

export type ChatStatus =
  | 'idle'
  | 'sending'
  | 'streaming'
  | 'suspended'
  | 'resuming'
  | 'error';

export interface PendingCard {
  card: CardDescriptor;
  correlation_id: string;
  turn_id: string;
  received_at: string;
}

export interface UseChatStreamOptions {
  sessionId?: string;
  /** Called with the backend-issued session id once known. */
  onSessionChange?: (id: string) => void;
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
  /** Scenario routing hint (sets `X-Scenario` header and `body.scenario`). */
  scenario?: string;
  /** Optional override for the active turn id (resumed sessions). */
  turnId?: string;
}

export interface UseChatStreamResult {
  messages: ChatMessage[];
  status: ChatStatus;
  error: string | null;
  serverSessionId: string | null;
  serverTurnId: string | null;
  scenario: ScenarioView | null;
  /** Card currently waiting for user input (set on `suspend`). */
  pendingCard: PendingCard | null;
  /** Most recent business state (Sxx). */
  currentState: string | null;
  /** True while a `suspend` has been received and the user has not yet submitted. */
  isSuspended: boolean;
  send: (content: string) => void;
  /** Submit the user response for the current pending card. */
  resumeTurn: (userInput: Record<string, unknown>, actionId?: string) => void;
  /** Cancel a running turn (server-side cancel, not just the SSE stream). */
  cancelTurn: () => Promise<void>;
  /** Stop the SSE stream locally without cancelling the server turn. */
  abort: () => void;
  reset: () => void;
}

const EMPTY_MESSAGES: ChatMessage[] = [];
const HEARTBEAT_INTERVAL_MS = 60_000;

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
  const [serverTurnId, setServerTurnId] = useState<string | null>(options.turnId ?? null);
  const [scenario, setScenario] = useState<ScenarioView | null>(null);
  const [pendingCard, setPendingCard] = useState<PendingCard | null>(null);
  const [currentState, setCurrentState] = useState<string | null>(null);

  // Refs of mutable inputs so callbacks can fire after unmount / re-render.
  const abortRef = useRef<AbortController | null>(null);
  const activeMsgIdRef = useRef<string | null>(null);
  const pendingRef = useRef<PendingCard | null>(null);
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const heartbeatTargetRef = useRef<string | null>(null);

  const optionsRef = useRef(options);
  useEffect(() => {
    optionsRef.current = options;
  }, [options]);

  useEffect(() => {
    if (options.sessionId && !serverSessionId && status === 'idle') {
      setServerSessionId(options.sessionId);
    }
  }, [options.sessionId, serverSessionId, status]);

  // --- Suspend / heartbeat helpers ---------------------------------------

  const stopHeartbeat = useCallback(() => {
    if (heartbeatRef.current) {
      clearInterval(heartbeatRef.current);
      heartbeatRef.current = null;
    }
    heartbeatTargetRef.current = null;
  }, []);

  const startHeartbeat = useCallback(
    (turnId: string) => {
      stopHeartbeat();
      heartbeatTargetRef.current = turnId;
      heartbeatRef.current = setInterval(() => {
        const target = heartbeatTargetRef.current;
        if (!target) return;
        turnService.heartbeat(target).catch(() => {
          // Heartbeat failures are non-fatal; the next resume will
          // surface a more meaningful error.
        });
      }, HEARTBEAT_INTERVAL_MS);
    },
    [stopHeartbeat],
  );

  // --- Public controls ----------------------------------------------------

  const abort = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    stopHeartbeat();
  }, [stopHeartbeat]);

  const reset = useCallback(() => {
    abort();
    setMessages(EMPTY_MESSAGES);
    setStatus('idle');
    setError(null);
    setServerSessionId(options.sessionId ?? null);
    setServerTurnId(options.turnId ?? null);
    setScenario(null);
    setPendingCard(null);
    pendingRef.current = null;
    setCurrentState(null);
  }, [abort, options.sessionId, options.turnId]);

  const send = useCallback(
    (content: string) => {
      const trimmed = content.trim();
      if (!trimmed) return;
      if (status === 'sending' || status === 'streaming' || status === 'resuming') return;
      // Clear any prior pending card; the new turn supersedes it.
      pendingRef.current = null;
      setPendingCard(null);
      stopHeartbeat();

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
        cards: [],
        stateEvents: [],
      };
      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setStatus('sending');
      setScenario(null);
      setCurrentState(null);

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
            ...(opts.scenario ? { scenario: opts.scenario } : {}),
          },
          {
            signal: ctrl.signal,
            onEvent: (event) => handleEvent(event, assistantId, opts.onSessionChange),
            onClose: ({ reason, error: closeErr }) =>
              handleClose(reason, closeErr, assistantId),
          } as SendStreamOptions,
        )
        .catch((e: unknown) => {
          if (e instanceof ApiError) setError(e.message);
          else if (e instanceof Error) setError(e.message);
        });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [serverSessionId, status, stopHeartbeat],
  );

  const resumeTurn = useCallback(
    (userInput: Record<string, unknown>, actionId?: string) => {
      const pending = pendingRef.current;
      if (!pending) {
        setError('当前没有等待中的卡片');
        return;
      }
      if (status !== 'suspended') return;

      const ctrl = new AbortController();
      abortRef.current = ctrl;
      setStatus('resuming');
      setError(null);

      // Mark the current pending card as submitted in the assistant message.
      setMessages((prev) =>
        prev.map((m) =>
          m.id === activeMsgIdRef.current
            ? {
                ...m,
                status: 'resuming',
                cards: (m.cards ?? []).map((c) =>
                  c.card_id === pending.card.card_id
                    ? { ...c, submitted: true, suspended: false }
                    : c,
                ),
              }
            : m,
        ),
      );

      // Clear local pending state — backend will emit a new card if the
      // resume path also needs user input.
      pendingRef.current = null;
      setPendingCard(null);
      stopHeartbeat();

      turnService
        .resumeStream(
          pending.turn_id,
          {
            correlation_id: pending.correlation_id,
            user_input: userInput,
            ...(actionId ? { action_id: actionId } : {}),
          },
          {
            signal: ctrl.signal,
            onEvent: (event) => handleEvent(event, activeMsgIdRef.current!, optionsRef.current.onSessionChange),
            onClose: ({ reason, error: closeErr }) =>
              handleClose(reason, closeErr, activeMsgIdRef.current!),
          } as SendResumeStreamOptions,
        )
        .catch((e: unknown) => {
          if (e instanceof ApiError) setError(e.message);
          else if (e instanceof Error) setError(e.message);
        });
    },
    // handleClose/handleEvent read mutable refs and don't need re-binding.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [status, stopHeartbeat],
  );

  const cancelTurn = useCallback(async () => {
    const tid = serverTurnId;
    abort();
    if (!tid) return;
    try {
      await turnService.cancel(tid);
    } catch (e) {
      if (e instanceof Error) setError(e.message);
    }
  }, [abort, serverTurnId]);

  // --- Event handling -----------------------------------------------------

  function handleEvent(
    event: StreamEvent,
    assistantId: string,
    onSess?: (id: string) => void,
  ): void {
    switch (event.type) {
      case 'scenario': {
        const data = event.data;
        setScenario({
          name: String(data.name ?? ''),
          version: (data.version as string | undefined) ?? undefined,
          matched_by: (data.matched_by as string | undefined) ?? undefined,
          orchestration: (data.orchestration as string | undefined) ?? undefined,
        });
        return;
      }
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
        if (!content) return;
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
        const data = event.data;
        const name = (data.name ?? data.tool_name ?? 'unknown') as string;
        const item: ToolEventView = {
          id: newId('tool'),
          name,
          phase: 'call',
          input: (data.input as Record<string, unknown> | undefined) ?? {},
          at: new Date().toISOString(),
        };
        patchAssistant(assistantId, (m) => ({
          ...m,
          toolEvents: [...(m.toolEvents ?? []), item],
        }));
        return;
      }
      case 'tool_result': {
        const data = event.data;
        const toolName = (data.name ?? data.tool_name ?? 'unknown') as string;
        const output = data.output;
        patchAssistant(assistantId, (m) => {
          const events = (m.toolEvents ?? []).slice();
          for (let i = events.length - 1; i >= 0; i -= 1) {
            if (events[i].name === toolName && events[i].phase === 'call') {
              events[i] = { ...events[i], phase: 'result', output };
              return { ...m, toolEvents: events };
            }
          }
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
      case 'card': {
        const data = event.data;
        const cardView: CardView = {
          card_id: data.card_id,
          card_type: data.card_type,
          card: data.card,
          correlation_id: data.correlation_id,
          at: new Date().toISOString(),
        };
        patchAssistant(assistantId, (m) => ({
          ...m,
          cards: [...(m.cards ?? []), cardView],
        }));
        return;
      }
      case 'state': {
        const data = event.data;
        const stateView: StateView = {
          state: String(data.state ?? ''),
          note: (data.note as string | undefined) ?? undefined,
          at: new Date().toISOString(),
        };
        setCurrentState(stateView.state);
        patchAssistant(assistantId, (m) => ({
          ...m,
          stateEvents: [...(m.stateEvents ?? []), stateView],
        }));
        return;
      }
      case 'suspend': {
        const data = event.data;
        const tid = (data.turn_id as string | undefined) ?? serverTurnId ?? '';
        if (tid) {
          setServerTurnId(tid);
          startHeartbeat(tid);
        }
        const card = data.card;
        const correlationId = data.correlation_id;
        const pending: PendingCard = {
          card,
          correlation_id: correlationId,
          turn_id: tid,
          received_at: new Date().toISOString(),
        };
        pendingRef.current = pending;
        setPendingCard(pending);
        // Mark the most recent matching card as suspended in the assistant
        // bubble so the renderer can dim the form controls.
        patchAssistant(assistantId, (m) => ({
          ...m,
          status: 'suspended',
          streaming: false,
          turnId: tid,
          pendingCorrelationId: correlationId,
          cards: (m.cards ?? []).map((c) =>
            c.card_id === card.card_id ? { ...c, suspended: true } : c,
          ),
        }));
        setStatus('suspended');
        abortRef.current = null; // stream is closed by server
        return;
      }
      case 'resume': {
        patchAssistant(assistantId, (m) => ({ ...m, status: 'resuming' }));
        setStatus('resuming');
        return;
      }
      case 'error': {
        const data = event.data;
        const message = data.message ?? 'Unknown error';
        const code = (data.code as string | undefined) ?? undefined;
        setError(message);
        patchAssistant(assistantId, (m) => ({
          ...m,
          status: 'error',
          errorMessage: code ? `[${code}] ${message}` : message,
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
    // Don't tear down heartbeat for a suspended turn — it's the only way
    // to keep the server-side timeout alive while the user reads the card.
    if (reason === 'done') {
      // If we're in a suspended state, the server "done" really just
      // means "end of this chunk of events"; don't reset to idle.
      if (pendingRef.current == null && status !== 'suspended') {
        patchAssistant(assistantId, (m) => ({ ...m, status: 'done', streaming: false }));
        setStatus('idle');
      } else {
        patchAssistant(assistantId, (m) => ({ ...m, status: 'suspended', streaming: false }));
        setStatus('suspended');
      }
      return;
    }
    if (reason === 'aborted') {
      stopHeartbeat();
      patchAssistant(assistantId, (m) => ({ ...m, status: 'aborted', streaming: false }));
      setStatus('idle');
      return;
    }
    // error
    const msg = closeErr?.message ?? 'Stream error';
    setError(msg);
    patchAssistant(assistantId, (m) => ({
      ...m,
      status: 'error',
      errorMessage: msg,
      streaming: false,
    }));
    setStatus('error');
  }

  function patchAssistant(
    id: string,
    updater: (m: ChatMessage) => ChatMessage,
  ): void {
    setMessages((prev) => prev.map((m) => (m.id === id ? updater(m) : m)));
  }

  // --- Lifecycle ----------------------------------------------------------

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      abortRef.current = null;
      stopHeartbeat();
    };
  }, [stopHeartbeat]);

  return {
    messages,
    status,
    error,
    serverSessionId,
    serverTurnId,
    scenario,
    pendingCard,
    currentState,
    isSuspended: status === 'suspended' && pendingCard != null,
    send,
    resumeTurn,
    cancelTurn,
    abort,
    reset,
  };
}
