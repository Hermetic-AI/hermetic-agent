import { useCallback, useState } from 'react';
import { MainLayout } from './components/layout';
import { ChatPage } from './components/chat/ChatPage';
import { SearchPage } from './components/flight/SearchPage';
import { OrdersPage } from './components/order/OrdersPage';
import { RulesPage } from './components/order/RulesPage';
import { LoginPage } from './components/auth';
import { HealthProvider } from './contexts/HealthContext';
import { AuthProvider, useAuth } from './contexts/AuthContext';
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

interface AppContentProps {
  /** 顶栏显示的当前用户标识 (用户名 / 工号) */
  userLabel?: string;
  /** 顶栏登出按钮回调 */
  onLogout: () => void;
}

/**
 * 已登录态下的真实 UI. 拆出来是为了把"路由守卫"和"业务内容"分清.
 */
function AppContent({ userLabel, onLogout }: AppContentProps) {
  const [activeNav, setActiveNav] = useState<NavId>('chat');
  // A prompt injected from another page into the chat.
  const [pendingPrompt, setPendingPrompt] = useState<string | null>(null);
  // The active scenario routing hint.
  const [scenario, setScenario] = useState<string | undefined>('flight_query');
  // 会话重置钥匙 — bump 即触发 ChatPage 整树 remount
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
        return <SearchPage onAskAI={handleAskAI} hintScenario="flight_query" />;
      case 'orders':
        return <OrdersPage onAskAI={handleAskAI} hintScenario="flight_booking" />;
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
    <MainLayout
      activeNav={activeNav}
      onNavChange={handleNavChange}
      scenario={scenario}
      onScenarioChange={handleScenarioChange}
      userLabel={userLabel}
      onLogout={onLogout}
    >
      {renderContent()}
    </MainLayout>
  );
}

/**
 * 路由守卫: 没登录 → LoginPage 占满屏幕
 * 登出 → 自动回到 LoginPage (因为 isAuthenticated → false)
 */
function AuthedShell() {
  const { isAuthenticated, loginInfo, logout } = useAuth();
  if (!isAuthenticated) {
    return <LoginPage />;
  }
  return (
    <AppContent
      userLabel={loginInfo?.displayName ?? loginInfo?.userCode}
      onLogout={logout}
    />
  );
}

function App() {
  return (
    <HealthProvider intervalMs={30_000}>
      <AuthProvider>
        <AuthedShell />
      </AuthProvider>
    </HealthProvider>
  );
}

export default App;
