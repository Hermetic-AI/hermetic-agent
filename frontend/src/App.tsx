import { useCallback, useState } from 'react';
import { MainLayout } from './components/layout';
import { ChatPage } from './components/chat/ChatPage';
import { LoginPage } from './components/auth';
import { AssetsPage } from './routes/admin/assets';
import { HealthProvider } from './contexts/HealthContext';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { logger } from './utils/logger';

type NavId = 'chat' | 'assets';

/**
 * Session id is persisted in localStorage.  When the user starts a new
 * conversation, we drop the stale id and bump chatKey to remount ChatPage.
 */
const SESSION_STORAGE_KEY = 'chat.session_id';

function clearLocalSession(): void {
  try {
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
  } catch {
    // ignore (privacy / quota)
  }
}

function AppContent({
  userLabel,
  onLogout,
}: {
  userLabel?: string;
  onLogout: () => void;
}) {
  const [activeNav, setActiveNav] = useState<NavId>('chat');
  const [chatKey, setChatKey] = useState(0);

  const handleNavChange = useCallback((id: string) => {
    logger.info('Navigation changed', { id });
    setActiveNav(id as NavId);
  }, []);

  const handleNewChat = useCallback(() => {
    logger.info('User started a new chat');
    clearLocalSession();
    setChatKey((k) => k + 1);
  }, []);

  return (
    <MainLayout
      activeNav={activeNav}
      onNavChange={handleNavChange}
      userLabel={userLabel}
      onLogout={onLogout}
    >
      {activeNav === 'assets'
        ? <AssetsPage />
        : <ChatPage key={chatKey} onNewChat={handleNewChat} />}
    </MainLayout>
  );
}

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