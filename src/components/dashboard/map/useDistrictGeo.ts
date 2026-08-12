/**
 * Loads the India district GeoJSON once (module-level cache) and exposes its
 * status to React. Client-only — call from a mounted component.
 */

import { useEffect, useState } from "react";

import { loadDistrictGeo, type DistrictGeo } from "@/lib/worldview/geo/districts";

export type GeoStatus = "loading" | "ready" | "missing";

let cache: DistrictGeo | null = null;
let inflight: Promise<DistrictGeo | null> | null = null;
let attempted = false;

function ensureGeo(): Promise<DistrictGeo | null> {
  if (cache) return Promise.resolve(cache);
  if (inflight) return inflight;
  inflight = loadDistrictGeo()
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

export interface UseDistrictGeo {
  geo: DistrictGeo | null;
  status: GeoStatus;
}

export function useDistrictGeo(): UseDistrictGeo {
  const [geo, setGeo] = useState<DistrictGeo | null>(cache);
  const [status, setStatus] = useState<GeoStatus>(
    cache ? "ready" : attempted ? "missing" : "loading",
  );

  useEffect(() => {
    let alive = true;
    if (cache) {
      setGeo(cache);
      setStatus("ready");
      return;
    }
    ensureGeo().then((g) => {
      if (!alive) return;
      setGeo(g);
      setStatus(g ? "ready" : "missing");
    });
    return () => {
      alive = false;
    };
  }, []);

  return { geo, status };
}
