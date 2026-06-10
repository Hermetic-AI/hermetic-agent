// 差旅产品的"用户快照" — 给 Welcome / Sidebar 提供上下文.
// 真实生产会从后端 /agent/profile 拉,目前用 localStorage + mock.

const STORAGE_KEY = 'openagent.user_snapshot.v1';

export interface UpcomingTrip {
  id: string;
  route: string;       // "北京 → 上海"
  date: string;        // yyyy-MM-dd
  flightNo: string;
  cabin: string;
}

export interface UserSnapshot {
  displayName: string;
  /** 近 30 天已出行次数. */
  recentTripCount: number;
  /** 近 30 天差标命中率 (0-1). */
  complianceHitRate: number;
  /** 待出行 / 待支付 数量. */
  pendingOrderCount: number;
  upcomingTrips: UpcomingTrip[];
  /** 常去的城市,按使用频次降序. */
  frequentCities: string[];
}

const DEFAULT_SNAPSHOT: UserSnapshot = {
  displayName: '差旅用户',
  recentTripCount: 3,
  complianceHitRate: 0.87,
  pendingOrderCount: 1,
  upcomingTrips: [
    {
      id: 't-1',
      route: '北京 → 上海',
      date: futureDateIso(3),
      flightNo: 'CA1501',
      cabin: '经济舱',
    },
    {
      id: 't-2',
      route: '上海 → 深圳',
      date: futureDateIso(7),
      flightNo: 'CZ3592',
      cabin: '经济舱',
    },
  ],
  frequentCities: ['北京', '上海', '深圳', '广州'],
};

export function loadUserSnapshot(): UserSnapshot {
  if (typeof localStorage === 'undefined') return DEFAULT_SNAPSHOT;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_SNAPSHOT;
    const parsed = JSON.parse(raw) as Partial<UserSnapshot>;
    return { ...DEFAULT_SNAPSHOT, ...parsed };
  } catch {
    return DEFAULT_SNAPSHOT;
  }
}

export function saveUserSnapshot(snap: UserSnapshot): void {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(snap));
  } catch {
    /* ignore */
  }
}

/** 根据本地时间给出中文问候. */
export function greetingForNow(now: Date = new Date()): string {
  const h = now.getHours();
  if (h < 6) return '凌晨好';
  if (h < 11) return '早上好';
  if (h < 13) return '中午好';
  if (h < 18) return '下午好';
  return '晚上好';
}

function futureDateIso(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}
