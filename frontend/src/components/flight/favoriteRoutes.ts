// "我的常飞" — 收藏常用出发-到达路线,localStorage 持久化.
//
// 真实接入会移到后端 (per-user 偏好),目前 demo 用 localStorage 够用.

const STORAGE_KEY = 'openagent.favorite_routes.v1';

export interface FavoriteRoute {
  id: string;
  departure: string;
  arrival: string;
  createdAt: number;
  /** 使用次数 (本地累加),用于排序. */
  useCount: number;
}

function safeRead(): FavoriteRoute[] {
  if (typeof localStorage === 'undefined') return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (f) =>
        f && typeof f.id === 'string' &&
        typeof f.departure === 'string' &&
        typeof f.arrival === 'string',
    );
  } catch {
    return [];
  }
}

function safeWrite(routes: FavoriteRoute[]): void {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(routes));
  } catch {
    // 配额满 / 隐私模式 — 静默忽略
  }
}

export function loadFavoriteRoutes(): FavoriteRoute[] {
  return safeRead().sort((a, b) => b.useCount - a.useCount);
}

export function addFavoriteRoute(input: { departure: string; arrival: string }): FavoriteRoute {
  const list = safeRead();
  // 已有同样路线 → 不重复添加,只是更新时间戳
  const existing = list.find(
    (r) => r.departure === input.departure && r.arrival === input.arrival,
  );
  if (existing) {
    existing.createdAt = Date.now();
    safeWrite(list);
    return existing;
  }
  const created: FavoriteRoute = {
    id: `${input.departure}-${input.arrival}-${Date.now()}`,
    departure: input.departure,
    arrival: input.arrival,
    createdAt: Date.now(),
    useCount: 0,
  };
  list.push(created);
  safeWrite(list);
  return created;
}

export function removeFavoriteRoute(id: string): void {
  const list = safeRead().filter((r) => r.id !== id);
  safeWrite(list);
}

export function bumpFavoriteUsage(id: string): void {
  const list = safeRead();
  const found = list.find((r) => r.id === id);
  if (found) {
    found.useCount += 1;
    safeWrite(list);
  }
}
