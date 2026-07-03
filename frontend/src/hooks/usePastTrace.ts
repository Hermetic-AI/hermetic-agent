// usePastTrace — fetch a previously stored turn's full work trace.
//
// Used when the user clicks a past turn in the session list (or history
// sidebar) so the WorkPanel can replay its events.

import { useEffect, useState } from 'react';
import type { TraceEvent } from './useWorkPanel';

export interface UsePastTraceResult {
  events: TraceEvent[];
  loading: boolean;
  error: string | null;
}

export function usePastTrace(turnId: string | null): UsePastTraceResult {
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!turnId) {
      setEvents([]);
      setLoading(false);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetch(`/agent/turns/${turnId}/work-trace`, {
      credentials: 'include',
      headers: { Accept: 'application/json' },
    })
      .then((r) => {
        if (!r.ok) {
          throw new Error(`HTTP ${r.status}: ${r.statusText}`);
        }
        return r.json() as Promise<{
          events?: Array<{
            seq: number;
            at: string;
            kind: string;
            payload: Record<string, unknown>;
          }>;
        }>;
      })
      .then((data) => {
        if (cancelled) return;
        setEvents((data.events ?? []) as TraceEvent[]);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [turnId]);

  return { events, loading, error };
}