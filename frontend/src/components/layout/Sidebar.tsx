import { useHealth } from '../../hooks';
import './Sidebar.css';

interface SidebarProps {
  activeId: string;
  onNavChange: (id: string) => void;
  onOpenSettings?: () => void;
}

export function Sidebar({ activeId, onNavChange, onOpenSettings }: SidebarProps) {
  const { state } = useHealth();
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <span className="sidebar-logo">AI Chat</span>
      </div>

      <nav className="sidebar-nav">
        <button
          type="button"
          className={`sidebar-nav-item ${activeId === 'chat' ? 'is-active' : ''}`}
          onClick={() => onNavChange('chat')}
        >
          <span className="sidebar-nav-icon"><ChatIcon /></span>
          <span className="sidebar-nav-label">Chat</span>
        </button>
        <button
          type="button"
          className={`sidebar-nav-item ${activeId === 'assets' ? 'is-active' : ''}`}
          onClick={() => onNavChange('assets')}
        >
          <span className="sidebar-nav-icon"><AssetsIcon /></span>
          <span className="sidebar-nav-label">Assets</span>
        </button>
      </nav>

      <div className="sidebar-footer">
        <HealthIndicator state={state} />
        <button
          type="button"
          className="sidebar-nav-item"
          onClick={onOpenSettings}
        >
          <span className="sidebar-nav-icon"><SettingsIcon /></span>
          <span className="sidebar-nav-label">Settings</span>
        </button>
      </div>
    </aside>
  );
}

function HealthIndicator({ state }: { state: ReturnType<typeof useHealth>['state'] }) {
  const label =
    state === 'healthy'
      ? 'Connected'
      : state === 'degraded'
        ? 'Degraded'
        : state === 'unreachable'
          ? 'Offline'
          : 'Connecting';
  return (
    <div className={`health-indicator health-${state}`} title={`Backend: ${label}`}>
      <span className="health-dot" />
      <span className="health-label">{label}</span>
    </div>
  );
}

function ChatIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  );
}

function AssetsIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
      <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
      <line x1="12" y1="22.08" x2="12" y2="12" />
    </svg>
  );
}

function SettingsIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}