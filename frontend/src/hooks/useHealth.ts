// useHealth — polls the backend's /health and /ready endpoints.

import { useEffect, useState } from 'react';
import { systemService, ApiError } from '../services';
import type { ReadyResponse } from '../types';

export type HealthState = 'unknown' | 'healthy' | 'degraded' | 'unreachable';

export interface UseHealthResult {
  state: HealthState;
  detail: string | null;
  ready: ReadyResponse | null;
  /** Force a re-check. */
  refresh: () => void;
}

const DEFAULT_INTERVAL = 15_000;

export function useHealth(
  intervalMs: number = DEFAULT_INTERVAL,
): UseHealthResult {
  const [state, setState] = useState<HealthState>('unknown');
  const [detail, setDetail] = useState<string | null>(null);
  const [ready, setReady] = useState<ReadyResponse | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    const ctrl = new AbortController();

    async function check() {
      try {
        await systemService.health(ctrl.signal);
        if (!alive) return;
        try {
          const r = await systemService.ready(ctrl.signal);
          if (!alive) return;
          setReady(r);
          if (r.status === 'ready') {
            setState('healthy');
            setDetail(null);
          } else {
            setState('degraded');
            setDetail(r.reason ?? 'Backend reports not_ready');
          }
        } catch (inner) {
          if (!alive) return;
          setReady(null);
          setState('degraded');
          setDetail(inner instanceof Error ? inner.message : 'Ready check failed');
        }
      } catch (e) {
        if (!alive) return;
        setState('unreachable');
        setDetail(
          e instanceof ApiError
            ? e.message
            : e instanceof Error
              ? e.message
              : 'Network error',
        );
        setReady(null);
      }
    }

    void check();
    const id = window.setInterval(check, intervalMs);

    return () => {
      alive = false;
      ctrl.abort();
      window.clearInterval(id);
    };
  }, [intervalMs, tick]);

  return { state, detail, ready, refresh: () => setTick((t) => t + 1) };
}
