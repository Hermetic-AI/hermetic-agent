// useHealth — consumer hook for the HealthContext singleton.
//
// The polling loop is owned by `<HealthProvider>` in App.tsx.  This hook is
// a thin context reader; the `intervalMs` argument is ignored (left in the
// signature for backward compatibility with callers that pre-date the
// singleton refactor — they'll be migrated in a follow-up).

import { useContext } from 'react';
import {
  HealthContext,
  type HealthState,
  type UseHealthResult,
} from '../contexts/healthContextValue';

export type { HealthState, UseHealthResult };

/**
 * Read the shared health state.  Must be called inside `<HealthProvider>`.
 *
 * @deprecated Pass `intervalMs` to `<HealthProvider intervalMs={...} />`
 * instead.  This hook is now a thin context reader; the polling loop is a
 * singleton owned by the provider.  The argument is ignored.
 */
export function useHealth(_intervalMs?: number): UseHealthResult {
  const ctx = useContext(HealthContext);
  if (!ctx) {
    throw new Error(
      'useHealth() must be called inside <HealthProvider>. ' +
        'Wrap your app with <HealthProvider> in App.tsx.',
    );
  }
  // `paused` is internal — don't leak it through the consumer-facing hook.
  const { paused: _paused, ...rest } = ctx;
  void _paused;
  return rest;
}
