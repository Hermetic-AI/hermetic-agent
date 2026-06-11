import { useState } from 'react';
import type {
  ChatMessage as ChatMessageType,
  ToolEventView,
  CardView,
  ScenarioView,
  StateView,
  QuestionView,
  TodoView,
  ChatEvent,
} from '../../types';
import { Button } from '../common';
import { AUIRenderer, QuestionCard, TodoListCard } from '../aui';
import { MarkdownText } from './MarkdownText';
import { groupConsecutiveEvents } from '../../hooks/chatEvents';
import './ChatBubble.css';

interface ChatBubbleProps {
  message: ChatMessageType;
  onQuickReply?: (value: string) => void;
  onAbort?: () => void;
  /** Called when the user submits an AUIP card form. */
  onCardSubmit?: (userInput: Record<string, unknown>, actionId?: string, cardId?: string) => void;
  onQuestionReply?: (requestId: string, answers: string[][], sessionId: string) => void;
  onQuestionReject?: (requestId: string, sessionId: string) => void;
}

export function ChatBubble({
  message,
  onQuickReply,
  onAbort,
  onCardSubmit,
  onQuestionReply,
  onQuestionReject,
}: ChatBubbleProps) {
  const isUser = message.role === 'user';
  const status = message.status ?? 'done';
  const showSpinner = !isUser && (status === 'sending' || status === 'streaming' || status === 'resuming');

  return (
    <div className={`chat-bubble ${isUser ? 'chat-bubble-user' : 'chat-bubble-assistant'}`}>
      {!isUser && (
        <div className="chat-avatar">
          <AIIcon />
        </div>
      )}
      <div className="chat-bubble-content">
        {!isUser && message.scenario && <ScenarioPill scenario={message.scenario} />}
        {!isUser && message.stateEvents && message.stateEvents.length > 0 && (
          <StatePill items={message.stateEvents} current={message.status} />
        )}

        {/* === 主要内容: 按 events[] 时间线顺序渲染 (text → tool → question → card 穿插) === */}
        {isUser ? (
          message.content && (
            <div className="chat-bubble-text">
              <span className="chat-bubble-plain">{message.content}</span>
            </div>
          )
        ) : (
          <EventTimeline
            message={message}
            showSpinner={showSpinner}
            onCardSubmit={onCardSubmit}
            onQuestionReply={onQuestionReply}
            onQuestionReject={onQuestionReject}
          />
        )}

        {message.status === 'error' && message.errorMessage && (
          <div className="chat-bubble-error" role="alert">
            <span className="chat-bubble-error-icon">!</span>
            <span>{message.errorMessage}</span>
          </div>
        )}
        {message.quickReplies && message.quickReplies.length > 0 && (
          <div className="chat-quick-replies">
            {message.quickReplies.map((reply) => (
              <Button
                key={reply.value}
                variant="secondary"
                size="small"
                onClick={() => onQuickReply?.(reply.value)}
              >
                {reply.label}
              </Button>
            ))}
          </div>
        )}
        <div className="chat-bubble-meta">
          <span className="chat-bubble-time">
            {formatTime(message.timestamp)}
            {statusBadge(status)}
            {message.turnId && (
              <span className="chat-bubble-turn" title={`turn: ${message.turnId}`}>
                · turn {message.turnId.slice(0, 6)}
              </span>
            )}
          </span>
          {(status === 'streaming' || status === 'sending' || status === 'resuming') && onAbort && (
            <button
              type="button"
              className="chat-bubble-abort"
              onClick={onAbort}
              aria-label="停止生成"
            >
              停止
            </button>
          )}
        </div>
      </div>
      {isUser && (
        <div className="chat-avatar chat-avatar-user">
          <UserIcon />
        </div>
      )}
    </div>
  );
}

// ===========================================================================
// 事件时间线渲染: 核心是按 SSE 到达顺序迭代 events[], 相邻同类型合并.
// ===========================================================================

