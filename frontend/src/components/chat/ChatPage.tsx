import { useCallback, useEffect, useState } from 'react';
import type { ChatMessage } from '../../types';
import { useChatStream, useChatSession, useHealth } from '../../hooks';
import { MessageList, ChatInput, ChatBubble, WelcomeMessage } from '../chat';
import { config } from '../../config';
import './ChatPage.css';

interface ChatPageProps {
  onQuickReply?: (message: string) => void;
  /** Pending prompt injected from another page. */
  pendingPrompt?: string | null;
  /** Cleared once the prompt has been consumed. */
  onPendingPromptConsumed?: () => void;
  /**
   * User clicked "New chat".  Parent App.tsx clears localStorage and bumps
   * chatKey to remount this whole tree.
   */
  onNewChat?: () => void;
}

export function ChatPage({
  onQuickReply,
  pendingPrompt,
  onPendingPromptConsumed,
  onNewChat,
}: ChatPageProps) {
  const session = useChatSession();
  const { state: healthState, ready } = useHealth();
  const agentName = pickAgentName(ready);
  const chat = useChatStream({
    sessionId: session.sessionId ?? undefined,
    onSessionChange: (id) => session.setSessionId(id),
    onSessionExpired: () => session.setSessionId(null),
    agentName,
  });

  // Pull existing history once when we know the session id.
  const [historyLoaded, setHistoryLoaded] = useState(false);
  useEffect(() => {
    if (!session.sessionId) {
      setHistoryLoaded(false);
      chat.reset();
      return;
    }
    if (historyLoaded) return;
    let cancelled = false;
    session
      .loadHistory(session.sessionId)
      .then(() => {
        if (cancelled) return;
        setHistoryLoaded(true);
      })
      .catch(() => setHistoryLoaded(true));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.sessionId]);

  const isBusy = chat.status === 'sending' || chat.status === 'streaming';

  // Inject prompt from outside.
  useEffect(() => {
    if (!pendingPrompt) return;
    if (isBusy) return;
    chat.send(pendingPrompt);
    onPendingPromptConsumed?.();
    onQuickReply?.(pendingPrompt);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingPrompt, isBusy]);

  const handleSend = useCallback(
    (content: string) => {
      chat.send(content);
    },
    [chat],
  );

  const handleQuickReply = useCallback(
    (value: string) => {
      chat.send(value);
    },
    [chat],
  );

  const handleAbort = useCallback(() => {
    chat.abort();
  }, [chat]);

  return (
    <div className="chat-page">
      <HealthBanner
        state={healthState}
        sessionLabel={labelFor(session.info)}
        tokenConfigured={Boolean(config.mcpToken)}
      />
      {onNewChat && <ChatToolbar onNewChat={onNewChat} />}
      {chat.messages.length === 0 ? (
        <div className="chat-page-empty">
          <WelcomeMessage
            onQuickReply={handleQuickReply}
            backendReady={healthState === 'healthy'}
          />
        </div>
      ) : (
        <MessageList loading={isBusy}>
          {chat.messages.map((msg: ChatMessage) => (
            <ChatBubble
              key={msg.id}
              message={msg}
              onQuickReply={handleQuickReply}
              onAbort={handleAbort}
            />
          ))}
        </MessageList>
      )}
      {chat.error && chat.messages.length > 0 && (
        <div className="chat-page-error" role="alert">
          <span>{chat.error}</span>
          <button
            type="button"
            className="chat-page-error-dismiss"
            onClick={() => chat.reset()}
            aria-label="Dismiss error"
          >
            ×
          </button>
        </div>
      )}
      <ChatInput
        onSend={handleSend}
        disabled={isBusy}
        placeholder={isBusy ? 'Generating...' : 'Message AI...'}
      />
    </div>
  );
}

function pickAgentName(ready: ReturnType<typeof useHealth>['ready']): string | undefined {
  if (!ready?.agents) return undefined;
  if (Array.isArray(ready.agents)) {
    return ready.agents.find((n): n is string => typeof n === 'string' && n.length > 0);
  }
  const names = Object.keys(ready.agents);
  return names.find((n) => n && typeof n === 'string');
}

function labelFor(info: { agent_name?: string; session_id?: string } | null): string {
  if (!info) return 'No session';
  const shortId = (info.session_id ?? '').slice(0, 8);
  return `${info.agent_name ?? 'agent'} · ${shortId || '...'}`;
}

function HealthBanner({
  state,
  sessionLabel,
  tokenConfigured,
}: {
  state: ReturnType<typeof useHealth>['state'];
  sessionLabel: string;
  tokenConfigured: boolean;
}) {
  let text = '';
  switch (state) {
    case 'healthy':
      text = `Connected · ${sessionLabel}`;
      break;
    case 'degraded':
      text = 'Backend is degraded — some features may be unavailable';
      break;
    case 'unreachable':
      text = 'Cannot reach backend — check the server';
      break;
    case 'unknown':
    default:
      text = 'Connecting to backend...';
  }
  return (
    <div className={`chat-health-banner chat-health-${state}`}>
      <span className="chat-health-dot" />
      <span className="chat-health-text">{text}</span>
      {!tokenConfigured && (
        <span className="chat-health-warn" title="VITE_MCP_TOKEN is not set; some MCP tools may 401">
          No MCP token
        </span>
      )}
    </div>
  );
}

function ChatToolbar({ onNewChat }: { onNewChat: () => void }) {
  return (
    <div className="chat-toolbar">
      <div className="chat-toolbar-title">Chat</div>
      <button
        type="button"
        className="chat-toolbar-new-btn"
        onClick={onNewChat}
        title="Clear the current conversation and start a new session"
      >
        <PlusIcon />
        <span>New chat</span>
      </button>
    </div>
  );
}

function PlusIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}