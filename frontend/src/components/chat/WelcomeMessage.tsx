import type { ReactNode } from 'react';
import {
  friendlyScenarioName,
  friendlyScenarioDescription,
  greetingForNow,
  loadUserSnapshot,
  type UpcomingTrip,
} from '../../lib';
import './WelcomeMessage.css';

interface QuickAction {
  label: string;
  value: string;
  icon: ReactNode;
  hint?: string;
  badge?: string;
}

interface WelcomeMessageProps {
  onQuickReply: (value: string) => void;
  backendReady?: boolean;
  scenarioLabel?: string;
}

export function WelcomeMessage({
  onQuickReply,
  backendReady = true,
  scenarioLabel,
}: WelcomeMessageProps) {
  const actions = pickActions(scenarioLabel, backendReady);
  const snapshot = loadUserSnapshot();
  const friendlyName = friendlyScenarioName(scenarioLabel);
  const friendlyDesc = friendlyScenarioDescription(scenarioLabel);
  const greeting = greetingForNow();

  return (
    <div className="welcome-hero">
      <div className="welcome-hero-inner">
        <div className="welcome-hero-avatar" aria-hidden="true">
          <AIIcon />
        </div>
        <h1 className="welcome-hero-title">
          {greeting}, {snapshot.displayName}
        </h1>
        <p className="welcome-hero-subtitle">
          {backendReady
            ? friendlyDesc
            : '无法连接后端服务，请检查 VITE_MCP_TOKEN 与后端是否已启动'}
        </p>

        {backendReady && <SnapshotStrip snapshot={snapshot} />}

        {scenarioLabel && (
          <div className="welcome-hero-scenario-pill" title={`当前场景: ${friendlyName}`}>
            <span className="welcome-hero-scenario-dot" />
            当前: <strong>{friendlyName}</strong>
          </div>
        )}

        {actions.length > 0 && (
          <div className="welcome-hero-grid">
            {actions.map((a) => (
              <button
                key={a.value}
                type="button"
                className="welcome-hero-card"
                onClick={() => onQuickReply(a.value)}
                disabled={!backendReady}
              >
                <span className="welcome-hero-card-icon" aria-hidden="true">
                  {a.icon}
                </span>
                <span className="welcome-hero-card-label">{a.label}</span>
                {a.hint && <span className="welcome-hero-card-hint">{a.hint}</span>}
                {a.badge && <span className="welcome-hero-card-badge">{a.badge}</span>}
              </button>
            ))}
          </div>
        )}

        {backendReady && snapshot.upcomingTrips.length > 0 && (
          <UpcomingTripsWidget trips={snapshot.upcomingTrips.slice(0, 3)} onAction={onQuickReply} />
        )}
      </div>
    </div>
  );
}

function SnapshotStrip({ snapshot }: { snapshot: ReturnType<typeof loadUserSnapshot> }) {
  return (
    <div className="welcome-hero-snapshot">
      <div className="snapshot-item">
        <span className="snapshot-num">{snapshot.recentTripCount}</span>
        <span className="snapshot-label">近 30 天出行</span>
      </div>
      <div className="snapshot-divider" />
      <div className="snapshot-item">
        <span
          className="snapshot-num"
          data-level={snapshot.complianceHitRate >= 0.9 ? 'ok' : snapshot.complianceHitRate >= 0.7 ? 'warn' : 'over'}
        >
          {Math.round(snapshot.complianceHitRate * 100)}%
        </span>
        <span className="snapshot-label">差标命中率</span>
      </div>
      <div className="snapshot-divider" />
      <div className="snapshot-item">
        <span className="snapshot-num">{snapshot.pendingOrderCount}</span>
        <span className="snapshot-label">待处理订单</span>
      </div>
    </div>
  );
}

