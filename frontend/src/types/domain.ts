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

/**
 * 单条消息内嵌的有序事件时间线.
 *
 * 旧设计把同类事件聚到一个字段 (toolEvents[] / cards[] / stateEvents[] / pendingQuestion),
 * 渲染时按"字段类型"固定顺序 (reasoning → text → tool → card), 完全丢失了 SSE
 * 真正的到达顺序.  比如 AI 说 "查一下" → 调 tool → 说 "查到了" → 弹问题,
 * 旧渲染会变成 ["查一下查到了" 拼成一段] [tool] [问题], 文本/工具/问题的穿插
 * 关系全错.
 *
 * 新设计: events[] 按 SSE 到达顺序追加, ChatBubble 按 events[] 顺序渲染,
 * 相邻同类型事件自动合并成一段 (避免 100 个 text chunk 变 100 行).
 * 老字段 (toolEvents/cards/...) 保留, 但由 events[] 推导出来, 单一数据源.
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
    }
  | {
      type: 'card';
      id: string;
      card: CardDescriptor;
      correlationId?: string;
      suspended?: boolean;
      submitted?: boolean;
      at: string;
    }
  | { type: 'state'; id: string; state: string; note?: string; at: string }
  | {
      type: 'question';
      id: string;
      requestId: string;
      sessionId: string;
      questions: QuestionItem[];
      submitted?: boolean;
      rejected?: boolean;
      at: string;
    };

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
  /** P7: opencode 原生 question request (来自 ``question_asked`` 事件) */
  pendingQuestion?: QuestionView;
  /** P7: opencode 原生 todo 列表 (来自 ``todo_updated`` 事件) */
  todoView?: TodoView;
  /**
   * Ordered timeline of streaming events (assistant only).  The renderer
   * walks this list in order so text / tool / question / card interleave
   * exactly as the SSE stream delivered them.  See {@link ChatEvent}.
   */
  events?: ChatEvent[];
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
  | 'error'
  // P7: opencode 原生 question / todo 事件透传
  | 'question_asked'
  | 'question_replied'
  | 'question_rejected'
  | 'todo_updated';

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
  // P7: opencode 原生 question / todo
  question_asked: {
    request_id: string;
    session_id: string;
    questions: QuestionItem[];
    [k: string]: unknown;
  };
  question_replied: {
    session_id: string;
    request_id: string;
    answers: string[][];
    [k: string]: unknown;
  };
  question_rejected: {
    session_id: string;
    request_id: string;
    [k: string]: unknown;
  };
  todo_updated: {
    session_id: string;
    todos: TodoItem[];
    [k: string]: unknown;
  };
}

// --- Question (opencode 原生) ---------------------------------------------

export interface QuestionOption {
  label: string;
  description?: string;
}

export interface QuestionItem {
  question: string;
  header: string;
  options: QuestionOption[];
  multiple?: boolean;
  custom?: boolean;
}

export interface QuestionView {
  request_id: string;
  session_id: string;
  questions: QuestionItem[];
  received_at: string;
  /** True after the user submits or rejects this question request. */
  submitted?: boolean;
  rejected?: boolean;
}

// --- Todo (opencode 原生) --------------------------------------------------

export type TodoStatus = 'pending' | 'in_progress' | 'completed' | 'cancelled' | string;
export type TodoPriority = 'high' | 'medium' | 'low' | string;

export interface TodoItem {
  content: string;
  status: TodoStatus;
  priority: TodoPriority;
}

export interface TodoView {
  session_id: string;
  todos: TodoItem[];
  at: string;
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
  // P7: opencode 原生透传 (一般不通过 AUIP 走, 走 ChatMessage.pendingQuestion/todoView)
  | 'QUESTION'
  | 'TODO_LIST'
  | string;

export interface CardAction {
  id: string;
  label: string;
  style?: 'primary' | 'secondary' | 'danger' | 'ghost' | string;
  confirm?: boolean;
  /** Optional opencode-style decision code (e.g. POLICY_DECISION buttons). */
  code?: string;
  /** Optional surcharge amount (POLICY_DECISION). */
  surcharge?: number;
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
  // 后端 readiness.collect_readiness() 返回 ``list(bridge.list_agents().keys())``,
  // 元素是已注册 Agent 的 name 字符串. 用 ``Record<string, AgentConfigView>`` 在
  // 前端跑会触发 ``Object.keys(["opencode-core"])`` 返 ``["0"]``, 把 "0" 当 agent
  // name 发出去; 必须按数组读.
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
