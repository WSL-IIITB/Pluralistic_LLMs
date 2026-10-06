/** Full persona descriptions (long text) from GET /api/personas. */

import { useEffect, useState } from "react";

import { cachedJson } from "./api";

export interface PersonaProfile {
  regionId: string;
  personaId: string;
  name: string;
  definition: string;
  topics: { key: string; label: string; profile: string }[];
}

const load = cachedJson<PersonaProfile[]>("/api/personas");

/** The full profile for one persona, or null while loading / if the backend is unreachable. */
export function usePersonaProfile(regionId: string, personaId: string): PersonaProfile | null {
  const [all, setAll] = useState<PersonaProfile[] | null>(null);
  useEffect(() => {
    let alive = true;
    void load().then((p) => alive && setAll(p));
    return () => {
      alive = false;
    };
  }, []);
  return all?.find((p) => p.regionId === regionId && p.personaId === personaId) ?? null;
}
