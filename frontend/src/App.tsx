import { useCallback, useState } from 'react';
import { MainLayout } from './components/layout';
import { ChatPage } from './components/chat/ChatPage';
import { SearchPage } from './components/flight/SearchPage';
import { OrdersPage } from './components/order/OrdersPage';
import { RulesPage } from './components/order/RulesPage';
import { logger } from './utils/logger';

type NavId = 'chat' | 'search' | 'orders' | 'rules';

function App() {
  const [activeNav, setActiveNav] = useState<NavId>('chat');
  // A prompt injected from another page into the chat.  The ChatPage
  // consumes it and calls `onPendingPromptConsumed` to clear it.
  const [pendingPrompt, setPendingPrompt] = useState<string | null>(null);

  const handleNavChange = useCallback((id: string) => {
    logger.info('Navigation changed', { id });
    setActiveNav(id as NavId);
  }, []);

  const handleAskAI = useCallback((prompt: string) => {
    logger.info('Cross-page prompt to AI', { prompt });
    setPendingPrompt(prompt);
    setActiveNav('chat');
  }, []);

  const handlePendingPromptConsumed = useCallback(() => {
    setPendingPrompt(null);
  }, []);

  const renderContent = () => {
    switch (activeNav) {
      case 'chat':
        return (
          <ChatPage
            onQuickReply={(m) => logger.info('Quick reply', { m })}
            pendingPrompt={pendingPrompt}
            onPendingPromptConsumed={handlePendingPromptConsumed}
          />
        );
      case 'search':
        return <SearchPage onAskAI={handleAskAI} />;
      case 'orders':
        return <OrdersPage onAskAI={handleAskAI} />;
      case 'rules':
        return <RulesPage />;
      default:
        return <ChatPage onQuickReply={(m) => logger.info('Quick reply', { m })} />;
    }
  };

  return (
    <MainLayout activeNav={activeNav} onNavChange={handleNavChange}>
      {renderContent()}
    </MainLayout>
  );
}

export default App;
