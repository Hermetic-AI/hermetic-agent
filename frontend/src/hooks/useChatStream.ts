// useChatStream — drives a single chat turn against the streaming endpoint.
//
// State machine:
//   idle       ──send()──▶ sending
//   sending    ──event:session──▶ streaming
//   streaming  ──event:text/reasoning/tool_use/tool_result──▶ streaming
//              ──event:done / abort / network close──▶ idle
//              ──event:error──▶ error
//
// The hook owns its own AbortController.  Unrecognised SSE event types
// (e.g. card / question / todo emitted by domain-specific scenarios) are
// silently ignored — the generic UI does not need them.

import { useCallback, useEffect, useRef, useState } from 'react';
import { chatService, ApiError, type SendStreamOptions } from '../services';
import type {
  ChatMessage,
  StreamEvent,
  ToolEventView,
  ReasoningEventView,
} from '../types';
import {
  appendReasoning,
  appendText,
  appendToolCall,
  updateToolResult,
} from './chatEvents';

export type ChatStatus =
  | 'idle'
  | 'sending'
  | 'streaming'
  | 'error';

export interface UseChatStreamOptions {
  sessionId?: string;
  /** Called with the backend-issued session id once known. */
  onSessionChange?: (id: string) => void;
  /**
   * Called when the backend reports the current session is gone (typically
   * because the server was restarted and lost its in-memory store, but the
   * localStorage entry is still around).  Should clear the local session id
   * so the next send creates a fresh one.
   */
  onSessionExpired?: () => void;
  /** Optional prompt prefix / system context appended to every user message. */
  systemPrompt?: string;
  /** Model hint forwarded to the backend. */
  model?: string;
  /** Agent instance (opencode sandbox) to target. */
  agentName?: string;
  /**
   * Agent asset code (from `/agent/agents/`) to inject.  When set, the
   * server resolves the agent and prepends its system_prompt / prompts /
   * commands / MCP block to the LLM call.  Sent both as `agent_code` in
   * the body and as `X-Agent-Code` header.
   */
  agentCode?: string;
  /**
   * Extra MCP servers to inject into this turn's opencode mcpServers block.
   * Sent as `extra_opencode_mcp` (snake_case) in the JSON body — the
   * backend `ChatRequest` schema already accepts this field.
   */
  extraMcpServers?: Record<string, Record<string, unknown>>;
  /**
   * Extra system messages prepended to this turn only.  Sent as
   * `extra_system_messages` (snake_case) in the JSON body.  Backend
   * ignores unknown fields today (Pydantic `extra='ignore'` default),
   * so this is a forward-compatible payload.
   */
  extraSystemMessages?: string[];
}

export interface UseChatStreamResult {
  messages: ChatMessage[];
  status: ChatStatus;
  error: string | null;
  serverSessionId: string | null;
  send: (content: string, displayContent?: string) => void;
  /** Stop the SSE stream locally. */
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

  const abortRef = useRef<AbortController | null>(null);
  const activeMsgIdRef = useRef<string | null>(null);
  const messagesRef = useRef<ChatMessage[]>(EMPTY_MESSAGES);

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

  // --- Public controls ----------------------------------------------------

  const abort = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const reset = useCallback(() => {
    abort();
    setMessages(EMPTY_MESSAGES);
    setStatus('idle');
    setError(null);
    setServerSessionId(options.sessionId ?? null);
  }, [abort, options.sessionId]);

  const send = useCallback(
    (content: string, displayContent?: string) => {
      const trimmed = content.trim();
      if (!trimmed) return;
      if (status === 'sending' || status === 'streaming') return;

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
        events: [],
        toolEvents: [],
        reasoningEvents: [],
      };
      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setStatus('sending');

      const opts = optionsRef.current;
      const reqSessionId = serverSessionId ?? opts.sessionId;
      const safeAgentName =
        typeof opts.agentName === 'string' && opts.agentName.trim().length > 0
          ? opts.agentName.trim()
          : undefined;
      const safeAgentCode =
        typeof opts.agentCode === 'string' && opts.agentCode.trim().length > 0
          ? opts.agentCode.trim()
          : undefined;

      chatService
        .sendStream(
          {
            message: trimmed,
            ...(reqSessionId ? { session_id: reqSessionId } : {}),
            ...(safeAgentName ? { agent_name: safeAgentName } : {}),
            ...(safeAgentCode ? { agent_code: safeAgentCode } : {}),
            ...(opts.model ? { model: opts.model } : {}),
            ...(opts.systemPrompt ? { system_prompt: opts.systemPrompt } : {}),
            ...(opts.extraMcpServers && Object.keys(opts.extraMcpServers).length > 0
              ? { extra_opencode_mcp: opts.extraMcpServers }
              : {}),
            ...(opts.extraSystemMessages && opts.extraSystemMessages.length > 0
              ? { extra_system_messages: opts.extraSystemMessages }
              : {}),
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
    [serverSessionId, status],
  );

  // --- Event handling -----------------------------------------------------

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
      default:
        // Unknown event type — ignore for the generic UI.
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
    if (reason === 'done') {
      patchAssistant(assistantId, (m) => ({ ...m, status: 'done', streaming: false }));
      setStatus('idle');
      return;
    }
    if (reason === 'aborted') {
      patchAssistant(assistantId, (m) => ({ ...m, status: 'aborted', streaming: false }));
      setStatus('idle');
      return;
    }
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
    };
  }, []);

  return {
    messages,
    status,
    error,
    serverSessionId,
    send,
    abort,
    reset,
  };
}