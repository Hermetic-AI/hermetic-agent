// usePrompts — fetches the list of prompt assets from `/agent/prompts/`.
//
// Mirrors useAgents (tick-refetch, no abort, alive guard).  Used by the
// chat shell to populate the prompt asset picker.  The service talks
// through the Vite dev-server proxy, so calling `promptsApi.list()` (not
// a hard-coded URL) keeps the proxy wiring intact.

import { useEffect, useState } from 'react';
import { promptsApi } from '../services/prompts';
import type { PromptAsset } from '../types/assets';

export interface UsePromptsResult {
  prompts: PromptAsset[];
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function usePrompts(): UsePromptsResult {
  const [prompts, setPrompts] = useState<PromptAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    promptsApi
      .list({ limit: 100 })
      .then((res) => {
        if (!alive) return;
        setPrompts(res.items ?? []);
        setError(null);
      })
      .catch((e) => {
        if (!alive) return;
        setError(e instanceof Error ? e.message : 'Failed to load prompts');
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [tick]);

  return { prompts, loading, error, refresh: () => setTick((t) => t + 1) };
}