interface EventTimelineProps {
  message: ChatMessageType;
  showSpinner: boolean;
  onCardSubmit?: (userInput: Record<string, unknown>, actionId?: string, cardId?: string) => void;
  onQuestionReply?: (requestId: string, answers: string[][], sessionId: string) => void;
  onQuestionReject?: (requestId: string, sessionId: string) => void;
}

function EventTimeline({
  message,
  showSpinner,
  onCardSubmit,
  onQuestionReply,
  onQuestionReject,
}: EventTimelineProps) {
  // 优先用 events[]; 老消息 / 从历史恢复的消息没有 events, 退回按字段渲染.
  const events = message.events;
  if (!events || events.length === 0) {
    return <LegacyBubbleBody message={message} onCardSubmit={onCardSubmit} />;
  }

  const groups = groupConsecutiveEvents(events);
  // 找最后一个 text group, 决定流式光标落在哪.
  const lastTextGroupIdx = (() => {
    for (let i = groups.length - 1; i >= 0; i -= 1) {
      if (groups[i].type === 'text') return i;
    }
    return -1;
  })();

  return (
    <>
      {groups.map((group, idx) => {
        const isLastText = idx === lastTextGroupIdx;
        switch (group.type) {
          case 'text': {
            const merged = group.events
              .map((e) => (e.type === 'text' ? e.content : ''))
              .join('');
            return (
              <div className="chat-bubble-text" key={`text-${idx}`}>
                <MarkdownText source={merged} showCursor={showSpinner && isLastText} />
              </div>
            );
          }
          case 'reasoning':
            return (
              <ReasoningGroupBlock
                key={`rsn-${idx}`}
                events={group.events.filter((e): e is Extract<ChatEvent, { type: 'reasoning' }> => e.type === 'reasoning')}
              />
            );
          case 'tool':
            return (
              <ToolGroupBlock
                key={`tool-${idx}`}
                events={group.events.filter((e): e is Extract<ChatEvent, { type: 'tool' }> => e.type === 'tool')}
              />
            );
          case 'card':
            return (
              <CardGroupBlock
                key={`card-${idx}`}
                events={group.events.filter((e): e is Extract<ChatEvent, { type: 'card' }> => e.type === 'card')}
                onSubmit={onCardSubmit}
                disabled={message.status === 'aborted' || message.status === 'error'}
              />
            );
          case 'state':
            // 状态单独成一行太碎, 跟 ScenarioPill/StatePill 走即可. 这里跳过.
            return null;
          case 'question':
            return (
              <QuestionGroupBlock
                key={`q-${idx}`}
                events={group.events.filter((e): e is Extract<ChatEvent, { type: 'question' }> => e.type === 'question')}
                onReply={onQuestionReply}
                onReject={onQuestionReject}
              />
            );
        }
      })}
      {/* todo 走独立字段, 单次快照, 不放进时间线. */}
      {message.todoView && <TodoBlock view={message.todoView} />}
    </>
  );
}

function LegacyBubbleBody({
  message,
  onCardSubmit,
}: {
  message: ChatMessageType;
  onCardSubmit?: (userInput: Record<string, unknown>, actionId?: string) => void;
}) {
  // 兜底: 老消息 / 历史回放, 走老字段. 顺序是历史最优近似, 不完美但能渲染.
  return (
    <>
      {message.content && (
        <div className="chat-bubble-text">
          <MarkdownText source={message.content} />
        </div>
      )}
      {message.toolEvents && message.toolEvents.length > 0 && (
        <ToolBlock items={message.toolEvents} />
      )}
      {message.cards && message.cards.length > 0 && onCardSubmit && (
        <CardsBlock items={message.cards} onSubmit={onCardSubmit} disabled={false} />
      )}
      {message.pendingQuestion && <QuestionBlockView question={message.pendingQuestion} />}
      {message.todoView && <TodoBlock view={message.todoView} />}
    </>
  );
}

// --- 分组渲染 ---

