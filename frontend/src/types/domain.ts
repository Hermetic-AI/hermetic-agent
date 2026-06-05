// Domain types matching the backend Pydantic schemas
// (see openagent/api/routes.py, openagent/api/controllers/chat_controller.py,
// and openagent/streaming.py).
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
  status?:
    | 'sending'
    | 'streaming'
    | 'thinking'
    | 'aborted'
    | 'error'
    | 'done'
    | 'suspended'
    | 'resuming';
  /** Tool calls / reasoning captured during the run. */
  toolEvents?: ToolEventView[];
  reasoningEvents?: ReasoningEventView[];
  /** AUIP cards emitted by the agent (HITL flow). */
  cards?: CardView[];
  /** Scenario routing info, attached to the first message of a turn. */
  scenario?: ScenarioView | null;
  /** State transitions emitted by the agent (HITL state machine). */
  stateEvents?: StateView[];
  /** Optional structured error to display. */
  errorMessage?: string;
  /** Turn id, when this message is part of a suspended / resumable turn. */
  turnId?: string;
  /** Correlation id of the most recent pending ask_user card. */
  pendingCorrelationId?: string;
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
//
// 12 event types, see docs/api/scenarios.md §2.3.

export type StreamEventType =
  | 'scenario'
  | 'session'
  | 'text'
  | 'reasoning'
  | 'tool_use'
  | 'tool_result'
  | 'card'
  | 'state'
  | 'suspend'
  | 'resume'
  | 'done'
  | 'error';

export interface ScenarioView {
  name: string;
  version?: string;
  matched_by?: string;
  orchestration?: string;
}

export interface StateView {
  state: string;
  note?: string;
  at: string;
}

export interface StreamEventPayloadMap {
  scenario: ScenarioView & Record<string, unknown>;
  session: { session_id: string; [k: string]: unknown };
  text: { content: string; [k: string]: unknown };
  reasoning: { content: string; [k: string]: unknown };
  tool_use: {
    id?: string;
    tool_name?: string;
    name?: string;
    input?: Record<string, unknown>;
    [k: string]: unknown;
  };
  tool_result: {
    id?: string;
    tool_name?: string;
    name?: string;
    output?: unknown;
    is_error?: boolean;
    [k: string]: unknown;
  };
  card: {
    card_id: string;
    card_type: string;
    card: CardDescriptor;
    correlation_id?: string;
    [k: string]: unknown;
  };
  state: { state: string; note?: string; [k: string]: unknown };
  suspend: {
    checkpoint_id: string;
    card: CardDescriptor;
    correlation_id: string;
    input_schema?: Record<string, unknown>;
    timeout_at?: number;
    [k: string]: unknown;
  };
  resume: { checkpoint_id: string; [k: string]: unknown };
  done: { stop_reason?: string; [k: string]: unknown };
  error: { message: string; code?: string; [k: string]: unknown };
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

// --- AUIP cards (see docs/design/book-flight-hitl-design.md §4.4) ---

export type CardType =
  | 'CHAT_FALLBACK'
  | 'OD_INPUT'
  | 'FLIGHT_RESULT'
  | 'FLIGHT_LIST'
  | 'CABIN_LIST'
  | 'PASSENGER_FORM'
  | 'OAT_BINDING'
  | 'PRICE_VERIFY'
  | 'POLICY_DECISION'
  | 'ORDER_CONFIRM'
  | 'ORDER_SUCCESS'
  | 'CANNOT_ORDER'
  | string;

export interface CardAction {
  id: string;
  label: string;
  style?: 'primary' | 'secondary' | 'danger' | 'ghost' | string;
  confirm?: boolean;
}

export interface CardField {
  id: string;
  label: string;
  type: string;
  required?: boolean;
  placeholder?: string;
  options?: Array<{ value: string; label: string }>;
  default?: unknown;
}

export interface FlightEndpoint {
  city: string;
  airport: string;
  airportCode: string;
  terminal?: string;
  time: string;
}

export interface FlightSegment {
  flightId: string;
  flightNo: string;
  shareFlight?: boolean;
  shareInfo?: string;
  airline: { code: string; name: string };
  aircraft?: string;
  date: string;
  departure: FlightEndpoint;
  arrival: FlightEndpoint;
  duration: string;
  stops: number;
  cabin: string;
  cabinClass?: 'ECONOMY' | 'PREMIUM_ECONOMY' | 'BUSINESS' | 'FIRST' | string;
  meal?: string;
  price: number;
  fullPrice?: number;
  tags?: string[];
  [k: string]: unknown;
}

export interface FlightPlan {
  id: string;
  title: string;
  subtitle?: string;
  criteria?: string;
  flights: FlightSegment[];
  [k: string]: unknown;
}

export interface FlightResultSummary {
  totalCount: number;
  filteredCount: number;
  searchType: string;
  depCity: string;
  arrCity: string;
  depDate: string;
  weather?: string;
  [k: string]: unknown;
}

export interface CardDescriptor {
  card_id: string;
  card_type: CardType;
  schema_version?: string;
  title?: string;
  body?: Record<string, unknown> & {
    summary?: FlightResultSummary;
    plans?: FlightPlan[];
  };
  message?: string;
  fields?: CardField[];
  options?: Array<{ value: string; label: string }>;
  actions?: CardAction[];
  decision_buttons?: CardAction[];
  flights?: Array<Record<string, unknown>>;
  cabins?: Array<Record<string, unknown>>;
  passengers?: Array<Record<string, unknown>>;
  order_summary?: Record<string, unknown>;
  order_no?: string;
  pay_url?: string;
  total_price?: number;
  current_price?: number;
  original_price?: number;
  price_diff?: number;
  policy_overrun?: boolean;
  reason?: string;
  fallback?: string;
  metadata?: Record<string, unknown>;
  dismissible?: boolean;
  [k: string]: unknown;
}

export interface CardView {
  card_id: string;
  card_type: CardType;
  card: CardDescriptor;
  correlation_id?: string;
  at: string;
  /** When true, the turn is suspended waiting for a user submission. */
  suspended?: boolean;
  /** True after the user submitted an answer for this card. */
  submitted?: boolean;
}

// --- Turn lifecycle (F3) ---

export type TurnStatus = 'running' | 'suspended' | 'done' | 'error' | 'cancelled';

export interface TurnInfo {
  turn_id: string;
  session_id: string;
  skill_name?: string;
  skill_version?: string;
  state?: string;
  status: TurnStatus;
  created_at?: string;
}

export interface ResumeRequest {
  correlation_id: string;
  user_input: Record<string, unknown>;
  action_id?: string;
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

// --- Scenarios (P6) ---

export interface ScenarioSummary {
  name: string;
  version?: string;
  description?: string;
  enabled?: boolean;
  tags?: string[];
  owner?: string;
  tier?: string;
  source?: string;
}

export interface ScenariosListResponse {
  success: true;
  total?: number;
  scenarios: ScenarioSummary[];
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
