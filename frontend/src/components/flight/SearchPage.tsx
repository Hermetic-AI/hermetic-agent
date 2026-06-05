import { useEffect, useState } from 'react';
import type { Flight } from '../../types';
import { FlightCard } from './FlightCard';
import { Button } from '../common';
import { FlightCardSkeleton, Empty } from '../common';
import { complianceHitRate, checkCompliance } from '../../lib';
import {
  addFavoriteRoute,
  loadFavoriteRoutes,
  removeFavoriteRoute,
  type FavoriteRoute,
} from './favoriteRoutes';
import './SearchPage.css';

const mockFlights: Flight[] = [
  {
    id: '1',
    airline: '中国国际航空',
    airlineCode: 'CA',
    flightNumber: 'CA1234',
    departure: { city: '北京', airport: '首都国际机场', airportCode: 'PEK', time: '08:30', date: '2026-06-01' },
    arrival: { city: '上海', airport: '浦东国际机场', airportCode: 'PVG', time: '10:45', date: '2026-06-01' },
    duration: '2小时15分钟',
    cabinClass: 'economy',
    price: 860,
    tax: 50,
    remainingSeats: 28,
    aircraft: '波音737-800',
  },
  {
    id: '2',
    airline: '东方航空',
    airlineCode: 'MU',
    flightNumber: 'MU5678',
    departure: { city: '北京', airport: '首都国际机场', airportCode: 'PEK', time: '10:00', date: '2026-06-01' },
    arrival: { city: '上海', airport: '浦东国际机场', airportCode: 'PVG', time: '12:20', date: '2026-06-01' },
    duration: '2小时20分钟',
    cabinClass: 'economy',
    price: 780,
    tax: 50,
    remainingSeats: 15,
    aircraft: '空客A320',
  },
  {
    id: '3',
    airline: '南方航空',
    airlineCode: 'CZ',
    flightNumber: 'CZ9012',
    departure: { city: '北京', airport: '大兴国际机场', airportCode: 'PKX', time: '14:30', date: '2026-06-01' },
    arrival: { city: '上海', airport: '虹桥国际机场', airportCode: 'SHA', time: '16:40', date: '2026-06-01' },
    duration: '2小时10分钟',
    cabinClass: 'business',
    price: 2180,
    tax: 80,
    remainingSeats: 8,
    aircraft: '波音787-9',
  },
];

type CabinClass = 'economy' | 'business' | 'first' | 'all';

function todayIso(): string {
  const d = new Date();
  return d.toISOString().slice(0, 10);
}

