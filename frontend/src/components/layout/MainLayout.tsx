import { useState, type ReactNode } from 'react';
import { Sidebar } from './Sidebar';
import { SettingsPanel } from './SettingsPanel';
import './MainLayout.css';

interface MainLayoutProps {
  children: ReactNode;
  activeNav: string;
  onNavChange: (id: string) => void;
  scenario?: string;
  onScenarioChange?: (scenario: string | undefined) => void;
  /** 顶栏显示的当前用户标识 */
  userLabel?: string;
  /** 顶栏登出按钮回调 */
  onLogout?: () => void;
}

export function MainLayout({
  children,
  activeNav,
  onNavChange,
  scenario,
  onScenarioChange,
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
        scenario={scenario}
        onScenarioChange={onScenarioChange}
      />
      <main className="main-content">
        {(userLabel || onLogout) && (
          <div className="layout-topbar">
            {userLabel && <span className="layout-user-label">👤 {userLabel}</span>}
            {onLogout && (
              <button
                type="button"
                className="layout-logout-btn"
                onClick={onLogout}
                title="登出, 清掉本地 token"
              >
                登出
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
