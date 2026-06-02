// Domain types matching the backend Pydantic schemas
// (see openagent/api/routes.py and openagent/streaming.py).
//
// Keep these in sync with the backend; if the backend response shape
// changes, update here first and let the rest of the frontend follow.

import type { ReactNode } from 'react';

// --- Session ---

export interface SessionInfo {
  session_id: string;
  agent_name: string;
  agent_base_url: string;
  model?: string | null;
}

// --- Chat ---

export type ChatRole = 'user' | 'assistant' | 'system' | 'tool';

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  /** ISO timestamp. */
  timestamp: string;
  /** Local-only fields below are populated by the UI. */
  attachments?: ChatAttachment[];
  quickReplies?: QuickReply[];
  /** True while the assistant message is still receiving text chunks. */
  streaming?: boolean;
  /** Optional UI badge shown next to the bubble. */
  status?: 'sending' | 'streaming' | 'thinking' | 'aborted' | 'error' | 'done';
  /** Tool calls / reasoning captured during the run. */
  toolEvents?: ToolEventView[];
  reasoningEvents?: ReasoningEventView[];
  /** Optional structured error to display. */
  errorMessage?: string;
}

export interface ChatAttachment {
  type: 'image' | 'file' | 'card';
  name: string;
  url?: string;
  data?: unknown;
}

export interface QuickReply {
  label: string;
  value: string;
}

// --- SSE event surface (from openagent/streaming.py) ---

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
  tool_use: { tool_name: string; input: Record<string, unknown>; [k: string]: unknown };
  tool_result: { tool_name: string; output: unknown; [k: string]: unknown };
  done: { [k: string]: unknown };
  error: { message: string; [k: string]: unknown };
}

export interface StreamEvent<T extends StreamEventType = StreamEventType> {
  type: T;
  data: StreamEventPayloadMap[T];
}

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

// --- Skills ---

export interface Skill {
  name: string;
  description: string;
  version: string;
  triggers: string[];
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  mcp_tools: string[];
  source: string;
}

export interface SkillsResponse {
  success: true;
  skills: Skill[];
}

// --- Tools (MCP) ---

export interface Tool {
  name: string;
  description?: string;
  input_schema?: Record<string, unknown>;
  enabled: boolean;
  source?: 'local' | 'remote' | string;
  remote_url?: string;
  remote_tool_name?: string;
}

export interface ToolsResponse {
  success: true;
  tools: Tool[];
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
  agents?: Record<string, AgentConfigView>;
  skills_count?: number;
  tools_count?: number;
}

// --- UI-only types ---

export interface NavItemView {
  id: string;
  label: string;
  icon: ReactNode;
}
