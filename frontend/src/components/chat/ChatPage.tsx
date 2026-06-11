import { useCallback, useEffect, useState } from 'react';
import type { ChatMessage } from '../../types';
import { useChatStream, useChatSession, useHealth } from '../../hooks';
import { MessageList, ChatInput, ChatBubble, WelcomeMessage } from '../chat';
import { questionService } from '../../services';
import { config } from '../../config';
import { friendlyScenarioName, friendlyScenarioDescription } from '../../lib';
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
  /**
   * 用户点了「新建对话」按钮. 父组件 App.tsx 收到后清掉 localStorage
   * 并 bump chatKey,触发整 ChatPage remount.  这里不直接做事,纯粹通知.
   */
  onNewChat?: () => void;
}

export function ChatPage({
  onQuickReply,
  pendingPrompt,
  onPendingPromptConsumed,
  scenario,
  scenarioLabel,
  onNewChat,
}: ChatPageProps) {
  const session = useChatSession();
  const { state: healthState, ready } = useHealth();
  const agentName = pickAgentName(ready);
  const chat = useChatStream({
    sessionId: session.sessionId ?? undefined,
    onSessionChange: (id) => session.setSessionId(id),
    // 后端 in-memory store 丢失 (容器重启/部署) 时, 主动清掉 localStorage
    // 里的 session_id, 下次发送自动建新 session.
    onSessionExpired: () => session.setSessionId(null),
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
    (userInput: Record<string, unknown>, actionId?: string, cardId?: string) => {
      chat.resumeTurn(userInput, actionId, cardId);
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
  // 优先从 events[] 时间线里抽 state 事件 (新数据源), 兜底用老字段.
  const allStateEvents = chat.messages.flatMap((m) => {
    const fromEvents = (m.events ?? [])
      .filter((e): e is Extract<typeof e, { type: 'state' }> => e.type === 'state')
      .map((e) => ({ state: e.state, note: e.note, at: e.at }));
    return fromEvents.length > 0 ? fromEvents : (m.stateEvents ?? []);
  });
  const latestState = allStateEvents[allStateEvents.length - 1] ?? null;
  const currentState = chat.currentState ?? latestState?.state ?? null;
  const stateEvents = allStateEvents.filter(
    (s) => s.state === currentState || s.state !== chat.currentState,
  );
  const scenarioView = chat.scenario;

  return (
    <div className="chat-page">
      <HealthBanner
        state={healthState}
        sessionLabel={labelFor(session.info)}
        scenarioLabel={scenarioLabel}
        tokenConfigured={Boolean(config.mcpToken)}
      />
      {onNewChat && (
        <ChatToolbar scenarioLabel={scenarioLabel} onNewChat={onNewChat} />
      )}
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
  const friendlyName = scenarioLabel ? friendlyScenarioName(scenarioLabel) : null;
  const friendlyDesc = scenarioLabel ? friendlyScenarioDescription(scenarioLabel) : null;
  return (
    <div className={cls}>
      <div className="chat-health-banner-left">
        <span>{text}</span>
        {friendlyName && (
          <span
            className="chat-scenario-chip"
            title={friendlyDesc ?? ''}
          >
            <span className="chat-scenario-chip-dot" />
            {friendlyName}
          </span>
        )}
      </div>
      {!tokenConfigured && (
        <span className="chat-health-banner-warn" title="未配置 VITE_MCP_TOKEN，部分 MCP 工具可能 401">
          ⚠ 未配置 MCP Token
        </span>
      )}
    </div>
  );
}

function ChatToolbar({
  scenarioLabel,
  onNewChat,
}: {
  scenarioLabel?: string;
  onNewChat: () => void;
}) {
  const friendlyName = scenarioLabel ? friendlyScenarioName(scenarioLabel) : '自动路由';
  return (
    <div className="chat-toolbar">
      <div className="chat-toolbar-title">
        <span className="chat-toolbar-icon" aria-hidden="true">
          <ChatBubbleIcon />
        </span>
        <span className="chat-toolbar-label">智能助手</span>
        <span className="chat-toolbar-divider">·</span>
        <span className="chat-toolbar-scenario" title={friendlyName}>
          {friendlyName}
        </span>
      </div>
      <div className="chat-toolbar-actions">
        <button
          type="button"
          className="chat-toolbar-new-btn"
          onClick={onNewChat}
          title="清空当前对话, 开一个新会话 (场景保持不变)"
        >
          <PlusIcon />
          <span>新建对话</span>
        </button>
      </div>
    </div>
  );
}

function ChatBubbleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}
