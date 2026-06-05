import { useCallback, useState } from 'react';
import { MainLayout } from './components/layout';
import { ChatPage } from './components/chat/ChatPage';
import { SearchPage } from './components/flight/SearchPage';
import { OrdersPage } from './components/order/OrdersPage';
import { RulesPage } from './components/order/RulesPage';
import { HealthProvider } from './contexts/HealthContext';
import { logger } from './utils/logger';

type NavId = 'chat' | 'search' | 'orders' | 'rules';

function App() {
  const [activeNav, setActiveNav] = useState<NavId>('chat');
  // A prompt injected from another page into the chat.  The ChatPage
  // consumes it and calls `onPendingPromptConsumed` to clear it.
  const [pendingPrompt, setPendingPrompt] = useState<string | null>(null);
  // The active scenario routing hint.  Persists across navigations so
  // going "chat → search → chat" stays in the same flow.
  const [scenario, setScenario] = useState<string | undefined>('flight_query');

  const handleNavChange = useCallback((id: string) => {
    logger.info('Navigation changed', { id });
    setActiveNav(id as NavId);
  }, []);

  const handleAskAI = useCallback(
    (prompt: string, hintScenario?: string) => {
      logger.info('Cross-page prompt to AI', { prompt, hintScenario });
      if (hintScenario) {
        setScenario(hintScenario);
      }
      setPendingPrompt(prompt);
      setActiveNav('chat');
    },
    [],
  );

  const handlePendingPromptConsumed = useCallback(() => {
    setPendingPrompt(null);
  }, []);

  const handleScenarioChange = useCallback((next: string | undefined) => {
    setScenario(next);
    logger.info('Scenario changed', { scenario: next });
  }, []);

  const renderContent = () => {
    switch (activeNav) {
      case 'chat':
        return (
          <ChatPage
            onQuickReply={(m) => logger.info('Quick reply', { m })}
            pendingPrompt={pendingPrompt}
            onPendingPromptConsumed={handlePendingPromptConsumed}
            scenario={scenario}
            scenarioLabel={scenario}
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
            onQuickReply={(m) => logger.info('Quick reply', { m })}
            scenario={scenario}
            scenarioLabel={scenario}
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
