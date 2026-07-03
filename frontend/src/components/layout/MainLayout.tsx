import { useState, type ReactNode } from 'react';
import { Sidebar } from './Sidebar';
import { SettingsPanel } from './SettingsPanel';
import './MainLayout.css';

interface MainLayoutProps {
  children: ReactNode;
  /** Current top-level nav id (only 'chat' for the generic UI). */
  activeNav: string;
  onNavChange: (id: string) => void;
  /** User label shown in the top bar. */
  userLabel?: string;
  /** Logout callback. */
  onLogout?: () => void;
}

export function MainLayout({
  children,
  activeNav,
  onNavChange,
  userLabel,
  onLogout,
}: MainLayoutProps) {
  const [settingsOpen, setSettingsOpen] = useState(false);
  return (
    <div className="main-layout">
      <Sidebar
        activeId={activeNav}
        onNavChange={onNavChange}
        onOpenSettings={() => setSettingsOpen(true)}
      />
      <main className="main-content">
        {(userLabel || onLogout) && (
          <div className="layout-topbar">
            {userLabel && <span className="layout-user-label">{userLabel}</span>}
            {onLogout && (
              <button
                type="button"
                className="layout-logout-btn"
                onClick={onLogout}
                title="Sign out"
              >
                Sign out
              </button>
            )}
          </div>
        )}
        {children}
      </main>
      <SettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}