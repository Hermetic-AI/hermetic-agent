import { useCallback, useEffect, useState } from 'react';
import type { ChatMessage } from '../../types';
import { useChatStream, useChatSession, useHealth } from '../../hooks';
import { MessageList, ChatInput, ChatBubble, WelcomeMessage } from '../chat';
import { questionService } from '../../services';
import { config } from '../../config';
import './ChatPage.css';

interface ChatPageProps {
  onQuickReply?: (message: string) => void;
  /** Pending prompt injected from another page (e.g. "Ask AI" on Search/Orders). */
  pendingPrompt?: string | null;
  /** Cleared once the prompt has been consumed. */
  onPendingPromptConsumed?: () => void;
  /** Scenario routing hint (X-Scenario + body.scenario). */
  scenario?: string;
  /** Optional override of the displayed scenario name in welcome. */
  scenarioLabel?: string;
}

export function ChatPage({
  onQuickReply,
  pendingPrompt,
  onPendingPromptConsumed,
  scenario,
  scenarioLabel,
}: ChatPageProps) {
  const session = useChatSession();
  const { state: healthState, ready } = useHealth();
  const agentName = pickAgentName(ready);
  const chat = useChatStream({
    sessionId: session.sessionId ?? undefined,
    onSessionChange: (id) => session.setSessionId(id),
    agentName,
    scenario,
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

  const isBusy =
    chat.status === 'sending' ||
    chat.status === 'streaming' ||
    chat.status === 'resuming';

  // Inject prompt from outside (e.g. Search/Orders "Ask AI" button).
  useEffect(() => {
    if (!pendingPrompt) return;
    if (isBusy || chat.isSuspended) return;
    chat.send(pendingPrompt);
    onPendingPromptConsumed?.();
    onQuickReply?.(pendingPrompt);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingPrompt, isBusy, chat.isSuspended]);

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

  const handleCardSubmit = useCallback(
    (userInput: Record<string, unknown>, actionId?: string) => {
      chat.resumeTurn(userInput, actionId);
    },
    [chat],
  );

  const handleCancelTurn = useCallback(() => {
    void chat.cancelTurn();
  }, [chat]);

  // P7: opencode 原生 question 提交 — 走 questionService.reply (不走 turnService.resume)
  const handleQuestionReply = useCallback(
    async (requestId: string, answers: string[][], sessionId: string) => {
      try {
        await questionService.reply(requestId, { session_id: sessionId, answers });
      } catch (e) {
        // 错误由 user-facing ChatPage error 兜底, 这里只 log
        console.error('questionService.reply failed', e);
        chat.reset();
      }
    },
    [chat],
  );

  // P7: opencode 原生 question 忽略 — 走 questionService.reject
  const handleQuestionReject = useCallback(
    async (requestId: string, sessionId: string) => {
      try {
        await questionService.reject(requestId, sessionId);
      } catch (e) {
        console.error('questionService.reject failed', e);
      }
    },
    [],
  );

  // Aggregate the most recent state from any assistant message.
  const latestState = chat.messages
    .slice()
    .reverse()
    .flatMap((m) => m.stateEvents ?? [])
    .pop();
  const currentState = chat.currentState ?? latestState?.state ?? null;
  const stateEvents = chat.messages
    .flatMap((m) => m.stateEvents ?? [])
    .filter((s) => s.state === currentState || s.state !== chat.currentState);
  const scenarioView = chat.scenario;

  return (
    <div className="chat-page">
      <HealthBanner
        state={healthState}
        sessionLabel={labelFor(session.info)}
        scenarioLabel={scenarioLabel}
        tokenConfigured={Boolean(config.mcpToken)}
      />
      {chat.messages.length === 0 ? (
        <div className="chat-page-empty">
          <WelcomeMessage
            onQuickReply={handleQuickReply}
            backendReady={healthState === 'healthy'}
            scenarioLabel={scenarioLabel}
          />
        </div>
      ) : (
        <MessageList
          loading={isBusy}
          scenario={scenarioView}
          currentState={currentState}
          stateEvents={stateEvents}
          turnId={chat.serverTurnId}
          isSuspended={chat.isSuspended}
          onCancelTurn={handleCancelTurn}
        >
          {chat.messages.map((msg: ChatMessage) => (
            <ChatBubble
              key={msg.id}
              message={msg}
              onQuickReply={handleQuickReply}
              onAbort={handleAbort}
              onCardSubmit={handleCardSubmit}
              onQuestionReply={handleQuestionReply}
              onQuestionReject={handleQuestionReject}
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
      <ChatInput
        onSend={handleSend}
        disabled={isBusy || chat.isSuspended}
        placeholder={
          chat.isSuspended
            ? '请在上方卡片中填写信息以继续…'
            : scenarioLabel
              ? `向 ${scenarioLabel} 提问…`
              : '输入消息…'
        }
      />
    </div>
  );
}

function pickAgentName(ready: ReturnType<typeof useHealth>['ready']): string | undefined {
  if (!ready?.agents) return undefined;
  // 后端 ``/ready`` 返回 ``agents: string[]`` (list of registered names).
  // 之前按 dict 处理 (Object.keys) 会得到 ``["0"]`` 然后把 "0" 当 agent_name
  // 发给后端, 报 ``KeyError: "Agent '0' not registered"`` —— 已修.
  if (Array.isArray(ready.agents)) {
    return ready.agents.find((n): n is string => typeof n === 'string' && n.length > 0);
  }
  // 兜底: 旧版本若返 dict (eg. {"opencode-core": {...}}) 也兼容
  const names = Object.keys(ready.agents);
  return names.find((n) => n && typeof n === 'string');
}

function labelFor(info: { agent_name?: string; session_id?: string } | null): string {
  if (!info) return '未建立会话';
  const shortId = (info.session_id ?? '').slice(0, 8);
  return `${info.agent_name ?? 'agent'} · ${shortId || '...'}`;
}

function HealthBanner({
  state,
  sessionLabel,
  scenarioLabel,
  tokenConfigured,
}: {
  state: ReturnType<typeof useHealth>['state'];
  sessionLabel: string;
  scenarioLabel?: string;
  tokenConfigured: boolean;
}) {
  let text = '';
  let cls = 'chat-health-banner';
  switch (state) {
    case 'healthy':
      text = scenarioLabel
        ? `已连接 · ${scenarioLabel} · ${sessionLabel}`
        : `已连接 · ${sessionLabel}`;
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
  return (
    <div className={cls}>
      <span>{text}</span>
      {!tokenConfigured && (
        <span className="chat-health-banner-warn" title="未配置 VITE_MCP_TOKEN，部分 MCP 工具可能 401">
          ⚠ 未配置 MCP Token
        </span>
      )}
    </div>
  );
}
