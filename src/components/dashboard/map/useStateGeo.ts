/**
 * Loads the precomputed India state-boundary GeoJSON once (module-level cache)
 * and exposes its status to React. Client-only — call from a mounted component.
 * Purely additive: `geo` is `null` if the file is missing, and callers should
 * degrade gracefully (skip the dedicated state-border/backing layers).
 */

import { useEffect, useState } from "react";

import { loadStateGeo, type StateFeatureCollection } from "@/lib/worldview/geo/states";

let cache: StateFeatureCollection | null = null;
let inflight: Promise<StateFeatureCollection | null> | null = null;
let attempted = false;

function ensureGeo(): Promise<StateFeatureCollection | null> {
  if (cache) return Promise.resolve(cache);
  if (inflight) return inflight;
  inflight = loadStateGeo()
    .then((geo) => {
      attempted = true;
      cache = geo;
      inflight = null;
      return geo;
    })
    .catch(() => {
      attempted = true;
      inflight = null;
      return null;
    });
  return inflight;
}

export function useStateGeo(): StateFeatureCollection | null {
  const [geo, setGeo] = useState<StateFeatureCollection | null>(cache);

  useEffect(() => {
    let alive = true;
    if (cache) {
      setGeo(cache);
      return;
    }
    if (attempted) return;
    ensureGeo().then((g) => {
      if (alive) setGeo(g);
    });
    return () => {
      alive = false;
    };
  }, []);

  return geo;
}
