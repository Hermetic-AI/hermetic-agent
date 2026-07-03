// useSkills — fetches the list of skill assets from `/agent/skills-db/`.
//
// Mirrors useAgents (tick-refetch, no abort, alive guard).  Used by the
// chat shell to populate the skill asset picker.  Talks through the Vite
// dev-server proxy via `skillsApi.list()`.

import { useEffect, useState } from 'react';
import { skillsApi } from '../services/skills';
import type { SkillAsset } from '../types/assets';

export interface UseSkillsResult {
  skills: SkillAsset[];
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useSkills(): UseSkillsResult {
  const [skills, setSkills] = useState<SkillAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    skillsApi
      .list({ limit: 100 })
      .then((res) => {
        if (!alive) return;
        setSkills(res.skills ?? []);
        setError(null);
      })
      .catch((e) => {
        if (!alive) return;
        setError(e instanceof Error ? e.message : 'Failed to load skills');
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [tick]);

  return { skills, loading, error, refresh: () => setTick((t) => t + 1) };
}
