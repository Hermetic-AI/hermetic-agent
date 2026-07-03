import { useCallback, useEffect, useState } from 'react';
import { MainLayout } from './components/layout';
import { ChatPage } from './components/chat/ChatPage';
import { LoginPage } from './components/auth';
import { AssetsPage } from './routes/admin/assets';
import { HealthProvider } from './contexts/HealthContext';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { logger } from './utils/logger';
import { ASSET_USE_EVENT, type AssetUseRequest } from './lib';

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
  const [pendingUse, setPendingUse] = useState<AssetUseRequest | null>(null);

  // Listen for "use this asset in chat" dispatched from the Assets tabs.
  // We can't use react-router (not installed) so a CustomEvent is the
  // simplest cross-component channel.
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<AssetUseRequest>).detail;
      logger.info('Use asset in chat', detail);
      setActiveNav('chat');
      setPendingUse(detail);
      // bump chatKey so ChatPage remounts with a fresh session
      setChatKey((k) => k + 1);
    };
    window.addEventListener(ASSET_USE_EVENT, handler);
    return () => window.removeEventListener(ASSET_USE_EVENT, handler);
  }, []);

  const handleNavChange = useCallback((id: string) => {
    logger.info('Navigation changed', { id });
    setActiveNav(id as NavId);
  }, []);

  const handleNewChat = useCallback(() => {
    logger.info('User started a new chat');
    clearLocalSession();
    setChatKey((k) => k + 1);
  }, []);

  const handlePendingUseConsumed = useCallback(() => {
    setPendingUse(null);
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
        : <ChatPage
            key={chatKey}
            onNewChat={handleNewChat}
            pendingUse={pendingUse}
            onPendingUseConsumed={handlePendingUseConsumed}
          />}
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