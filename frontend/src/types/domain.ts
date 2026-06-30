// Minimal generic chat types — frontend no longer carries domain knowledge.
//
// The backend may still emit card / question / todo / scenario / state
// events for richer integrations, but the generic UI ignores them.  Add
// new event types here ONLY when the frontend needs to render them.

import type { ReactNode } from 'react';

// --- Session ---

export interface SessionInfo {
  session_id: string;
  agent_name: string;
  agent_base_url: string;
  model?: string | null;
}

// --- Chat messages ---

export type ChatRole = 'user' | 'assistant' | 'system' | 'tool';

/**
 * An ordered timeline of streaming events.  Assistant messages walk this
 * list in order so text / tool calls interleave exactly as the SSE stream
 * delivered them.  Adjacent events of the same type are merged by the
 * renderer into a single visual block.
 */
export type ChatEvent =
  | { type: 'reasoning'; id: string; content: string; at: string }
  | { type: 'text'; id: string; content: string; at: string }
  | {
      type: 'tool';
      id: string;
      name: string;
      phase: 'call' | 'result';
      input?: unknown;
      output?: unknown;
      at: string;
    };

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  /** ISO timestamp. */
  timestamp: string;
  /** Local-only fields populated by the UI. */
  quickReplies?: QuickReply[];
  /** True while the assistant message is still receiving chunks. */
  streaming?: boolean;
  status?: 'sending' | 'streaming' | 'aborted' | 'error' | 'done';
  /** Tool calls captured during the run. */
  toolEvents?: ToolEventView[];
  reasoningEvents?: ReasoningEventView[];
  /** Ordered streaming timeline. */
  events?: ChatEvent[];
  errorMessage?: string;
}

export interface QuickReply {
  label: string;
  value: string;
}

// --- SSE event surface (from hermetic_agent/streaming.py) ---
//
// Generic events the UI understands.  Unrecognised types are ignored
// at runtime — see useChatStream.handleEvent.

export type StreamEventType =
  | 'session'
  | 'text'
  | 'reasoning'
  | 'tool_use'
  | 'tool_result'
  | 'done'
  | 'error';

export interface StreamEventPayloadMap {
  session: { session_id: string; [k: string]: unknown };
  text: { content: string; [k: string]: unknown };
  reasoning: { content: string; [k: string]: unknown };
  tool_use: {
    id?: string;
    name?: string;
    tool_name?: string;
    input?: Record<string, unknown>;
    [k: string]: unknown;
  };
  tool_result: {
    id?: string;
    name?: string;
    tool_name?: string;
    output?: unknown;
    is_error?: boolean;
    [k: string]: unknown;
  };
  done: { stop_reason?: string; [k: string]: unknown };
  error: { message: string; code?: string; [k: string]: unknown };
}

export type StreamEvent<T extends StreamEventType = StreamEventType> = T extends StreamEventType
  ? { type: T; data: StreamEventPayloadMap[T] }
  : never;

export interface ToolEventView {
  id: string;
  name: string;
  phase: 'call' | 'result';
  input?: Record<string, unknown>;
  output?: unknown;
  /** ISO timestamp; missing on the call side is fine. */
  at: string;
}

export interface ReasoningEventView {
  id: string;
  content: string;
  at: string;
}

// --- Pool / Agents ---

export interface AgentConfigView {
  name: string;
  base_url: string;
  sdk_type: 'opencode' | 'claude_code' | string;
  default_model?: string | null;
}

export interface PoolStatsResponse {
  total_agents: number;
  agents: Record<string, AgentConfigView>;
}

// --- Health / Ready ---

export interface HealthResponse {
  status: 'ok';
}

export interface ReadyResponse {
  status: 'ready' | 'not_ready';
  storage: boolean;
  bridge: boolean;
  skill_registry: boolean;
  mcp_registry: boolean;
  reason?: string;
  agents?: string[];
  skills_count?: number;
  tools_count?: number;
}

// --- UI-only types ---

export interface NavItemView {
  id: string;
  label: string;
  icon: ReactNode;
}