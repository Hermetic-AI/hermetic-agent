import { useState } from 'react';
import type {
  ChatMessage as ChatMessageType,
  ToolEventView,
  ReasoningEventView,
  CardView,
  ScenarioView,
  StateView,
} from '../../types';
import { Button } from '../common';
import { AUIRenderer } from '../aui';
import './ChatBubble.css';

interface ChatBubbleProps {
  message: ChatMessageType;
  onQuickReply?: (value: string) => void;
  onAbort?: () => void;
  /** Called when the user submits an AUIP card form. */
  onCardSubmit?: (userInput: Record<string, unknown>, actionId?: string) => void;
}

export function ChatBubble({ message, onQuickReply, onAbort, onCardSubmit }: ChatBubbleProps) {
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
        {message.role !== 'user' && (message.reasoningEvents?.length ?? 0) > 0 && (
          <ReasoningBlock items={message.reasoningEvents!} />
        )}
        {message.content && (
          <div className="chat-bubble-text">
            {message.content}
            {showSpinner && <span className="chat-bubble-cursor">▍</span>}
          </div>
        )}
        {message.role !== 'user' && (message.toolEvents?.length ?? 0) > 0 && (
          <ToolBlock items={message.toolEvents!} />
        )}
        {message.role !== 'user' && (message.cards?.length ?? 0) > 0 && onCardSubmit && (
          <CardsBlock
            items={message.cards!}
            onSubmit={onCardSubmit}
            disabled={status === 'suspended' || status === 'aborted' || status === 'error'}
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

function ReasoningBlock({ items }: { items: ReasoningEventView[] }) {
  const [open, setOpen] = useState(false);
  const last = items[items.length - 1];
  if (!last) return null;
  return (
    <div className="chat-reasoning">
      <button
        type="button"
        className="chat-reasoning-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="chat-reasoning-icon">💭</span>
        <span>{open ? '隐藏思考过程' : `已思考 ${items.length} 步`}</span>
      </button>
      {open && (
        <ul className="chat-reasoning-list">
          {items.map((r) => (
            <li key={r.id}>{r.content}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

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
                <pre className="chat-tool-pre">
                  {stringifySafe(tool.output)}
                </pre>
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
  onSubmit: (userInput: Record<string, unknown>, actionId?: string) => void;
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
          onSubmit={onSubmit}
        />
      ))}
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
