// useScenarios — fetches the list of registered scenarios and exposes
// helpers for the sidebar selector / debug UI.

import { useCallback, useEffect, useState } from 'react';
import { scenarioService, ApiError } from '../services';
import type { ScenarioSummary } from '../types';

export interface UseScenariosResult {
  scenarios: ScenarioSummary[];
  loading: boolean;
  error: string | null;
  reload: () => void;
}

export function useScenarios(tag?: string): UseScenariosResult {
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    scenarioService
      .list(tag, ctrl.signal)
      .then((res) => {
        setScenarios(res.scenarios ?? []);
      })
      .catch((e: unknown) => {
        if (e instanceof ApiError) setError(e.message);
        else if (e instanceof Error) setError(e.message);
        else setError('Unknown error');
      })
      .finally(() => setLoading(false));
    return () => ctrl.abort();
  }, [tag, tick]);

  const reload = useCallback(() => setTick((n) => n + 1), []);

  return { scenarios, loading, error, reload };
}
