import { useEffect, useState, useCallback } from 'react';
import type { ChatMessage } from '../../types';
import { useChatStream, useChatSession, useHealth } from '../../hooks';
import { MessageList, ChatInput, ChatBubble, WelcomeMessage } from '../chat';
import './ChatPage.css';

interface ChatPageProps {
  onQuickReply?: (message: string) => void;
  /** Pending prompt injected from another page (e.g. "Ask AI" on Search/Orders). */
  pendingPrompt?: string | null;
  /** Cleared once the prompt has been consumed. */
  onPendingPromptConsumed?: () => void;
}

export function ChatPage({
  onQuickReply,
  pendingPrompt,
  onPendingPromptConsumed,
}: ChatPageProps) {
  const session = useChatSession();
  const { state: healthState, ready } = useHealth(20_000);
  const agentName = pickAgentName(ready);
  const chat = useChatStream({
    sessionId: session.sessionId ?? undefined,
    onSessionChange: (id) => session.setSessionId(id),
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
      .then((items) => {
        if (cancelled) return;
        if (items.length > 0) {
          chat.reset();
          // Stash the items via a fresh send? Easier: expose history on
          // useChatStream.  Since we don't want to overhaul the hook now,
          // we instead simply skip auto-restoring and require explicit
          // "load history" UX in a later iteration.
        }
        setHistoryLoaded(true);
      })
      .catch(() => setHistoryLoaded(true));
    return () => {
      cancelled = true;
    };
    // We intentionally do not depend on `chat` to avoid re-trigger loops.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.sessionId]);

  // Surface the active status for the welcome / input row.
  const isBusy = chat.status === 'sending' || chat.status === 'streaming';

  // Inject prompt from outside (e.g. Search/Orders "Ask AI" button).
  useEffect(() => {
    if (!pendingPrompt) return;
    if (isBusy) return;
    chat.send(pendingPrompt);
    onPendingPromptConsumed?.();
    onQuickReply?.(pendingPrompt);
  }, [pendingPrompt, isBusy, chat, onPendingPromptConsumed, onQuickReply]);

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
      <HealthBanner state={healthState} sessionLabel={labelFor(session.info)} />
      {chat.messages.length === 0 ? (
        <WelcomeMessage onQuickReply={handleQuickReply} backendReady={healthState === 'healthy'} />
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
          {chat.error}
          <button
            type="button"
            className="chat-page-error-dismiss"
            onClick={() => chat.reset()}
            aria-label="关闭错误"
          >
            ×
          </button>
        </div>
      )}
      <ChatInput onSend={handleSend} disabled={isBusy} />
    </div>
  );
}

function pickAgentName(ready: ReturnType<typeof useHealth>['ready']): string | undefined {
  if (!ready?.agents) return undefined;
  const names = Object.keys(ready.agents);
  return names[0];
}

function labelFor(info: { agent_name?: string; session_id?: string } | null): string {
  if (!info) return '未建立会话';
  const shortId = (info.session_id ?? '').slice(0, 8);
  return `${info.agent_name ?? 'agent'} · ${shortId || '...'}`;
}

function HealthBanner({
  state,
  sessionLabel,
}: {
  state: ReturnType<typeof useHealth>['state'];
  sessionLabel: string;
}) {
  let text = '';
  let cls = 'chat-health-banner';
  switch (state) {
    case 'healthy':
      text = `已连接 · ${sessionLabel}`;
      cls += ' is-healthy';
      break;
    case 'degraded':
      text = '后端就绪检查未通过，部分功能可能不可用';
      cls += ' is-degraded';
      break;
    case 'unreachable':
      text = '无法连接后端，请确认服务已启动';
      cls += ' is-unreachable';
      break;
    case 'unknown':
    default:
      text = '正在连接后端…';
      break;
  }
  return <div className={cls}>{text}</div>;
}