function UpcomingTripsWidget({
  trips,
  onAction,
}: {
  trips: UpcomingTrip[];
  onAction: (value: string) => void;
}) {
  return (
    <div className="welcome-hero-upcoming">
      <div className="upcoming-header">
        <span className="upcoming-title">近期行程</span>
        <button
          type="button"
          className="upcoming-action"
          onClick={() => onAction('查看我的全部行程')}
        >
          查看全部 →
        </button>
      </div>
      <ul className="upcoming-list">
        {trips.map((t) => (
          <li key={t.id} className="upcoming-item">
            <div className="upcoming-date">
              <span className="upcoming-date-day">{t.date.slice(5)}</span>
              <span className="upcoming-date-route">{t.route}</span>
            </div>
            <div className="upcoming-meta">
              <span className="upcoming-flight">{t.flightNo}</span>
              <span className="upcoming-cabin">{t.cabin}</span>
            </div>
            <button
              type="button"
              className="upcoming-rebook"
              onClick={() => onAction(`帮我再订一次 ${t.route} ${t.date} 的机票, 跟上次 ${t.flightNo} 类似`)}
              title="一键重订同样行程"
            >
              再来一次
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function pickActions(label?: string, backendReady = true): QuickAction[] {
  if (!backendReady) {
    return [
      { label: '差旅规则', value: '差旅规则是什么', icon: <BookIcon />, hint: '查看公司差旅标准' },
    ];
  }
  if (label === 'flight_booking' || label === 'flight_booking_v2') {
    return [
      { label: '订机票', value: '帮我订明天北京到上海的经济舱', icon: <PlaneIcon />, hint: '按差标预订, 全程引导' },
      { label: '查航班', value: '帮我查下周二上海到深圳的航班', icon: <SearchIcon />, hint: '单程/往返, 实时价格' },
      { label: '多城差旅', value: '下周我要从北京去上海，再去杭州，最后回北京，帮我规划机票和酒店', icon: <RouteIcon />, hint: '多城市机票 + 酒店规划' },
      { label: '预算合规', value: '我去上海出差，机票和酒店总预算 3000，帮我做一个合规方案', icon: <BudgetIcon />, hint: '预算 + 差标约束' },
      { label: '端午出行', value: '端午节给我推荐 3 个适合从北京出发的出行目的地，并规划 3 天 2 晚行程，帮我订酒店和机票，并给我一个游玩攻略', icon: <TripIcon />, hint: '目的地 + 行程 + 酒店机票' },
      { label: '我的订单', value: '查看我的订单', icon: <TicketIcon />, hint: '待支付 / 待出行 / 已完成' },
      { label: '差旅规则', value: '差旅规则是什么', icon: <BookIcon />, hint: '舱位/价格上限' },
    ];
  }
  // flight_query + 通用 (含 v3) — 主推"查 + 查+订"
  return [
    { label: '查机票', value: '帮我查一下北京到上海明天的单程机票', icon: <SearchIcon />, hint: '用城市名查, 不用三字码' },
    { label: '订机票', value: '帮我订明天北京到上海的经济舱', icon: <PlaneIcon />, hint: '跳到预订流程' },
    { label: '多城差旅', value: '下周我要从北京去上海，再去杭州，最后回北京，帮我规划机票和酒店', icon: <RouteIcon />, hint: '多城市机票 + 酒店规划' },
    { label: '预算合规', value: '我去上海出差，机票和酒店总预算 3000，帮我做一个合规方案', icon: <BudgetIcon />, hint: '预算 + 差标约束' },
    { label: '端午出行', value: '端午节给我推荐 3 个适合从北京出发的出行目的地，并规划 3 天 2 晚行程，帮我订酒店和机票，并给我一个游玩攻略', icon: <TripIcon />, hint: '目的地 + 行程 + 酒店机票' },
    { label: '我的订单', value: '查看我的订单', icon: <TicketIcon />, hint: '差旅订单状态' },
    { label: '差旅规则', value: '差旅规则是什么', icon: <BookIcon />, hint: '公司差旅标准' },
  ];
}

// --- inline icons ---

function AIIcon() {
  return (
    <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <path d="M12 6v6l4 2" />
      <circle cx="12" cy="12" r="3" fill="currentColor" stroke="none" opacity="0.15" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  );
}

function PlaneIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" />
    </svg>
  );
}

function TicketIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M3 9a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v2a2 2 0 0 0 0 4v2a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-2a2 2 0 0 0 0-4V9z" />
      <path d="M9 7v10" strokeDasharray="2 2" />
    </svg>
  );
}

function BookIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
    </svg>
  );
}

function RouteIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <circle cx="5" cy="6" r="2" />
      <circle cx="19" cy="18" r="2" />
      <path d="M7 6h5a3 3 0 0 1 0 6H9a3 3 0 0 0 0 6h8" />
    </svg>
  );
}

function BudgetIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M4 7h16v12H4z" />
      <path d="M4 10h16" />
      <path d="M8 15h3" />
      <path d="M16 15h1" />
    </svg>
  );
}

function TripIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M3 20h18" />
      <path d="M5 20 12 4l7 16" />
      <path d="M8 14h8" />
      <path d="M9.5 10h5" />
    </svg>
  );
}
