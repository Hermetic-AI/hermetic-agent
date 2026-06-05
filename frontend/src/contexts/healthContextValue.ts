// Pure data layer for the health polling singleton.
//
// This file has no JSX so Vite's fast-refresh treats it as a "constants
// only" module and stays happy.  The actual `HealthProvider` component
// lives in `HealthProvider.tsx` and consumes the context defined here.

import { createContext } from 'react';
import type { ReadyResponse } from '../types';

export type HealthState = 'unknown' | 'healthy' | 'degraded' | 'unreachable';

export interface UseHealthResult {
  state: HealthState;
  detail: string | null;
  ready: ReadyResponse | null;
  /** Force an immediate re-check (and bypass the /ready cache). */
  refresh: () => void;
}

export interface HealthContextValue extends UseHealthResult {
  /** True when polling is paused (tab hidden). */
  paused: boolean;
}

export const HealthContext = createContext<HealthContextValue | null>(null);
