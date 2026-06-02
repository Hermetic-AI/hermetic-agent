import { useState, type ReactNode } from 'react';
import { Sidebar } from './Sidebar';
import { SettingsPanel } from './SettingsPanel';
import './MainLayout.css';

interface MainLayoutProps {
  children: ReactNode;
  activeNav: string;
  onNavChange: (id: string) => void;
}

export function MainLayout({ children, activeNav, onNavChange }: MainLayoutProps) {
  const [settingsOpen, setSettingsOpen] = useState(false);
  return (
    <div className="main-layout">
      <Sidebar
        activeId={activeNav}
        onNavChange={onNavChange}
        onOpenSettings={() => setSettingsOpen(true)}
      />
      <main className="main-content">{children}</main>
      <SettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}
