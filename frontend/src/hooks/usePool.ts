// usePool — fetches agent pool stats.

import { useEffect, useState } from 'react';
import { poolService } from '../services';
import type { PoolStatsResponse } from '../types';

export interface UsePoolResult {
  stats: PoolStatsResponse | null;
  loading: boolean;
  error: string | null;
}

export function usePool(): UsePoolResult {
  const [stats, setStats] = useState<PoolStatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    poolService
      .stats(ctrl.signal)
      .then((res) => {
        setStats(res);
        setError(null);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : 'Failed to load pool stats');
      })
      .finally(() => setLoading(false));
    return () => ctrl.abort();
  }, []);

  return { stats, loading, error };
}
