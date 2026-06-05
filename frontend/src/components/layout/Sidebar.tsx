import { useEffect, useState, type ReactNode } from 'react';
import { useHealth, useScenarios } from '../../hooks';
import { friendlyScenarioName, friendlyScenarioDescription, loadUserSnapshot } from '../../lib';
import type { ScenarioSummary } from '../../types';
import './Sidebar.css';

type NavItem = {
  id: string;
  label: string;
  icon: ReactNode;
  badgeKey?: 'pending' | 'confirmed' | 'rules';
};

interface SidebarProps {
  activeId: string;
  onNavChange: (id: string) => void;
  onOpenSettings?: () => void;
  scenario?: string;
  onScenarioChange?: (scenario: string | undefined) => void;
}

const navItems: NavItem[] = [
  { id: 'chat', label: '智能助手', icon: <ChatIcon /> },
  { id: 'search', label: '机票查询', icon: <SearchIcon /> },
  { id: 'orders', label: '我的订单', icon: <OrderIcon />, badgeKey: 'pending' },
  { id: 'rules', label: '差旅规则', icon: <RulesIcon /> },
];

const STATIC_BADGE: Record<string, number> = {
  // 真实接入会从后端 /agent/orders/summary 拉,这里先用 mock 数量,跟
  // OrdersPage 里的 mock 保持一致.
  pending: 1,
  confirmed: 1,
};

export function Sidebar({
  activeId,
  onNavChange,
  onOpenSettings,
  scenario,
  onScenarioChange,
}: SidebarProps) {
  const { state } = useHealth();
  const { scenarios } = useScenarios();
  const [open, setOpen] = useState(false);
  const [pendingCount, setPendingCount] = useState(0);
  const [confirmedCount, setConfirmedCount] = useState(0);

  useEffect(() => {
    // 真实接入: const res = await orderService.summary(); setPendingCount(res.pending);
    // demo 用 localStorage + 静态兜底,等接入后端即可替换.
    void loadUserSnapshot(); // 触发现有数据
    setPendingCount(STATIC_BADGE.pending ?? 0);
    setConfirmedCount(STATIC_BADGE.confirmed ?? 0);
  }, []);

  const pickable: ScenarioSummary[] = scenarios.filter(
    (s) => s.enabled !== false,
  );

  const activeScenarioName = friendlyScenarioName(scenario);
  const activeScenarioDesc = scenario ? friendlyScenarioDescription(scenario) : '由后端按 keyword 推断';

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <span className="logo-text">OpenAgent</span>
        <span className="sidebar-tagline">差旅 AI 调度中心</span>
      </div>

      {onScenarioChange && pickable.length > 0 && (
        <div className={`sidebar-scenario ${open ? 'is-open' : ''}`}>
          <button
            type="button"
            className="sidebar-scenario-toggle"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            title={`当前场景: ${activeScenarioName}`}
          >
            <span className="sidebar-scenario-dot" />
            <span className="sidebar-scenario-label">{activeScenarioName}</span>
            <span className="sidebar-scenario-caret">▾</span>
          </button>
          {open && (
            <ul className="sidebar-scenario-list" role="menu">
              <li>
                <button
                  type="button"
                  className={`sidebar-scenario-item ${!scenario ? 'is-active' : ''}`}
                  onClick={() => {
                    onScenarioChange(undefined);
                    setOpen(false);
                  }}
                >
                  <span className="sidebar-scenario-item-name">自动路由</span>
                  <span className="sidebar-scenario-item-hint">{activeScenarioDesc}</span>
                </button>
              </li>
              {pickable.map((s) => {
                const isActive = scenario === s.name;
                return (
                  <li key={s.name}>
                    <button
                      type="button"
                      className={`sidebar-scenario-item ${isActive ? 'is-active' : ''}`}
                      onClick={() => {
                        onScenarioChange(s.name);
                        setOpen(false);
                      }}
                    >
                      <span className="sidebar-scenario-item-name">
                        {friendlyScenarioName(s.name)}
                      </span>
                      {(s.description || friendlyScenarioDescription(s.name)) && (
                        <span className="sidebar-scenario-item-hint">
                          {s.description || friendlyScenarioDescription(s.name)}
                        </span>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}

      <nav className="sidebar-nav">
        {navItems.map((item) => {
          const badge =
            item.badgeKey === 'pending'
              ? pendingCount
              : item.badgeKey === 'confirmed'
                ? confirmedCount
                : 0;
          return (
            <button
              key={item.id}
              className={`nav-item ${activeId === item.id ? 'nav-item-active' : ''}`}
              onClick={() => onNavChange(item.id)}
            >
              <span className="nav-icon">{item.icon}</span>
              <span className="nav-label">{item.label}</span>
              {badge > 0 && (
                <span
                  className={`nav-badge ${item.badgeKey === 'pending' ? 'nav-badge-pending' : 'nav-badge-confirmed'}`}
                  title={item.badgeKey === 'pending' ? `${badge} 个待支付` : `${badge} 个待出行`}
                >
                  {badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>
      <div className="sidebar-footer">
        <HealthIndicator state={state} />
        <button
          type="button"
          className="nav-item"
          onClick={onOpenSettings}
        >
          <span className="nav-icon"><SettingsIcon /></span>
          <span className="nav-label">设置</span>
        </button>
      </div>
    </aside>
  );
}

function HealthIndicator({ state }: { state: ReturnType<typeof useHealth>['state'] }) {
  const label =
    state === 'healthy'
      ? '已连接'
      : state === 'degraded'
        ? '降级'
        : state === 'unreachable'
          ? '离线'
          : '连接中';
  return (
    <div className={`health-indicator health-${state}`} title={`后端状态: ${label}`}>
      <span className="health-dot" />
      <span className="health-label">后端 {label}</span>
    </div>
  );
}

function ChatIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  );
}

function OrderIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
    </svg>
  );
}

function RulesIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
    </svg>
  );
}

function SettingsIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}
