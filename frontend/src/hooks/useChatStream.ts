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
  QuestionView,
  QuestionItem,
  TodoView,
  TodoItem,
} from '../types';
import {
  appendCard,
  appendQuestion,
  appendReasoning,
  appendState,
  appendText,
  appendToolCall,
  markQuestionRejected,
  markQuestionSubmitted,
  suspendCard,
  updateToolResult,
} from './chatEvents';

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
  /**
   * Called when the backend reports the current session is gone (typically
   * because the server was restarted and lost its in-memory store, but the
   * localStorage entry is still around).  Should clear the local session id
   * so the next send creates a fresh one.  The hook will then auto-retry
   * the current send once with the cleared session.
   */
  onSessionExpired?: () => void;
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
  send: (content: string, displayContent?: string) => void;
  /** Submit the user response for the current pending card. */
  resumeTurn: (userInput: Record<string, unknown>, actionId?: string, cardId?: string) => void;
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

function hasRenderableFlightPlans(card: CardDescriptor): boolean {
  if (card.card_type !== 'FLIGHT_RESULT') return true;
  const plans = card.body?.plans;
  return Array.isArray(plans) && plans.some((plan) => {
    if (Array.isArray(plan.flights) && plan.flights.length > 0) return true;
    return Boolean(plan.flightNo ?? plan.flight_no ?? plan.flightNumber);
  });
}

function flightResultSignature(card: CardDescriptor): string | null {
  if (card.card_type !== 'FLIGHT_RESULT') return null;
  const plans = card.body?.plans;
  if (!Array.isArray(plans)) return null;
  const flights = plans.flatMap((plan) =>
    Array.isArray(plan.flights)
      ? plan.flights.map((flight) => [flight.flightId, flight.flightNo, flight.price].filter(Boolean).join(':'))
      : [[plan.flightNo, plan.flight_no, plan.flightNumber, plan.price].filter(Boolean).join(':')],
  );
  const signature = flights.filter(Boolean).join('|');
  return signature || null;
}

function messageHasCard(message: ChatMessage, card: CardDescriptor): boolean {
  if ((message.cards ?? []).some((item) => item.card_id === card.card_id)) return true;
  const nextSignature = flightResultSignature(card);
  if (!nextSignature) return false;
  return (message.cards ?? []).some((item) => flightResultSignature(item.card) === nextSignature);
}

function enrichFlightResultCard(
  card: CardDescriptor,
  messages: ChatMessage[],
  flightRoute: { depCity: string; arrCity: string },
): CardDescriptor {
  if (card.card_type !== 'FLIGHT_RESULT') return card;
  const route = flightRoute.depCity || flightRoute.arrCity ? flightRoute : inferRouteFromMessages(messages);
  if (!route.depCity && !route.arrCity) return card;
  const body = card.body ?? {};
  const plans = Array.isArray(body.plans)
    ? body.plans.map((plan) => ({
        ...plan,
        flights: Array.isArray(plan.flights)
          ? plan.flights.map((flight) => ({
              ...flight,
              departure: {
                ...(flight.departure ?? {}),
                city: flight.departure?.city || route.depCity,
              },
              arrival: {
                ...(flight.arrival ?? {}),
                city: flight.arrival?.city || route.arrCity,
              },
            }))
          : plan.flights,
      }))
    : body.plans;
  return {
    ...card,
    body: {
      ...body,
      summary: {
        ...(typeof body.summary === 'object' && body.summary ? body.summary : {}),
        depCity: (typeof body.summary === 'object' && body.summary ? body.summary.depCity : '') || route.depCity,
        arrCity: (typeof body.summary === 'object' && body.summary ? body.summary.arrCity : '') || route.arrCity,
      },
      plans,
    },
  };
}

function inferRouteFromMessages(messages: ChatMessage[]): { depCity: string; arrCity: string } {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const text = collectMessageText(messages[i]);
    const route = inferRouteFromText(text);
    if (route.depCity || route.arrCity) return route;
  }
  return { depCity: '', arrCity: '' };
}

function collectMessageText(message: ChatMessage): string {
  const cardTexts = (message.cards ?? []).flatMap((item) => [
    item.card.title,
    item.card.message,
    typeof item.card.body?.summary === 'string' ? item.card.body.summary : '',
  ]);
  return [message.content, ...cardTexts].filter(Boolean).join('\n');
}

function inferRouteFromText(text: string): { depCity: string; arrCity: string } {
  const patterns = [
    /(?:从)?([\u4e00-\u9fa5]{2,4})\s*[→至-]\s*([\u4e00-\u9fa5]{2,4})(?:的|单程|往返|机票|航班|$)/,
    /(?:从)?([\u4e00-\u9fa5]{2,4})到([\u4e00-\u9fa5]{2,4})(?:的|单程|往返|机票|航班|$)/,
  ];
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match) return { depCity: cleanCity(match[1]), arrCity: cleanCity(match[2]) };
  }
  return { depCity: '', arrCity: '' };
}

