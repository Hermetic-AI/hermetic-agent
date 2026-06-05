import { useCallback, useState } from 'react';
import { MainLayout } from './components/layout';
import { ChatPage } from './components/chat/ChatPage';
import { SearchPage } from './components/flight/SearchPage';
import { OrdersPage } from './components/order/OrdersPage';
import { RulesPage } from './components/order/RulesPage';
import { HealthProvider } from './contexts/HealthContext';
import { logger } from './utils/logger';

type NavId = 'chat' | 'search' | 'orders' | 'rules';

/**
 * 跟 useChatSession 里的 STORAGE_KEY ('openagent.session_id') 保持一致.
 * 当用户切换场景或主动「新建对话」时,我们要:
 *   1. 清掉 localStorage 里残留的旧 session_id,防止下次 mount 误恢复
 *   2. bump chatKey,触发 ChatPage 整树 remount,所有 hooks 状态归零
 */
const SESSION_STORAGE_KEY = 'openagent.session_id';

function clearLocalSession(): void {
  try {
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
  } catch {
    // 隐私模式 / 配额满 — 静默忽略,下次 mount 会拿到 stale id 但不会崩
  }
}

function App() {
  const [activeNav, setActiveNav] = useState<NavId>('chat');
  // A prompt injected from another page into the chat.  The ChatPage
  // consumes it and calls `onPendingPromptConsumed` to clear it.
  const [pendingPrompt, setPendingPrompt] = useState<string | null>(null);
  // The active scenario routing hint.  Persists across navigations so
  // going "chat → search → chat" stays in the same flow.
  const [scenario, setScenario] = useState<string | undefined>('flight_query');

  /**
   * 会话重置钥匙 — bump 即触发 ChatPage 整树 remount.
   * 触发条件 (3 种,都走同一路径):
   *   a) 用户在 sidebar 切换场景           → handleScenarioChange
   *   b) 用户在 ChatPage 顶部点「新建对话」 → handleNewChat (透传 from ChatPage)
   *   c) 用户从 SearchPage/OrdersPage「让 AI 帮我查」切到不同场景
   *      → handleAskAI (同场景则不重置,继续上轮对话)
   */
  const [chatKey, setChatKey] = useState(0);

  const handleNavChange = useCallback((id: string) => {
    logger.info('Navigation changed', { id });
    setActiveNav(id as NavId);
  }, []);

  const handleAskAI = useCallback(
    (prompt: string, hintScenario?: string) => {
      logger.info('Cross-page prompt to AI', { prompt, hintScenario });
      const scenarioChanged = hintScenario !== undefined && hintScenario !== scenario;
      if (scenarioChanged) {
        // 跨场景 → 老会话作废, 重新开
        clearLocalSession();
        setChatKey((k) => k + 1);
        setScenario(hintScenario);
      } else if (hintScenario) {
        setScenario(hintScenario);
      }
      setPendingPrompt(prompt);
      setActiveNav('chat');
    },
    [scenario],
  );

  const handlePendingPromptConsumed = useCallback(() => {
    setPendingPrompt(null);
  }, []);

  const handleScenarioChange = useCallback(
    (next: string | undefined) => {
      if (next === scenario) return;
      logger.info('Scenario changed → reset conversation', { from: scenario, to: next });
      clearLocalSession();
      setScenario(next);
      setChatKey((k) => k + 1);
    },
    [scenario],
  );

  const handleNewChat = useCallback(() => {
    logger.info('User started a new chat', { scenario });
    clearLocalSession();
    setChatKey((k) => k + 1);
    setPendingPrompt(null);
  }, [scenario]);

  const renderContent = () => {
    switch (activeNav) {
      case 'chat':
        return (
          <ChatPage
            key={chatKey}
            onQuickReply={(m) => logger.info('Quick reply', { m })}
            pendingPrompt={pendingPrompt}
            onPendingPromptConsumed={handlePendingPromptConsumed}
            scenario={scenario}
            scenarioLabel={scenario}
            onNewChat={handleNewChat}
          />
        );
      case 'search':
        return (
          <SearchPage
            onAskAI={handleAskAI}
            hintScenario="flight_query"
          />
        );
      case 'orders':
        return (
          <OrdersPage
            onAskAI={handleAskAI}
            hintScenario="flight_booking"
          />
        );
      case 'rules':
        return <RulesPage />;
      default:
        return (
          <ChatPage
            key={chatKey}
            onQuickReply={(m) => logger.info('Quick reply', { m })}
            scenario={scenario}
            scenarioLabel={scenario}
            onNewChat={handleNewChat}
          />
        );
    }
  };

  return (
    <HealthProvider intervalMs={30_000}>
      <MainLayout
        activeNav={activeNav}
        onNavChange={handleNavChange}
        scenario={scenario}
        onScenarioChange={handleScenarioChange}
      >
        {renderContent()}
      </MainLayout>
    </HealthProvider>
  );
}

export default App;