function ReasoningGroupBlock({
  events,
}: {
  events: Extract<ChatEvent, { type: 'reasoning' }>[];
}) {
  const [open, setOpen] = useState(false);
  const merged = events.map((e) => e.content).join('');
  if (!merged) return null;
  return (
    <div className="chat-reasoning">
      <button
        type="button"
        className="chat-reasoning-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="chat-reasoning-icon">💭</span>
        <span>{open ? '隐藏思考过程' : `已思考 ${events.length} 步`}</span>
      </button>
      {open && (
        <ul className="chat-reasoning-list">
          {events.map((e) => (
            <li key={e.id}>{e.content}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ToolGroupBlock({
  events,
}: {
  events: Extract<ChatEvent, { type: 'tool' }>[];
}) {
  const [open, setOpen] = useState(false);
  const callCount = events.filter((e) => e.phase === 'call').length;
  return (
    <div className="chat-tools">
      <button
        type="button"
        className="chat-tools-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="chat-tools-icon">🔧</span>
        <span>
          工具调用 ({callCount}) · {open ? '收起' : '展开'}
        </span>
      </button>
      {open && (
        <ol className="chat-tools-list">
          {events.map((tool) => (
            <li key={tool.id} className={`chat-tool-item chat-tool-${tool.phase}`}>
              <div className="chat-tool-header">
                <span className="chat-tool-name">{tool.name}</span>
                <span className={`chat-tool-phase chat-tool-phase-${tool.phase}`}>
                  {tool.phase === 'call' ? '调用' : '结果'}
                </span>
              </div>
              {tool.phase === 'call' && tool.input !== undefined && (
                <pre className="chat-tool-pre">
                  {JSON.stringify(tool.input, null, 2)}
                </pre>
              )}
              {tool.phase === 'result' && (
                <pre className="chat-tool-pre">{stringifySafe(tool.output)}</pre>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function CardGroupBlock({
  events,
  onSubmit,
  disabled,
}: {
  events: Extract<ChatEvent, { type: 'card' }>[];
  onSubmit?: (userInput: Record<string, unknown>, actionId?: string, cardId?: string) => void;
  disabled: boolean;
}) {
  if (!onSubmit) return null;
  return (
    <div className="chat-cards">
      {events.map((e) => (
        <AUIRenderer
          key={e.id}
          card={e.card}
          suspended={Boolean(e.suspended) || disabled}
          submitted={Boolean(e.submitted)}
          onSubmit={(userInput, actionId) => onSubmit(userInput, actionId, e.card.card_id)}
        />
      ))}
    </div>
  );
}

function QuestionGroupBlock({
  events,
  onReply,
  onReject,
}: {
  events: Extract<ChatEvent, { type: 'question' }>[];
  onReply?: (requestId: string, answers: string[][], sessionId: string) => void;
  onReject?: (requestId: string, sessionId: string) => void;
}) {
  return (
    <>
      {events.map((q) => {
        const isDone = Boolean(q.submitted) || Boolean(q.rejected);
        return (
          <div className="chat-question" key={q.id}>
            <QuestionCard
              card={{
                card_id: `q-${q.requestId}`,
                card_type: 'QUESTION',
                schema_version: '1.0',
                title: '需要您确认',
                body: { questions: q.questions },
              }}
              suspended={isDone}
              submitted={q.submitted ?? false}
              questions={q.questions}
              requestId={q.requestId}
              sessionId={q.sessionId}
              onSubmit={
                onReply
                  ? (answers) => onReply(q.requestId, answers, q.sessionId)
                  : undefined
              }
              onReject={onReject ? () => onReject(q.requestId, q.sessionId) : undefined}
            />
          </div>
        );
      })}
    </>
  );
}

// --- 老字段渲染 (兜底) ---

function ToolBlock({ items }: { items: ToolEventView[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="chat-tools">
      <button
        type="button"
        className="chat-tools-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="chat-tools-icon">🔧</span>
        <span>
          工具调用 ({items.filter((i) => i.phase === 'call').length}) ·{' '}
          {open ? '收起' : '展开'}
        </span>
      </button>
      {open && (
        <ol className="chat-tools-list">
          {items.map((tool) => (
            <li key={tool.id} className={`chat-tool-item chat-tool-${tool.phase}`}>
              <div className="chat-tool-header">
                <span className="chat-tool-name">{tool.name}</span>
                <span className={`chat-tool-phase chat-tool-phase-${tool.phase}`}>
                  {tool.phase === 'call' ? '调用' : '结果'}
                </span>
              </div>
              {tool.phase === 'call' && tool.input !== undefined && (
                <pre className="chat-tool-pre">
                  {JSON.stringify(tool.input, null, 2)}
                </pre>
              )}
              {tool.phase === 'result' && (
                <pre className="chat-tool-pre">{stringifySafe(tool.output)}</pre>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function CardsBlock({
  items,
  onSubmit,
  disabled,
}: {
  items: CardView[];
  onSubmit: (userInput: Record<string, unknown>, actionId?: string, cardId?: string) => void;
  disabled: boolean;
}) {
  if (items.length === 0) return null;
  return (
    <div className="chat-cards">
      {items.map((c) => (
        <AUIRenderer
          key={c.card_id}
          card={c.card}
          suspended={Boolean(c.suspended) || disabled}
          submitted={Boolean(c.submitted)}
          onSubmit={(userInput, actionId) => onSubmit(userInput, actionId, c.card_id)}
        />
      ))}
    </div>
  );
}

function QuestionBlockView({ question }: { question: QuestionView }) {
  const isDone = Boolean(question.submitted) || Boolean(question.rejected);
  return (
    <div className="chat-question">
      <QuestionCard
        card={{
          card_id: `q-${question.request_id}`,
          card_type: 'QUESTION',
          schema_version: '1.0',
          title: '需要您确认',
          body: { questions: question.questions },
        }}
        suspended={isDone}
        submitted={question.submitted ?? false}
        questions={question.questions}
        requestId={question.request_id}
        sessionId={question.session_id}
      />
    </div>
  );
}

function TodoBlock({ view }: { view: TodoView }) {
  if (view.todos.length === 0) return null;
  return (
    <div className="chat-todo">
      <TodoListCard
        card={{
          card_id: `todo-${view.at}`,
          card_type: 'TODO_LIST',
          schema_version: '1.0',
          title: '任务清单',
          body: { todos: view.todos },
        }}
        todos={view.todos}
      />
    </div>
  );
}

// --- 顶部 pill (Scenario/State) ---

function statusBadge(status: NonNullable<ChatMessageType['status']>): string | null {
  switch (status) {
    case 'sending':
      return ' · 发送中';
    case 'streaming':
      return ' · 生成中';
    case 'thinking':
      return ' · 思考中';
    case 'aborted':
      return ' · 已停止';
    case 'error':
      return ' · 失败';
    case 'suspended':
      return ' · 等待您输入';
    case 'resuming':
      return ' · 正在恢复';
    case 'done':
    default:
      return null;
  }
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  } catch {
    return iso;
  }
}

function ScenarioPill({ scenario }: { scenario: ScenarioView }) {
  return (
    <div className="chat-scenario-pill" title={`Scenario: ${scenario.name} v${scenario.version ?? '?'} via ${scenario.matched_by ?? '?'}`}>
      <span className="chat-scenario-icon">⚙</span>
      <span className="chat-scenario-name">{scenario.name}</span>
      {scenario.orchestration && (
        <span className="chat-scenario-orch">{scenario.orchestration}</span>
      )}
    </div>
  );
}

function StatePill({ items }: { items: StateView[]; current?: string }) {
  const last = items[items.length - 1];
  if (!last) return null;
  return (
    <div className="chat-state-pill" title={`State: ${items.map((s) => s.state).join(' → ')}`}>
      <span className="chat-state-dot" />
      <span className="chat-state-label">业务状态</span>
      <code className="chat-state-code">{last.state}</code>
    </div>
  );
}

function stringifySafe(v: unknown): string {
  if (typeof v === 'string') return v;
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
}

function AIIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#0051A1" strokeWidth="2">
      <circle cx="12" cy="12" r="10" />
      <path d="M12 6v6l4 2" />
    </svg>
  );
}

function UserIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
      <circle cx="12" cy="8" r="4" />
      <path d="M12 14c-4 0-8 2-8 4v2h16v-2c0-2-4-4-8-4z" />
    </svg>
  );
}
