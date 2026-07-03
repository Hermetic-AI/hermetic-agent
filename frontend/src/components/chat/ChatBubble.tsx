import { useState } from 'react';
import type {
  ChatMessage as ChatMessageType,
  ToolEventView,
  ChatEvent,
} from '../../types';
import { Button } from '../common';
import { MarkdownText } from './MarkdownText';
import { groupConsecutiveEvents } from '../../hooks/chatEvents';
import './ChatBubble.css';

interface ChatBubbleProps {
  message: ChatMessageType;
  onQuickReply?: (value: string) => void;
  onAbort?: () => void;
}

export function ChatBubble({
  message,
  onQuickReply,
  onAbort,
}: ChatBubbleProps) {
  const isUser = message.role === 'user';
  const status = message.status ?? 'done';
  const showSpinner = !isUser && (status === 'sending' || status === 'streaming');

  return (
    <div className={`chat-bubble ${isUser ? 'chat-bubble-user' : 'chat-bubble-assistant'}`}>
      {!isUser && (
        <div className="chat-avatar" aria-hidden="true">
          <AIIcon />
        </div>
      )}
      <div className="chat-bubble-content">
        {isUser ? (
          message.content && (
            <div className="chat-bubble-text chat-bubble-plain">{message.content}</div>
          )
        ) : (
          <EventTimeline message={message} showSpinner={showSpinner} />
        )}

        {message.status === 'error' && message.errorMessage && (
          <div className="chat-bubble-error" role="alert">
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
          <span className="chat-bubble-time">{formatTime(message.timestamp)}</span>
          {(status === 'streaming' || status === 'sending') && onAbort && (
            <button
              type="button"
              className="chat-bubble-abort"
              onClick={onAbort}
              aria-label="Stop"
            >
              Stop
            </button>
          )}
        </div>
      </div>
      {isUser && (
        <div className="chat-avatar chat-avatar-user" aria-hidden="true">
          <UserIcon />
        </div>
      )}
    </div>
  );
}

// --- Event timeline rendering (text / reasoning / tool) ---

function EventTimeline({
  message,
  showSpinner,
}: {
  message: ChatMessageType;
  showSpinner: boolean;
}) {
  const events = message.events;
  if (!events || events.length === 0) {
    return <LegacyBubbleBody message={message} />;
  }

  const groups = groupConsecutiveEvents(events);
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
                events={group.events.filter(
                  (e): e is Extract<ChatEvent, { type: 'reasoning' }> => e.type === 'reasoning',
                )}
              />
            );
          case 'tool':
            return (
              <ToolGroupBlock
                key={`tool-${idx}`}
                events={group.events.filter(
                  (e): e is Extract<ChatEvent, { type: 'tool' }> => e.type === 'tool',
                )}
              />
            );
          default:
            return null;
        }
      })}
    </>
  );
}

function LegacyBubbleBody({ message }: { message: ChatMessageType }) {
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
    </>
  );
}

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
        <span>{open ? 'Hide reasoning' : `Reasoned ${events.length} step${events.length === 1 ? '' : 's'}`}</span>
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
        <span>
          Tool calls ({callCount}) · {open ? 'Hide' : 'Show'}
        </span>
      </button>
      {open && (
        <ol className="chat-tools-list">
          {events.map((tool) => (
            <li key={tool.id} className={`chat-tool-item chat-tool-${tool.phase}`}>
              <div className="chat-tool-header">
                <span className="chat-tool-name">{tool.name}</span>
                <span className={`chat-tool-phase chat-tool-phase-${tool.phase}`}>
                  {tool.phase === 'call' ? 'call' : 'result'}
                </span>
              </div>
              {tool.phase === 'call' && tool.input !== undefined && (
                <pre className="chat-tool-pre">{JSON.stringify(tool.input, null, 2)}</pre>
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
        <span>
          Tool calls ({items.filter((i) => i.phase === 'call').length}) ·{' '}
          {open ? 'Hide' : 'Show'}
        </span>
      </button>
      {open && (
        <ol className="chat-tools-list">
          {items.map((tool) => (
            <li key={tool.id} className={`chat-tool-item chat-tool-${tool.phase}`}>
              <div className="chat-tool-header">
                <span className="chat-tool-name">{tool.name}</span>
                <span className={`chat-tool-phase chat-tool-phase-${tool.phase}`}>
                  {tool.phase === 'call' ? 'call' : 'result'}
                </span>
              </div>
              {tool.phase === 'call' && tool.input !== undefined && (
                <pre className="chat-tool-pre">{JSON.stringify(tool.input, null, 2)}</pre>
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

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return iso;
  }
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
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <path d="M12 6v6l4 2" />
    </svg>
  );
}

function UserIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="8" r="4" />
      <path d="M12 14c-4 0-8 2-8 4v2h16v-2c0-2-4-4-8-4z" />
    </svg>
  );
}