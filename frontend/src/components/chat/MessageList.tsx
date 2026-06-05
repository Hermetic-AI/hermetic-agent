import { useRef, useEffect, type ReactNode } from 'react';
import { LoadingIcon } from './Icons';
import type { ScenarioView, StateView } from '../../types';
import './MessageList.css';

interface MessageListProps {
  children: ReactNode;
  loading?: boolean;
  scenario?: ScenarioView | null;
  currentState?: string | null;
  stateEvents?: StateView[];
  turnId?: string | null;
  isSuspended?: boolean;
  onCancelTurn?: () => void;
}

export function MessageList({
  children,
  loading = false,
  scenario,
  currentState,
  stateEvents,
  turnId,
  isSuspended,
  onCancelTurn,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [children]);

  const showBanner = Boolean(scenario) || isSuspended || Boolean(turnId);

  return (
    <div className="message-list">
      {showBanner && (
        <div className={`message-list-banner ${isSuspended ? 'is-suspended' : ''}`}>
          <div className="message-list-banner-main">
            {scenario && (
              <span className="message-list-scenario">
                <span className="message-list-scenario-dot" />
                <strong>{scenario.name}</strong>
                {scenario.orchestration && (
                  <span className="message-list-scenario-orch">{scenario.orchestration}</span>
                )}
                {scenario.matched_by && (
                  <span className="message-list-scenario-matched">
                    命中方式: {scenario.matched_by}
                  </span>
                )}
              </span>
            )}
            {currentState && (
              <span className="message-list-state">
                业务状态 <code>{currentState}</code>
                {stateEvents && stateEvents.length > 1 && (
                  <span className="message-list-state-history">
                    ({stateEvents.length} 次切换)
                  </span>
                )}
              </span>
            )}
          </div>
          <div className="message-list-banner-meta">
            {turnId && (
              <span className="message-list-turn" title={turnId}>
                turn {turnId.slice(0, 6)}
              </span>
            )}
            {isSuspended && (
              <span className="message-list-suspend-badge">AI 在等您输入</span>
            )}
            {isSuspended && onCancelTurn && (
              <button
                type="button"
                className="message-list-cancel"
                onClick={onCancelTurn}
              >
                取消本轮
              </button>
            )}
          </div>
        </div>
      )}
      {children}
      {loading && (
        <div className="message-loading">
          <LoadingIcon />
          <span>AI 思考中...</span>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}