function cleanCity(value: string): string {
  return value.replace(/机票|航班|单程|往返|查询|请提供|出发|到达/g, '').trim();
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
  const submittedCardIdsRef = useRef<Set<string>>(new Set());
  const messagesRef = useRef<ChatMessage[]>(EMPTY_MESSAGES);
  const lastFlightRouteRef = useRef<{ depCity: string; arrCity: string }>({ depCity: '', arrCity: '' });
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const heartbeatTargetRef = useRef<string | null>(null);

  const optionsRef = useRef(options);
  useEffect(() => {
    optionsRef.current = options;
  }, [options]);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

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
    submittedCardIdsRef.current.clear();
    lastFlightRouteRef.current = { depCity: '', arrCity: '' };
    setCurrentState(null);
  }, [abort, options.sessionId, options.turnId]);

  const send = useCallback(
    (content: string, displayContent?: string) => {
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
        content: displayContent?.trim() || trimmed,
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
        // 双写: events[] 是新数据源 (按 SSE 顺序), 老字段保留为推导视图.
        events: [],
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
      // 防御: agent_name 只在值是合法非空字符串时才发. 历史上曾因为
      // ``Object.keys(agents)`` 错读成 ``["0"]`` 把 "0" 当 agent name 发出去,
      // 后端 ``KeyError: "Agent '0' not registered"``. 这里再做一道闸门.
      const safeAgentName =
        typeof opts.agentName === 'string' && opts.agentName.trim().length > 0
          ? opts.agentName.trim()
          : undefined;

      chatService
        .sendStream(
          {
            message: trimmed,
            ...(reqSessionId ? { session_id: reqSessionId } : {}),
            ...(safeAgentName ? { agent_name: safeAgentName } : {}),
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
    (userInput: Record<string, unknown>, actionId?: string, cardId?: string) => {
      const pending = pendingRef.current;
      if (!pending) {
        if (status === 'sending' || status === 'streaming' || status === 'resuming') {
          setError('请等待当前回复结束后再提交卡片');
          return;
        }
        const latestCard = latestSubmittableCard(messages, cardId);
        if (!latestCard) {
          setError('当前没有等待中的卡片');
          return;
        }
        if (submittedCardIdsRef.current.has(latestCard.card.card_id)) return;
        submittedCardIdsRef.current.add(latestCard.card.card_id);
        markCardSubmitted(latestCard.messageId, latestCard.card.card_id);
        send(
          formatCardReply(latestCard.card, userInput, actionId),
          formatCardReplyDisplay(latestCard.card.card, userInput),
        );
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
    [messages, send, status, stopHeartbeat],
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
        const at = new Date().toISOString();
        patchAssistant(assistantId, (m) => ({
          ...m,
          content: m.content + chunk,
          status: 'streaming',
          events: appendText(m.events ?? [], chunk, at),
        }));
        return;
      }
      case 'reasoning': {
        const content = event.data.content ?? '';
        if (!content) return;
        const at = new Date().toISOString();
        const item: ReasoningEventView = {
          id: newId('reasoning'),
          content,
          at,
        };
        patchAssistant(assistantId, (m) => ({
          ...m,
          reasoningEvents: [...(m.reasoningEvents ?? []), item],
          events: appendReasoning(m.events ?? [], content, at),
        }));
        return;
      }
      case 'tool_use': {
        const data = event.data;
        const name = (data.name ?? data.tool_name ?? 'unknown') as string;
        const input = (data.input as Record<string, unknown> | undefined) ?? {};
        if (name === 'feihe-travel_queryFlightBasic' || name === 'queryFlightBasic') {
          lastFlightRouteRef.current = {
            depCity: String(input.departureCity ?? input.depCity ?? ''),
            arrCity: String(input.arrivalCity ?? input.arrCity ?? ''),
          };
        }
        const at = new Date().toISOString();
        const item: ToolEventView = {
          id: newId('tool'),
          name,
          phase: 'call',
          input,
          at,
        };
        patchAssistant(assistantId, (m) => ({
          ...m,
          toolEvents: [...(m.toolEvents ?? []), item],
          events: appendToolCall(m.events ?? [], name, input, at),
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
              return {
                ...m,
                toolEvents: events,
                events: updateToolResult(m.events ?? [], toolName, output),
              };
            }
          }
          events.push({
            id: newId('tool'),
            name: toolName,
            phase: 'result',
            output,
            at: new Date().toISOString(),
          });
          return {
            ...m,
            toolEvents: events,
            events: updateToolResult(m.events ?? [], toolName, output),
          };
        });
        return;
      }
      case 'card': {
        const data = event.data;
        const cardView: CardView = {
          card_id: data.card_id,
          card_type: data.card_type,
          card: enrichFlightResultCard(
            { ...data.card, card_type: data.card_type, card_id: data.card_id },
            messagesRef.current,
            lastFlightRouteRef.current,
          ),
          correlation_id: data.correlation_id,
          at: new Date().toISOString(),
        };
        if (!hasRenderableFlightPlans(cardView.card)) return;
        patchAssistant(assistantId, (m) => {
          if (messageHasCard(m, cardView.card)) return m;
          return {
            ...m,
            cards: [...(m.cards ?? []), cardView],
            events: appendCard(m.events ?? [], cardView),
          };
        });
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
          events: appendState(m.events ?? [], stateView.state, stateView.note, stateView.at),
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
          events: suspendCard(m.events ?? [], card.card_id),
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
        // Detect stale session: 后端 in-memory store 丢了 (容器重启/部署),
        // localStorage 还存着旧 session_id. 触发 onSessionExpired 让 ChatPage
        // 清掉, 下次发送会自动建新 session.
        const isSessionExpired =
          code === 'SESSION_ERROR' ||
          (typeof message === 'string' && /session .* not found/i.test(message));
        if (isSessionExpired) {
          optionsRef.current.onSessionExpired?.();
        }
        return;
      }
      case 'done':
        // Final state is set in `handleClose`.
        return;
      // P7: opencode 原生 question 事件 ----
      case 'question_asked': {
        const data = event.data;
        const requestId = String(data.request_id ?? '');
        const questions = Array.isArray(data.questions)
          ? (data.questions as QuestionItem[])
          : [];
        if (!requestId || questions.length === 0) {
          // 防御: 空数据不挂
          return;
        }
        const pending: QuestionView = {
          request_id: requestId,
          session_id: String(data.session_id ?? serverSessionId ?? ''),
          questions,
          received_at: new Date().toISOString(),
        };
        const at = new Date().toISOString();
        patchAssistant(assistantId, (m) => ({
          ...m,
          pendingQuestion: pending,
          events: appendQuestion(
            m.events ?? [],
            { requestId, sessionId: pending.session_id, questions },
            at,
          ),
        }));
        return;
      }
      case 'question_replied': {
        const data = event.data;
        const requestId = String(data.request_id ?? '');
        // Mark the matching pending question as submitted so the UI dims.
        patchAssistant(assistantId, (m) =>
          m.pendingQuestion?.request_id === requestId
            ? {
                ...m,
                pendingQuestion: { ...m.pendingQuestion, submitted: true },
                events: markQuestionSubmitted(m.events ?? [], requestId),
              }
            : { ...m, events: markQuestionSubmitted(m.events ?? [], requestId) },
        );
        return;
      }
      case 'question_rejected': {
        const data = event.data;
        const requestId = String(data.request_id ?? '');
        patchAssistant(assistantId, (m) =>
          m.pendingQuestion?.request_id === requestId
            ? {
                ...m,
                pendingQuestion: { ...m.pendingQuestion, rejected: true },
                events: markQuestionRejected(m.events ?? [], requestId),
              }
            : { ...m, events: markQuestionRejected(m.events ?? [], requestId) },
        );
        return;
      }
      // P7: opencode 原生 todo 事件 ----
      case 'todo_updated': {
        const data = event.data;
        const todos = Array.isArray(data.todos) ? (data.todos as TodoItem[]) : [];
        const view: TodoView = {
          session_id: String(data.session_id ?? serverSessionId ?? ''),
          todos,
          at: new Date().toISOString(),
        };
        patchAssistant(assistantId, (m) => ({ ...m, todoView: view }));
        return;
      }
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

  function markCardSubmitted(messageId: string, cardId: string): void {
    setMessages((prev) =>
      prev.map((m) =>
        m.id === messageId
          ? {
              ...m,
              cards: (m.cards ?? []).map((c) =>
                c.card_id === cardId ? { ...c, submitted: true, suspended: false } : c,
              ),
              events: (m.events ?? []).map((e) =>
                e.type === 'card' && e.card.card_id === cardId
                  ? { ...e, submitted: true, suspended: false }
                  : e,
              ),
            }
          : m,
      ),
    );
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

function latestSubmittableCard(
  messages: ChatMessage[],
  cardId?: string,
): { messageId: string; card: CardView } | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message.role !== 'assistant') continue;
    const cards = message.cards ?? [];
    for (let j = cards.length - 1; j >= 0; j -= 1) {
      const card = cards[j];
      if (cardId && card.card_id !== cardId) continue;
      if (!card.submitted && !card.suspended) {
        return { messageId: message.id, card };
      }
    }
  }
  return null;
}

function formatCardReply(
  card: CardView,
  userInput: Record<string, unknown>,
  actionId?: string,
): string {
  const payload = {
    card_type: card.card_type,
    card_id: card.card_id,
    action_id: actionId ?? 'submit',
    user_input: userInput,
  };
  return `用户已提交 ${card.card_type} 卡片：${JSON.stringify(payload)}`;
}

function formatCardReplyDisplay(
  card: CardDescriptor,
  userInput: Record<string, unknown>,
): string {
  const labels = new Map(
    (card.fields ?? []).map((field) => [field.id ?? field.key ?? field.name ?? field.label, field.label]),
  );
  return Object.entries(userInput)
    .map(([key, value]) => `${labels.get(key) ?? key}：${formatUserInputValue(value)}`)
    .join('，');
}

function formatUserInputValue(value: unknown): string {
  if (Array.isArray(value)) return value.map(formatUserInputValue).join('、');
  if (value && typeof value === 'object') return JSON.stringify(value);
  return String(value ?? '');
}
