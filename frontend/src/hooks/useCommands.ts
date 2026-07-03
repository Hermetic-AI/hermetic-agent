// useCommands — fetches the list of command assets from `/agent/commands/`.
//
// Mirrors useAgents (tick-refetch, no abort, alive guard).  Used by the
// chat shell to populate the slash-command asset picker.  Talks through
// the Vite dev-server proxy via `commandsApi.list()`.

import { useEffect, useState } from 'react';
import { commandsApi } from '../services/commands';
import type { CommandAsset } from '../types/assets';

export interface UseCommandsResult {
  commands: CommandAsset[];
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useCommands(): UseCommandsResult {
  const [commands, setCommands] = useState<CommandAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    commandsApi
      .list({ limit: 100 })
      .then((res) => {
        if (!alive) return;
        setCommands(res.items ?? []);
        setError(null);
      })
      .catch((e) => {
        if (!alive) return;
        setError(e instanceof Error ? e.message : 'Failed to load commands');
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [tick]);

  return { commands, loading, error, refresh: () => setTick((t) => t + 1) };
}
