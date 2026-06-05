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
}

export function MainLayout({
  children,
  activeNav,
  onNavChange,
  scenario,
  onScenarioChange,
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
      <main className="main-content">{children}</main>
      <SettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}
