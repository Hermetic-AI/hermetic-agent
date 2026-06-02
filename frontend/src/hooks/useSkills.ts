// useSkills — fetches the current skills list from the backend.

import { useCallback, useEffect, useState } from 'react';
import { skillsService, ApiError } from '../services';
import type { Skill } from '../types';

export interface UseSkillsResult {
  skills: Skill[];
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useSkills(): UseSkillsResult {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    skillsService
      .list(ctrl.signal)
      .then((res) => {
        setSkills(res.skills ?? []);
        setError(null);
      })
      .catch((e) => {
        if (e instanceof ApiError) {
          setError(e.message);
        } else if (e instanceof Error) {
          setError(e.message);
        } else {
          setError('Failed to load skills');
        }
        setSkills([]);
      })
      .finally(() => setLoading(false));
    return () => ctrl.abort();
  }, [tick]);

  const refresh = useCallback(() => setTick((t) => t + 1), []);
  return { skills, loading, error, refresh };
}
