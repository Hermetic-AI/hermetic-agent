// HealthProvider — single shared polling loop for the backend health probe.
//
// Why this exists (replaces the per-component `useHealth(intervalMs)` hook):
//   - Old design: every component that wanted health state called
//     `useHealth(20_000)`, each spinning its own setInterval.  Two callers
//     meant **2x** traffic on /health + /ready (one /health + one /ready
//     per check per caller) — roughly a request every 5s on a quiet page.
//   - Worse, `useHealth(0)` was documented as "passive, no polling" but
//     `setInterval(fn, 0)` actually fires ~every 4ms in browsers, hammering
//     the backend with hundreds of requests per second while the settings
//     drawer was open.
//   - Polling also kept running when the tab was hidden in the background.
//
// What this does:
//   - One polling loop per app (singleton via React Context), shared by all
//     consumers (`useHealth()` is read-only).
//   - `intervalMs <= 0` means "one fetch on mount, no polling".
//   - `/health` is called on every tick; `/ready` (which is heavier — it
//     inspects storage / bridge / registries) is cached for `readyIntervalMs`
//     (default 5x the /health interval) unless `refresh()` is called or
//     the previous /ready failed.
//   - Polling pauses while `document.hidden` is true; a `visibilitychange`
//     listener resumes + immediately re-checks when the tab comes back.

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { systemService, ApiError } from '../services';
import type { ReadyResponse } from '../types';
import {
  HealthContext,
  type HealthContextValue,
  type HealthState,
  type UseHealthResult,
} from './healthContextValue';

export type { HealthState, UseHealthResult, HealthContextValue };

interface HealthProviderProps {
  children: ReactNode;
  /**
   * Polling interval in ms for `/health`.  Default 30s.
   * Set to 0 or negative to fetch once on mount and never again.
   */
  intervalMs?: number;
  /**
   * How often to re-fetch `/ready` (the expensive endpoint).  Defaults to
   * 5x `intervalMs`.  Ignored if `intervalMs <= 0`.
   */
  readyIntervalMs?: number;
}

const DEFAULT_INTERVAL_MS = 30_000;
const DEFAULT_READY_RATIO = 5;

function isDocumentHidden(): boolean {
  return typeof document !== 'undefined' && document.hidden;
}

export function HealthProvider({
  children,
  intervalMs = DEFAULT_INTERVAL_MS,
  readyIntervalMs,
}: HealthProviderProps) {
  const [state, setState] = useState<HealthState>('unknown');
  const [detail, setDetail] = useState<string | null>(null);
  const [ready, setReady] = useState<ReadyResponse | null>(null);
  const [paused, setPaused] = useState<boolean>(isDocumentHidden);
  const [tick, setTick] = useState(0);

  // Refs that need to be read inside the polling closure without re-creating
  // the effect each time.  `lastReadyAt` is a wall-clock ms timestamp; 0 means
  // "never fetched /ready since the last refresh" and forces the next check
  // to include /ready.  `inFlight` dedupes overlapping ticks (e.g. when the
  // interval fires while the previous fetch hasn't returned yet).
  const lastReadyAtRef = useRef<number>(0);
  const inFlightRef = useRef<boolean>(false);
  const lastStatusRef = useRef<HealthState>('unknown');

  const readyInterval =
    readyIntervalMs ?? Math.max(intervalMs * DEFAULT_READY_RATIO, 60_000);

  // Page Visibility API — pause polling when the tab is hidden, resume
  // (and re-check immediately) when it becomes visible again.
  useEffect(() => {
    if (typeof document === 'undefined') return;
    const onVis = () => setPaused(document.hidden);
    document.addEventListener('visibilitychange', onVis);
    return () => document.removeEventListener('visibilitychange', onVis);
  }, []);

  useEffect(() => {
    let alive = true;
    const ctrl = new AbortController();
    let intervalId: number | null = null;

    async function check() {
      if (!alive) return;
      if (paused) return;
      if (inFlightRef.current) return;
      inFlightRef.current = true;

      const localCtrl = new AbortController();
      const onParentAbort = () => localCtrl.abort();
      ctrl.signal.addEventListener('abort', onParentAbort);

      try {
        // 1. Cheap liveness probe — always called on each tick.
        await systemService.health(localCtrl.signal);
        if (!alive || localCtrl.signal.aborted) return;

        // 2. /ready is cached unless stale, never-fetched, or last ready call
        //    failed (lastStatusRef != 'healthy' && != 'degraded-with-ready').
        const now = Date.now();
        const haveReady = lastReadyAtRef.current > 0;
        const readyStale = !haveReady || now - lastReadyAtRef.current >= readyInterval;
        const previousOk = lastStatusRef.current === 'healthy';
        if (!readyStale && previousOk) {
          // /health OK, /ready cache fresh — nothing to do.
          return;
        }

        // 3. /ready is expensive (hits storage/bridge/registries); call only
        //    when we have to.
        try {
          const r = await systemService.ready(localCtrl.signal);
          if (!alive || localCtrl.signal.aborted) return;
          setReady(r);
          lastReadyAtRef.current = Date.now();
          lastStatusRef.current = r.status === 'ready' ? 'healthy' : 'degraded';
          setState(lastStatusRef.current);
          setDetail(r.status === 'ready' ? null : r.reason ?? 'Backend reports not_ready');
        } catch (inner) {
          if (!alive) return;
          setReady(null);
          lastStatusRef.current = 'degraded';
          setState('degraded');
          setDetail(inner instanceof Error ? inner.message : 'Ready check failed');
          // Don't bump lastReadyAtRef — let the next tick retry.
        }
      } catch (e) {
        if (!alive) return;
        lastStatusRef.current = 'unreachable';
        setState('unreachable');
        setReady(null);
        setDetail(
          e instanceof ApiError
            ? e.message
            : e instanceof Error
              ? e.message
              : 'Network error',
        );
      } finally {
        ctrl.signal.removeEventListener('abort', onParentAbort);
        inFlightRef.current = false;
      }
    }

    void check();
    if (intervalMs > 0) {
      intervalId = window.setInterval(check, intervalMs);
    }

    return () => {
      alive = false;
      ctrl.abort();
      if (intervalId !== null) window.clearInterval(intervalId);
    };
  }, [intervalMs, readyInterval, paused, tick]);

  const refresh = useCallback(() => {
    // Invalidate /ready cache so the next tick re-fetches the heavy endpoint.
    lastReadyAtRef.current = 0;
    setTick((t) => t + 1);
  }, []);

  const value: HealthContextValue = {
    state,
    detail,
    ready,
    refresh,
    paused,
  };

  return <HealthContext.Provider value={value}>{children}</HealthContext.Provider>;
}
