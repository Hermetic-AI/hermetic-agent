import { useState } from 'react';
import type { Flight } from '../../types';
import { FlightCard } from './FlightCard';
import { Button } from '../common';
import { FlightCardSkeleton, Empty } from '../common';
import './SearchPage.css';

const mockFlights: Flight[] = [
  {
    id: '1',
    airline: '中国国际航空',
    airlineCode: 'CA',
    flightNumber: 'CA1234',
    departure: {
      city: '北京',
      airport: '首都国际机场',
      airportCode: 'PEK',
      time: '08:30',
      date: '2026-06-01'
    },
    arrival: {
      city: '上海',
      airport: '浦东国际机场',
      airportCode: 'PVG',
      time: '10:45',
      date: '2026-06-01'
    },
    duration: '2小时15分钟',
    cabinClass: 'economy',
    price: 860,
    tax: 50,
    remainingSeats: 28,
    aircraft: '波音737-800'
  },
  {
    id: '2',
    airline: '东方航空',
    airlineCode: 'MU',
    flightNumber: 'MU5678',
    departure: {
      city: '北京',
      airport: '首都国际机场',
      airportCode: 'PEK',
      time: '10:00',
      date: '2026-06-01'
    },
    arrival: {
      city: '上海',
      airport: '浦东国际机场',
      airportCode: 'PVG',
      time: '12:20',
      date: '2026-06-01'
    },
    duration: '2小时20分钟',
    cabinClass: 'economy',
    price: 780,
    tax: 50,
    remainingSeats: 15,
    aircraft: '空客A320'
  },
  {
    id: '3',
    airline: '南方航空',
    airlineCode: 'CZ',
    flightNumber: 'CZ9012',
    departure: {
      city: '北京',
      airport: '大兴国际机场',
      airportCode: 'PKX',
      time: '14:30',
      date: '2026-06-01'
    },
    arrival: {
      city: '上海',
      airport: '虹桥国际机场',
      airportCode: 'SHA',
      time: '16:40',
      date: '2026-06-01'
    },
    duration: '2小时10分钟',
    cabinClass: 'business',
    price: 2180,
    tax: 80,
    remainingSeats: 8,
    aircraft: '波音787-9'
  }
];

type CabinClass = 'economy' | 'business' | 'first' | 'all';

export function SearchPage({ onAskAI }: { onAskAI?: (prompt: string) => void } = {}) {
  const [loading, setLoading] = useState(false);
  const [selectedCabin, setSelectedCabin] = useState<CabinClass>('economy');
  const [searchParams, setSearchParams] = useState({
    departure: '北京',
    arrival: '上海',
    date: '2026-06-01',
    passengers: 1
  });

  const handleSearch = () => {
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
    }, 1500);
  };

  const handleSelect = (flight: Flight) => {
    onAskAI?.(`帮我预订 ${flight.flightNumber}，${flight.departure.city}→${flight.arrival.city}，${flight.departure.date} ${flight.departure.time} 出发。`);
  };

  const handleAskAI = () => {
    const { departure, arrival, date, passengers } = searchParams;
    onAskAI?.(`帮我查 ${date} 从 ${departure} 到 ${arrival} 的机票，${passengers} 人。`);
  };

  const filteredFlights = selectedCabin === 'all'
    ? mockFlights
    : mockFlights.filter((f) => f.cabinClass === selectedCabin || f.price < 2000);

  const cabinOptions: { value: CabinClass; label: string }[] = [
    { value: 'all', label: '全部' },
    { value: 'economy', label: '经济舱' },
    { value: 'business', label: '商务舱' },
    { value: 'first', label: '头等舱' }
  ];

  return (
    <div className="search-page">
      <div className="search-header">
        <h1>机票查询</h1>
        <p className="search-subtitle">下方展示为示例航班；点击「让 AI 帮我查」可唤起智能助手进行实时查询。</p>
      </div>

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
          <button className="swap-btn" type="button" aria-label="交换出发与到达">
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
              onChange={(e) => setSearchParams({ ...searchParams, date: e.target.value })}
            />
          </div>
          <div className="search-field">
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
          <Button onClick={handleSearch} className="search-btn">
            搜索
          </Button>
          {onAskAI && (
            <Button variant="secondary" onClick={handleAskAI} className="search-ai-btn">
              <SparkleIcon />
              让 AI 帮我查
            </Button>
          )}
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
        <div className="results-count">
          找到 {filteredFlights.length} 个航班
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