function addDaysIso(base: string, days: number): string {
  const d = new Date(base);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

/** 常用日期预设: 今天/明天/后天/下个周一. 用于 "差旅快速订". */
const DATE_PRESETS: { id: string; label: string; offset: number }[] = [
  { id: 'today', label: '今天', offset: 0 },
  { id: 'tomorrow', label: '明天', offset: 1 },
  { id: 'dayAfter', label: '后天', offset: 2 },
  { id: 'nextMon', label: '下周一', offset: -1 },
];

function nextWeekdayIso(weekday: number): string {
  const d = new Date();
  const diff = ((weekday - d.getDay() + 7) % 7) || 7;
  return addDaysIso(todayIso(), diff);
}

export function SearchPage({ onAskAI, hintScenario }: { onAskAI?: (prompt: string, hintScenario?: string) => void; hintScenario?: string } = {}) {
  const [loading, setLoading] = useState(false);
  const [selectedCabin, setSelectedCabin] = useState<CabinClass>('economy');
  const [searchParams, setSearchParams] = useState(() => ({
    departure: '北京',
    arrival: '上海',
    date: todayIso(),
    passengers: 1,
  }));
  const [favorites, setFavorites] = useState<FavoriteRoute[]>([]);

  useEffect(() => {
    setFavorites(loadFavoriteRoutes());
  }, []);

  const handleSearch = () => {
    setLoading(true);
    setTimeout(() => setLoading(false), 1200);
  };

  const handleSelect = (flight: Flight) => {
    onAskAI?.(
      `帮我预订 ${flight.flightNumber}，${flight.departure.city}→${flight.arrival.city}，${flight.departure.date} ${flight.departure.time} 出发。`,
      'flight_booking',
    );
  };

  /** "让 AI 帮我查" — 把当前表单内容转成自然语言 prompt,塞进 chat. */
  const handleAskAI = () => {
    const { departure, arrival, date, passengers } = searchParams;
    if (!departure.trim() || !arrival.trim()) {
      onAskAI?.(
        '我想查机票,但还没填完出发和到达,你能帮我想几个常见出差组合吗?',
        hintScenario ?? 'flight_query',
      );
      return;
    }
    onAskAI?.(
      `帮我查 ${date} 从 ${departure} 到 ${arrival} 的机票，${passengers} 人。请用中文城市名查询, 不要使用三字码。`,
      hintScenario ?? 'flight_query',
    );
  };

  /** "让 AI 接下去" — 当用户填了部分表单但想去 chat 里继续微调 (比如加筛选条件),用这个. */
  const handleHandoff = () => {
    const { departure, arrival, date, passengers } = searchParams;
    const partial = [
      departure && `从 ${departure}`,
      arrival && `到 ${arrival}`,
      date && `${date} 出发`,
      passengers > 1 && `${passengers} 人`,
    ].filter(Boolean).join(' ');
    onAskAI?.(
      `我已经在搜索表单填了${partial}, 但想再加一些筛选 (舱等/航司/时段/直飞等), 帮我用对话接下去查。`,
      hintScenario ?? 'flight_query',
    );
  };

  const handleSwap = () => {
    setSearchParams((p) => ({ ...p, departure: p.arrival, arrival: p.departure }));
  };

  const handleDatePreset = (offset: number, presetId: string) => {
    let date: string;
    if (presetId === 'nextMon') {
      date = nextWeekdayIso(1);
    } else {
      date = addDaysIso(todayIso(), offset);
    }
    setSearchParams((p) => ({ ...p, date }));
  };

  const handleAddFavorite = () => {
    if (!searchParams.departure.trim() || !searchParams.arrival.trim()) return;
    addFavoriteRoute({
      departure: searchParams.departure,
      arrival: searchParams.arrival,
    });
    setFavorites(loadFavoriteRoutes());
  };

  const handleRemoveFavorite = (id: string) => {
    removeFavoriteRoute(id);
    setFavorites(loadFavoriteRoutes());
  };

  const handleApplyFavorite = (fav: FavoriteRoute) => {
    setSearchParams((p) => ({ ...p, departure: fav.departure, arrival: fav.arrival }));
  };

  const filteredFlights = selectedCabin === 'all'
    ? mockFlights
    : mockFlights.filter((f) => f.cabinClass === selectedCabin || f.price < 2000);

  const cabinOptions: { value: CabinClass; label: string }[] = [
    { value: 'all', label: '全部' },
    { value: 'economy', label: '经济舱' },
    { value: 'business', label: '商务舱' },
    { value: 'first', label: '头等舱' },
  ];

  const isFavorited = favorites.some(
    (f) => f.departure === searchParams.departure && f.arrival === searchParams.arrival,
  );

  const stats = complianceHitRate(filteredFlights);

  return (
    <div className="search-page">
      <div className="search-header">
        <h1>机票查询</h1>
        <p className="search-subtitle">
          下方展示为示例航班; 点击「让 AI 帮我查」可唤起 AI 助手实时查询 (支持自然语言补充筛选条件)。
        </p>
      </div>

      {favorites.length > 0 && (
        <div className="search-favorites">
          <div className="search-favorites-header">
            <span className="search-favorites-title">⭐ 我的常飞</span>
            <span className="search-favorites-hint">点一下秒填表单</span>
          </div>
          <div className="search-favorites-list">
            {favorites.map((fav) => (
              <div key={fav.id} className="search-favorite-chip">
                <button
                  type="button"
                  className="search-favorite-main"
                  onClick={() => handleApplyFavorite(fav)}
                  title={`${fav.departure} → ${fav.arrival}`}
                >
                  {fav.departure} → {fav.arrival}
                </button>
                <button
                  type="button"
                  className="search-favorite-remove"
                  onClick={() => handleRemoveFavorite(fav.id)}
                  aria-label="删除收藏"
                  title="删除收藏"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="search-form-card">
        <div className="search-form">
          <div className="search-field">
            <label>出发城市</label>
            <input
              type="text"
              value={searchParams.departure}
              onChange={(e) => setSearchParams({ ...searchParams, departure: e.target.value })}
              placeholder="请输入出发城市"
            />
          </div>
          <button
            className="swap-btn"
            type="button"
            aria-label="交换出发与到达"
            onClick={handleSwap}
          >
            <SwapIcon />
          </button>
          <div className="search-field">
            <label>到达城市</label>
            <input
              type="text"
              value={searchParams.arrival}
              onChange={(e) => setSearchParams({ ...searchParams, arrival: e.target.value })}
              placeholder="请输入到达城市"
            />
          </div>
          <div className="search-field">
            <label>出发日期</label>
            <input
              type="date"
              value={searchParams.date}
              min={todayIso()}
              onChange={(e) => setSearchParams({ ...searchParams, date: e.target.value })}
            />
          </div>
          <div className="search-field search-field-narrow">
            <label>乘客</label>
            <select
              value={searchParams.passengers}
              onChange={(e) => setSearchParams({ ...searchParams, passengers: Number(e.target.value) })}
            >
              {[1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={n}>{n}人</option>
              ))}
            </select>
          </div>
          <div className="search-form-actions">
            <Button onClick={handleSearch} className="search-btn">
              搜索
            </Button>
            {onAskAI && (
              <>
                <Button variant="secondary" onClick={handleAskAI} className="search-ai-btn">
                  <SparkleIcon />
                  让 AI 帮我查
                </Button>
                <Button variant="text" onClick={handleHandoff} className="search-handoff-btn" title="把当前已填字段交给 AI, 用对话继续补筛选">
                  <HandoffIcon />
                  AI 接下去
                </Button>
              </>
            )}
          </div>
        </div>

        <div className="search-date-presets">
          {DATE_PRESETS.map((preset) => (
            <button
              key={preset.id}
              type="button"
              className="search-date-chip"
              onClick={() => handleDatePreset(preset.offset, preset.id)}
            >
              {preset.label}
            </button>
          ))}
          <button
            type="button"
            className={`search-fav-btn ${isFavorited ? 'is-active' : ''}`}
            onClick={handleAddFavorite}
            disabled={isFavorited}
            title={isFavorited ? '已收藏' : '收藏此路线'}
          >
            {isFavorited ? '★ 已收藏' : '☆ 收藏路线'}
          </button>
        </div>
      </div>

      <div className="search-filters">
        <div className="cabin-tabs">
          {cabinOptions.map((opt) => (
            <button
              key={opt.value}
              className={`cabin-tab ${selectedCabin === opt.value ? 'active' : ''}`}
              onClick={() => setSelectedCabin(opt.value)}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <div className="results-meta">
          <span className="results-count">找到 {filteredFlights.length} 个航班</span>
          {filteredFlights.length > 0 && (
            <span className="results-compliance" title={`差标命中 ${Math.round(stats.rate * 100)}%`}>
              <span className={`compliance-dot compliance-${stats.over > 0 ? 'over' : stats.warn > 0 ? 'warn' : 'ok'}`}>
                差标命中 {Math.round(stats.rate * 100)}%
              </span>
            </span>
          )}
        </div>
      </div>

      <div className="search-results">
        {loading ? (
          <>
            <FlightCardSkeleton />
            <FlightCardSkeleton />
            <FlightCardSkeleton />
          </>
        ) : filteredFlights.length > 0 ? (
          filteredFlights.map((flight, index) => (
            <div
              key={flight.id}
              className="flight-card-wrapper"
              style={{ animationDelay: `${index * 80}ms` }}
            >
              <FlightCard flight={flight} onSelect={onAskAI ? handleSelect : undefined} />
            </div>
          ))
        ) : (
          <Empty
            icon={<SearchEmptyIcon />}
            title="暂无航班"
            description="请尝试更换出发地、目的地或日期，或让 AI 助手协助查询"
            action={
              onAskAI
                ? { label: '让 AI 帮我查', onClick: handleAskAI }
                : { label: '清除筛选', onClick: () => setSelectedCabin('all') }
            }
          />
        )}
      </div>
    </div>
  );
}

function SparkleIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M12 2l1.8 4.6L18 8l-4.2 1.4L12 14l-1.8-4.6L6 8l4.2-1.4L12 2z" />
      <path d="M19 14l.9 2.3L22 17l-2.1.7L19 20l-.9-2.3L16 17l2.1-.7L19 14z" />
    </svg>
  );
}

function HandoffIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M5 12h14M13 5l7 7-7 7" />
    </svg>
  );
}

function SwapIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M7 16V4M7 4L3 8M7 4l4 4M17 8v12m0 0l4-4m-4 4l-4-4" />
    </svg>
  );
}

function SearchEmptyIcon() {
  return (
    <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#E5E5EA" strokeWidth="1.5">
      <circle cx="11" cy="11" r="8" />
      <path d="M21 21l-4.35-4.35" />
      <path d="M8 11h6M11 8v6" strokeOpacity="0" />
    </svg>
  );
}

// Suppress unused warning — checkCompliance is imported via lib barrel for
// downstream card components but kept here for future date-based pricing logic.
void checkCompliance;
